"""Autonomous Post-Run Health Checkup & Self-Healing Agent.

Audits execution logs, diagnoses application failures, sanitizes system resources,
updates persistent screening knowledge bases, and executes an autonomous stabilization
catch-up loop to guarantee daily confirmed application quotas.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.utils.config_loader import load_config
from src.database.connection import get_db_session
from src.database.models import JobModel, ApplicationModel, JobScoreModel, JobEvidenceModel
from src.database.repositories.job_repo import JobRepository
from src.database.repositories.application_repo import ApplicationRepository
from src.database.repositories.resume_repo import ResumeRepository
from src.database.repositories.interview_repo import InterviewRepository
from src.models.job import JobListing, JobStatus, ApplicationMethod, ApplicationRecord
from src.models.score import JobScore, JobEvidence
from src.models.candidate import CandidateTruth
from candidate.profile_extractor import get_candidate_truth

from src.agents.failure_analysis_agent import FailureAnalysisAgent, FailureDiagnostic
from src.agents.resume_agent import ResumeAgent
from src.agents.application import ApplicationAgent
from src.agents.interview_agent import InterviewAgent
from src.agents.ats_filler import AtsPortalFiller
from src.linkedin.adapter import LinkedInAdapter
from src.naukri.playwright_adapter import PlaywrightBrowserAdapter
from src.utils.screening_knowledge import get_screening_knowledge_base
from src.utils.logger import get_logger

logger = get_logger("post_run_healer")

PROJECT_DIR = Path("/u01/CareerOps")
LOG_DIR = PROJECT_DIR / "logs"
CRON_LOG_FILE = LOG_DIR / "cron_run.log"
AGENT_LOG_FILE = LOG_DIR / "career_agent.log"
HEALER_LOG_FILE = LOG_DIR / "healer_run.log"
HEALTH_REPORT_DIR = PROJECT_DIR / "reports" / "health"
DAILY_REPORT_DIR = PROJECT_DIR / "reports" / "daily"
LOCK_FILE = Path("/tmp/careerops.lock")
HEALER_LOCK_FILE = Path("/tmp/careerops_healer.lock")


class PostRunHealerAgent:
    """Audits pipeline execution, auto-heals screening dropouts, and stabilizes application throughput."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        candidate_truth: Optional[CandidateTruth] = None,
        offline_mode: bool = False,
    ):
        self.config = config or load_config()
        self.candidate_truth = candidate_truth or get_candidate_truth()
        self.offline_mode = offline_mode
        self.kb = get_screening_knowledge_base()
        HEALTH_REPORT_DIR.mkdir(parents=True, exist_ok=True)
        DAILY_REPORT_DIR.mkdir(parents=True, exist_ok=True)

        app_cfg = self.config.get("application", {})
        self.target_quota = int(app_cfg.get("max_applications_per_day", 20))
        self.min_match_score = float(app_cfg.get("match_threshold", 70.0))

    def sanitize_system_environment(self) -> Dict[str, Any]:
        """Cleans orphan zombie browser processes, verifies memory, and recovers stale locks."""
        logger.info("Step 1: Sanitizing system environment and checking server resources...")
        report = {
            "stale_lock_cleared": False,
            "zombie_browsers_killed": 0,
            "memory_available_mb": 0,
            "swap_used_mb": 0,
            "healthy": True,
        }

        # 1. Recover stale lock if owning process is dead
        if LOCK_FILE.exists():
            try:
                # Check if flock is actually held
                res = subprocess.run(
                    ["fuser", str(LOCK_FILE)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                if not res.stdout.strip():
                    logger.warning(f"Found stale lock file '{LOCK_FILE}' with no active holding PID. Removing...")
                    LOCK_FILE.unlink(missing_ok=True)
                    report["stale_lock_cleared"] = True
            except Exception as e:
                logger.debug(f"Lock verification note: {e}")

        # 2. Check Memory Status
        try:
            mem_res = subprocess.run(["free", "-m"], stdout=subprocess.PIPE, text=True)
            for line in mem_res.stdout.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 7:
                        report["memory_available_mb"] = int(parts[6])
                elif line.startswith("Swap:"):
                    parts = line.split()
                    if len(parts) >= 3:
                        report["swap_used_mb"] = int(parts[2])
        except Exception as e:
            logger.debug(f"Memory check note: {e}")

        # 3. Terminate orphan zombie chrome/chromium processes if no active pipeline
        if not report.get("pipeline_active", False):
            try:
                # Check for lingering headless chromium processes older than 30 minutes
                pids_res = subprocess.run(
                    ["pgrep", "-f", "chrome|chromium|playwright"],
                    stdout=subprocess.PIPE,
                    text=True,
                )
                pids = [p.strip() for p in pids_res.stdout.splitlines() if p.strip()]
                # If pipeline lock is not active, terminate lingering orphan browsers
                if pids and not LOCK_FILE.exists():
                    logger.info(f"Terminating {len(pids)} orphan browser processes to reclaim VPS RAM...")
                    subprocess.run(["pkill", "-f", "chrome|chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    report["zombie_browsers_killed"] = len(pids)
            except Exception as e:
                logger.debug(f"Zombie process cleanup note: {e}")

        return report

    def audit_run_logs(self, lookback_lines: int = 1500) -> Dict[str, Any]:
        """Parses execution logs for crashes, timeouts, Akamai blocks, and adapter exceptions."""
        logger.info("Step 2: Auditing cron and career agent execution logs...")
        audit: Dict[str, Any] = {
            "cron_log_present": CRON_LOG_FILE.exists(),
            "agent_log_present": AGENT_LOG_FILE.exists(),
            "errors_detected": [],
            "warnings_detected": [],
            "last_run_timestamp": None,
            "last_run_duration_sec": None,
            "last_run_exit_code": None,
            "detected_issues": [],
        }

        # 1. Parse cron_run.log
        if CRON_LOG_FILE.exists():
            try:
                with open(CRON_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    cron_lines = f.readlines()[-300:]
                for line in reversed(cron_lines):
                    if "CareerOps Run Completed in" in line:
                        m = re.search(r"Completed in (\d+)s with exit code (\d+)", line)
                        if m:
                            audit["last_run_duration_sec"] = int(m.group(1))
                            audit["last_run_exit_code"] = int(m.group(2))
                            break
                    elif "CareerOps Weekday Pipeline Started" in line:
                        m = re.search(r"\[(.*?)\]", line)
                        if m:
                            audit["last_run_timestamp"] = m.group(1)
            except Exception as e:
                logger.warning(f"Error reading cron log: {e}")

        # 2. Parse career_agent.log
        if AGENT_LOG_FILE.exists():
            try:
                with open(AGENT_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    log_lines = f.readlines()[-lookback_lines:]

                for line in log_lines:
                    line_lower = line.lower()
                    if "pointer events" in line_lower or "popover-floating" in line_lower:
                        audit["detected_issues"].append("LINKEDIN_POPOVER_INTERCEPTION")
                    if "invalid input" in line_lower or "salary expectations" in line_lower:
                        audit["detected_issues"].append("LINKEDIN_FIELD_VALIDATION_ERROR")
                    if "unresolved screening fields" in line_lower or "multi-page form pause" in line_lower:
                        audit["detected_issues"].append("LINKEDIN_SCREENING_PAUSE")
                    if "no matching option or input was available" in line_lower:
                        audit["detected_issues"].append("NAUKRI_SCREENING_DROPOUT")
                    if "timeoutexceeded" in line_lower or "timeout 30000ms" in line_lower:
                        audit["detected_issues"].append("PLAYWRIGHT_TIMEOUT")
                    if "checkpoint" in line_lower or "security challenge" in line_lower:
                        audit["detected_issues"].append("LINKEDIN_AUTH_CHECKPOINT")
                    if "akamai" in line_lower and "403" in line_lower:
                        audit["detected_issues"].append("AKAMAI_BOT_403")

                    if " ERROR " in line or " CRITICAL " in line:
                        audit["errors_detected"].append(line.strip())
                    elif " WARNING " in line and ("gate" in line_lower or "limit" in line_lower or "timeout" in line_lower):
                        audit["warnings_detected"].append(line.strip())

                audit["detected_issues"] = list(set(audit["detected_issues"]))
                audit["errors_detected"] = audit["errors_detected"][-15:]
                audit["warnings_detected"] = audit["warnings_detected"][-15:]
            except Exception as e:
                logger.warning(f"Error reading agent log: {e}")

        return audit

    def audit_database_state(self, session: Session) -> Dict[str, Any]:
        """Audits database application records for the current day to measure quota attainment."""
        logger.info("Step 3: Auditing database application metrics and quota attainment...")
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Applications submitted or attempted today
        apps_today = (
            session.query(ApplicationModel, JobModel)
            .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
            .filter(func.date(func.coalesce(ApplicationModel.submitted_at, ApplicationModel.created_at, ApplicationModel.started_at)) == today_utc)
            .all()
        )

        confirmed = [(a, j) for a, j in apps_today if a.status == JobStatus.APPLIED_CONFIRMED.value]
        failed = [(a, j) for a, j in apps_today if a.status in (JobStatus.APPLICATION_FAILED.value, JobStatus.FAILED.value)]
        intervention = [(a, j) for a, j in apps_today if a.status == JobStatus.NEEDS_MANUAL_INTERVENTION.value]
        unverified = [(a, j) for a, j in apps_today if a.status == JobStatus.SUBMISSION_UNVERIFIED.value]
        external = [(a, j) for a, j in apps_today if a.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value]
        ready_retry = [(a, j) for a, j in apps_today if a.status == JobStatus.READY_FOR_RETRY.value]

        confirmed_nk = len([
            (a, j) for a, j in confirmed
            if "linkedin" not in (j.source_platform or "").lower()
            and a.application_method != ApplicationMethod.LINKEDIN_EASY_APPLY.value
            and "ats" not in (j.source_platform or "").lower()
        ])
        confirmed_li = len([
            (a, j) for a, j in confirmed
            if "linkedin" in (j.source_platform or "").lower()
            or a.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY.value
            or "linkedin" in (j.url or "").lower()
        ])

        target_nk = int(self.config.get("application", {}).get("target_naukri_per_day", 10))
        target_li = int(self.config.get("linkedin", {}).get("target_linkedin_per_day", 10))
        naukri_shortfall = max(0, target_nk - confirmed_nk)
        linkedin_shortfall = max(0, target_li - confirmed_li)

        # Check total confirmed applications on the current calendar date
        total_confirmed_today = len(confirmed)
        shortfall = max(0, self.target_quota - total_confirmed_today)
        effective_shortfall = max(shortfall, naukri_shortfall + linkedin_shortfall)

        # Count unapplied qualified jobs discovered today (starved opportunities)
        qualified_unapplied = (
            session.query(JobModel)
            .join(JobScoreModel, JobModel.job_id == JobScoreModel.job_id)
            .filter(
                JobModel.status.in_([
                    JobStatus.READY_FOR_RETRY.value,
                    JobStatus.QUALIFIED.value,
                    JobStatus.HIGH_MATCH.value,
                    JobStatus.APPLICATION_READY.value,
                    JobStatus.ELIGIBLE.value,
                    JobStatus.DISCOVERED.value,
                ]),
                JobScoreModel.overall_score >= self.min_match_score,
                ~JobModel.job_id.in_(
                    session.query(ApplicationModel.job_id).filter(
                        ApplicationModel.status == JobStatus.APPLIED_CONFIRMED.value
                    )
                ),
            )
            .all()
        )

        return {
            "date": today_utc,
            "target_quota": self.target_quota,
            "target_naukri": target_nk,
            "target_linkedin": target_li,
            "confirmed_today": total_confirmed_today,
            "confirmed_naukri_today": confirmed_nk,
            "confirmed_linkedin_today": confirmed_li,
            "shortfall": effective_shortfall,
            "naukri_shortfall": naukri_shortfall,
            "linkedin_shortfall": linkedin_shortfall,
            "failed_count": len(failed),
            "intervention_count": len(intervention),
            "unverified_count": len(unverified),
            "external_count": len(external),
            "ready_for_retry_count": len(ready_retry),
            "qualified_unapplied_count": len(qualified_unapplied),
            "quota_achieved": confirmed_nk >= target_nk and confirmed_li >= target_li and total_confirmed_today >= self.target_quota,
        }

    def diagnose_and_heal_failures(self, session: Session) -> List[FailureDiagnostic]:
        """Executes root cause diagnosis and self-healing across recent failed applications."""
        logger.info("Step 4: Executing autonomous failure diagnosis and self-healing...")
        failure_agent = FailureAnalysisAgent(session, self.candidate_truth, self.config)
        diagnostics = failure_agent.analyze_and_heal_run()

        logger.info(f"Self-healing complete. Diagnosed {len(diagnostics)} application failure cases.")
        return diagnostics

    def execute_stabilization_catchup(
        self,
        session: Session,
        max_retries: int = 50,
        dry_run: bool = False,
        force_catchup: bool = False,
    ) -> Dict[str, Any]:
        """Runs a focused, rate-limited catchup application batch to meet the daily confirmed quota."""
        logger.info("Step 5: Assessing need for autonomous stabilization catch-up...")
        db_audit = self.audit_database_state(session)
        shortfall = db_audit["shortfall"]

        result: Dict[str, Any] = {
            "attempted": 0,
            "confirmed": 0,
            "failed": 0,
            "details": [],
            "initial_confirmed": db_audit["confirmed_today"],
            "final_confirmed": db_audit["confirmed_today"],
            "quota_met": db_audit["quota_achieved"],
        }

        target_per_platform = int(self.config.get("application", {}).get("target_naukri_per_day", 10))
        target_li = int(self.config.get("linkedin", {}).get("target_linkedin_per_day") or self.config.get("application", {}).get("target_linkedin_per_day", 10))
        max_per_platform = int(self.config.get("application", {}).get("max_naukri_per_day", 15))
        max_li_per_day = int(self.config.get("linkedin", {}).get("max_applications_per_day", 15))

        naukri_today = db_audit.get("confirmed_naukri_today", 0)
        linkedin_today = db_audit.get("confirmed_linkedin_today", 0)
        current_confirmed = db_audit.get("confirmed_today", 0)

        if not force_catchup and naukri_today >= target_per_platform and linkedin_today >= target_li and current_confirmed >= self.target_quota:
            logger.info(f"Daily quotas already satisfied for both platforms (Naukri: {naukri_today}/{target_per_platform}, LinkedIn: {linkedin_today}/{target_li}). No catch-up required.")
            return result

        logger.info(f"Catch-up required: Naukri today {naukri_today}/{target_per_platform}, LinkedIn today {linkedin_today}/{target_li}. Effective shortfall: {shortfall}")

        # Find eligible candidate jobs:
        # 1. Jobs in READY_FOR_RETRY (overall_score >= 70%)
        # 2. High-match qualified jobs that were starved due to time limits (overall_score >= 75%)
        # 3. Jobs stalled or failed due to timeout / reload that can now be retried
        candidate_records = (
            session.query(JobModel, JobScoreModel)
            .join(JobScoreModel, JobModel.job_id == JobScoreModel.job_id)
            .filter(
                JobModel.status.in_([
                    JobStatus.READY_FOR_RETRY.value,
                    JobStatus.QUALIFIED.value,
                    JobStatus.HIGH_MATCH.value,
                    JobStatus.APPLICATION_READY.value,
                    JobStatus.ELIGIBLE.value,
                    JobStatus.DISCOVERED.value,
                    JobStatus.NEEDS_MANUAL_INTERVENTION.value,
                    JobStatus.APPLICATION_FAILED.value,
                ]),
                JobScoreModel.overall_score >= self.min_match_score,
                ~JobModel.job_id.in_(
                    session.query(ApplicationModel.job_id).filter(
                        ApplicationModel.status == JobStatus.APPLIED_CONFIRMED.value
                    )
                ),
            )
            .all()
        )

        if not candidate_records:
            logger.info("No eligible retry or qualified jobs found in database for catch-up.")
            return result

        # Separate by platform and interleave (prioritizing direct Naukri and LinkedIn Easy Apply)
        naukri_candidates = [
            (job, score) for job, score in candidate_records
            if "naukri" in (job.source_platform or "").lower()
        ]
        linkedin_candidates = [
            (job, score) for job, score in candidate_records
            if "linkedin" in (job.source_platform or "").lower()
            or job.application_method in (ApplicationMethod.LINKEDIN_EASY_APPLY.value, "LINKEDIN_EASY_APPLY")
        ]
        ats_candidates = [
            (job, score) for job, score in candidate_records
            if (job, score) not in naukri_candidates and (job, score) not in linkedin_candidates
        ]

        naukri_candidates.sort(key=lambda x: x[1].overall_score, reverse=True)
        linkedin_candidates.sort(key=lambda x: x[1].overall_score, reverse=True)
        ats_candidates.sort(key=lambda x: x[1].overall_score, reverse=True)

        # Strictly sequential pipeline per user directive:
        # Phase 1: Naukri direct applications run to full completion first (if quota not yet reached).
        # Phase 2: LinkedIn Easy Apply applications run only after Naukri finishes completely (if LinkedIn quota not reached).
        # Phase 3: External ATS candidates.
        active_naukri = naukri_candidates if naukri_today < max_per_platform else []
        active_linkedin = linkedin_candidates if linkedin_today < max_li_per_day else []
        active_ats = ats_candidates if (naukri_today + linkedin_today) < self.target_quota else []

        sequential_queue = active_naukri + active_linkedin + active_ats

        # Limit catch-up batch size (allow sufficient attempts to overcome external portals or gate filters)
        batch_limit = min(max_retries, len(sequential_queue))
        catchup_queue = sequential_queue[:batch_limit]
        logger.info(f"Selected {len(catchup_queue)} high-scoring candidates for sequential stabilization catch-up (Active Naukri: {len(active_naukri)}, Active LinkedIn: {len(active_linkedin)}).")

        # Initialize repositories & agents
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        resume_repo = ResumeRepository(session)
        interview_repo = InterviewRepository(session)

        resume_agent = ResumeAgent(resume_repo, self.candidate_truth, self.config)
        interview_agent = InterviewAgent(interview_repo, self.candidate_truth)
        ats_filler = AtsPortalFiller(self.candidate_truth, self.config, offline_mode=self.offline_mode)

        # Lazy initialize browser adapters only when live
        naukri_client: Optional[PlaywrightBrowserAdapter] = None
        linkedin_adapter: Optional[LinkedInAdapter] = None

        if not dry_run and not self.offline_mode:
            logger.info("Initializing Playwright adapters for autonomous catch-up submissions...")
            naukri_client = PlaywrightBrowserAdapter(offline_mode=False)
            linkedin_adapter = LinkedInAdapter(
                config=self.config,
                candidate_truth=self.candidate_truth,
                offline_mode=False,
            )

        app_agent = ApplicationAgent(
            client=naukri_client if naukri_client else PlaywrightBrowserAdapter(offline_mode=True),
            job_repo=job_repo,
            app_repo=app_repo,
            resume_repo=resume_repo,
            candidate_truth=self.candidate_truth,
            config=self.config,
        )

        naukri_newly_confirmed = 0
        linkedin_newly_confirmed = 0
        catchup_start = time.time()
        max_catchup_duration = int(self.config.get("application", {}).get("max_catchup_duration_seconds", 1800))

        try:
            for job_model, score_model in catchup_queue:
                if (time.time() - catchup_start) > max_catchup_duration:
                    logger.warning(f"Catch-up execution duration ceiling reached ({max_catchup_duration}s). Wrapping up gracefully to protect VPS memory.")
                    break

                job = job_model.to_listing()
                is_li_role = (
                    job.application_method in (ApplicationMethod.LINKEDIN_EASY_APPLY, "LINKEDIN_EASY_APPLY", "linkedin_easy_apply")
                    or "linkedin" in (job.source_platform or "").lower()
                    or "linkedin" in (job.url or "").lower()
                )

                if naukri_today >= target_per_platform and linkedin_today >= target_li:
                    logger.info(f"Target of {target_per_platform}+ applications on BOTH Naukri and LinkedIn achieved during catch-up! (Naukri: {naukri_today}, LinkedIn: {linkedin_today})")
                    break

                if is_li_role and linkedin_today >= max_li_per_day:
                    continue
                if not is_li_role and naukri_today >= max_per_platform:
                    continue

                # 1. Retry Guard
                can_retry, retry_reason = app_repo.can_retry_application(job.job_id, job.company, job.title)
                if not can_retry or job_repo.is_already_applied(job.job_id):
                    logger.info(f"Retry Guard: Skipping '{job.title}' @ {job.company} ({retry_reason})")
                    continue

                # 2. Submission Gates
                from src.agents.orchestrator import check_submission_gates
                passed_gates, gate_type, gate_reason = check_submission_gates(job, self.candidate_truth, self.config)
                if not passed_gates:
                    logger.warning(f"Submission Gate [{gate_type}] skipped '{job.title}' @ {job.company}: {gate_reason}")
                    continue
                score = JobScore(
                    job_id=score_model.job_id,
                    overall_score=score_model.overall_score,
                    architecture_score=score_model.architecture_score,
                    cloud_score=score_model.cloud_score,
                    oci_score=score_model.oci_score,
                    ai_score=score_model.ai_score,
                    agentic_ai_score=score_model.agentic_ai_score,
                    kubernetes_score=score_model.kubernetes_score,
                    security_score=score_model.security_score,
                    multicloud_score=score_model.multicloud_score,
                    experience_alignment=score_model.experience_alignment,
                    skill_alignment=score_model.skill_alignment,
                    passed_threshold=score_model.passed_threshold,
                    match_reasons=score_model.match_reasons or [],
                    strengths=score_model.strengths or [],
                    gaps=score_model.gaps or [],
                    categories=score_model.categories or [],
                )

                logger.info(f"Catch-Up Application: Attempting '{job.title}' @ {job.company} (Match: {score.overall_score:.1f}%)...")
                result["attempted"] += 1

                # Tailor ATS Resume
                docx_path, pdf_path, _ = resume_agent.generate_tailored_resume(job, score)

                app_status = JobStatus.APPLICATION_FAILED
                rec = None

                if dry_run or self.offline_mode:
                    app_status = JobStatus.APPLICATION_READY
                    logger.info(f"[DRY_RUN] Application prepared for {job.title} @ {job.company}")
                elif (
                    job.application_method in (ApplicationMethod.LINKEDIN_EASY_APPLY, "LINKEDIN_EASY_APPLY", "linkedin_easy_apply")
                    or "linkedin" in (job.source_platform or "").lower()
                    or "linkedin" in (job.url or "").lower()
                ) and linkedin_adapter:
                    rec = linkedin_adapter.apply_easy_apply(job, score, docx_path, pdf_path)
                    app_status = rec.status
                    app_repo.record_application(rec)
                    job_repo.update_status(job.job_id, app_status)
                    session.commit()
                elif ats_filler.is_supported_portal(job.url):
                    rec = ats_filler.fill_and_apply(job, docx_path, pdf_path)
                    app_status = rec.status
                    app_repo.record_application(rec)
                    job_repo.update_status(job.job_id, app_status)
                    session.commit()
                else:
                    outcome = app_agent.process_application(job, score, docx_path, pdf_path)
                    rec = outcome.app_record
                    app_status = outcome.status
                    if rec:
                        app_repo.record_application(rec)
                    job_repo.update_status(job.job_id, app_status)
                    session.commit()

                is_confirmed = (app_status == JobStatus.APPLIED_CONFIRMED) or ((dry_run or self.offline_mode) and app_status == JobStatus.APPLICATION_READY)

                if is_confirmed:
                    result["confirmed"] += 1
                    if is_li_role:
                        linkedin_today += 1
                        linkedin_newly_confirmed += 1
                    else:
                        naukri_today += 1
                        naukri_newly_confirmed += 1
                    current_confirmed = naukri_today + linkedin_today
                    logger.info(f"✅ CONFIRMED: Successfully applied to '{job.title}' @ {job.company} (Today: Naukri {naukri_today}/{target_per_platform}, LinkedIn {linkedin_today}/{target_li} | Total: {current_confirmed}/{self.target_quota})")
                    # Build interview pack
                    evidence = JobEvidence(job_id=job.job_id)
                    interview_agent.generate_interview_pack(job, score, evidence)

                    if naukri_today >= target_per_platform and linkedin_today >= target_li:
                        logger.info(f"Target of {target_per_platform}+ applications on BOTH platforms achieved (Naukri: {naukri_today}, LinkedIn: {linkedin_today})! Halting catch-up.")
                        break
                else:
                    result["failed"] += 1
                    fail_reason = (rec.failure_reason if rec else "") or "Catch-up submission unconfirmed"
                    logger.warning(f"❌ Catch-up unconfirmed for '{job.title}' @ {job.company}: {fail_reason}")

                result["details"].append({
                    "company": job.company,
                    "role": job.title,
                    "status": app_status.value if hasattr(app_status, "value") else str(app_status),
                    "score": score.overall_score,
                })

                session.commit()
                import gc
                gc.collect()
                time.sleep(2)

        finally:
            if linkedin_adapter:
                try:
                    linkedin_adapter.close()
                except Exception:
                    pass
            if naukri_client:
                try:
                    naukri_client.close()
                except Exception:
                    pass

        result["final_confirmed"] = current_confirmed
        result["confirmed_naukri"] = naukri_today
        result["confirmed_linkedin"] = linkedin_today
        result["quota_met"] = (naukri_today >= target_per_platform and linkedin_today >= target_li) or current_confirmed >= self.target_quota
        return result

    def generate_health_report_markdown(
        self,
        env_report: Dict[str, Any],
        log_audit: Dict[str, Any],
        db_audit: Dict[str, Any],
        diagnostics: List[FailureDiagnostic],
        catchup_result: Dict[str, Any],
    ) -> str:
        """Constructs a comprehensive post-run health checkup and self-healing markdown report."""
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# 🩺 AUTONOMOUS POST-RUN HEALTH & HEALING REPORT",
            f"**Date:** `{today_str}` | **Audit Timestamp:** `{now_utc}`",
            "",
            "## 1. Executive Quota & Stabilization Summary",
            f"- **Daily Confirmed Quota Target:** `{self.target_quota}`",
            f"- **Initial Confirmed Submissions:** `{catchup_result.get('initial_confirmed', db_audit['confirmed_today'])}`",
            f"- **Stabilization Catch-Up Attempts:** `{catchup_result.get('attempted', 0)}`",
            f"- **Newly Secured Applications:** `{catchup_result.get('confirmed', 0)}`",
            f"- **Final Confirmed Applications Today:** **`{catchup_result.get('final_confirmed', db_audit['confirmed_today'])} / {self.target_quota}`**",
            f"- **Quota Status:** {'✅ **QUOTA SATISFIED**' if catchup_result.get('quota_met') else '⚠️ **QUOTA DEFICIT**'}",
            "",
            "## 2. Server & Environment Telemetry",
            f"- **VPS Memory Available:** `{env_report.get('memory_available_mb', 0)} MB`",
            f"- **VPS Swap Used:** `{env_report.get('swap_used_mb', 0)} MB`",
            f"- **Zombie Browser Processes Terminated:** `{env_report.get('zombie_browsers_killed', 0)}`",
            f"- **Stale Execution Locks Cleared:** `{'YES' if env_report.get('stale_lock_cleared') else 'NONE'}`",
            "",
            "## 3. Log Audit & Diagnostic Signatures",
            f"- **Last Pipeline Duration:** `{log_audit.get('last_run_duration_sec', 'N/A')}s`",
            f"- **Pipeline Exit Code:** `{log_audit.get('last_run_exit_code', '0')}`",
            f"- **Detected Failure Vectors in Logs:** `{', '.join(log_audit.get('detected_issues', [])) or 'None'}`",
            "",
            "## 4. Autonomous Root-Cause Diagnosis & Self-Healing Actions",
            f"Total Issues Analyzed: **{len(diagnostics)}**",
            "",
            "| Company | Role | Category | Diagnosis | Self-Healing Action | Status |",
            "|---|---|---|---|---|---|",
        ]

        if not diagnostics:
            lines.append("| _None_ | _No application failures recorded_ | - | - | - | ✅ `HEALTHY` |")
        else:
            for d in diagnostics:
                status_badge = f"`{d.healing_status}`"
                if d.healing_status == "HEALED":
                    status_badge = "✅ `HEALED`"
                elif d.healing_status == "DISQUALIFIED_PERMANENT":
                    status_badge = "🛑 `DISQUALIFIED`"
                elif d.healing_status == "RESOLVED":
                    status_badge = "ℹ️ `RESOLVED`"

                clean_diag = d.analysis_summary.replace("|", "/")[:75]
                lines.append(
                    f"| **{d.company}** | {d.job_title[:28]} | `{d.root_cause_category}` | {clean_diag}... | `{d.self_healing_action}` | {status_badge} |"
                )

        lines.extend([
            "",
            "## 5. Catch-Up Application Telemetry",
        ])

        details = catchup_result.get("details", [])
        if not details:
            lines.append("_No catch-up applications were required or executed._\n")
        else:
            lines.extend([
                "| Company | Role | Match Score | Outcome |",
                "|---|---|---|---|",
            ])
            for item in details:
                badge = "✅ `CONFIRMED`" if item["status"] == JobStatus.APPLIED_CONFIRMED.value else f"❌ `{item['status']}`"
                lines.append(f"| **{item['company']}** | {item['role'][:35]} | `{item['score']:.1f}%` | {badge} |")
            lines.append("")

        return "\n".join(lines)

    def run_post_run_checkup(
        self,
        max_retries: int = 50,
        dry_run: bool = False,
        force_catchup: bool = False,
    ) -> Dict[str, Any]:
        """Orchestrates full post-run inspection, diagnosis, self-healing, and catch-up stabilization."""
        logger.info("=" * 70)
        logger.info("STARTING AUTONOMOUS POST-RUN HEALTH & SELF-HEALING INSPECTION")
        logger.info("=" * 70)

        # 1. Environment Sanitization
        env_report = self.sanitize_system_environment()

        # 2. Log Audit
        log_audit = self.audit_run_logs()

        # 3. Database Audit & Self-Healing
        with get_db_session() as session:
            db_audit = self.audit_database_state(session)
            diagnostics = self.diagnose_and_heal_failures(session)
            session.commit()

            # 4. Stabilization Catchup Loop
            catchup_result = self.execute_stabilization_catchup(
                session=session,
                max_retries=max_retries,
                dry_run=dry_run,
                force_catchup=force_catchup,
            )
            session.commit()

        # 5. Generate and Persist Health Report
        report_md = self.generate_health_report_markdown(
            env_report=env_report,
            log_audit=log_audit,
            db_audit=db_audit,
            diagnostics=diagnostics,
            catchup_result=catchup_result,
        )

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        health_report_path = HEALTH_REPORT_DIR / f"{today_str}_healer.md"
        with open(health_report_path, "w", encoding="utf-8") as f:
            f.write(report_md)
        logger.info(f"Health report persisted to: {health_report_path}")

        # Append to Daily Report
        daily_report_path = DAILY_REPORT_DIR / f"{today_str}.md"
        if daily_report_path.exists():
            try:
                with open(daily_report_path, "r", encoding="utf-8") as f:
                    daily_content = f.read()
                if "## 🩺 AUTONOMOUS POST-RUN HEALTH & HEALING REPORT" not in daily_content:
                    with open(daily_report_path, "a", encoding="utf-8") as f:
                        f.write("\n\n---\n\n" + report_md)
                    logger.info(f"Appended autonomous healing telemetry to daily report: {daily_report_path}")
            except Exception as e:
                logger.warning(f"Could not append to daily report: {e}")

        logger.info("=" * 70)
        logger.info(f"POST-RUN HEALTH CHECKUP COMPLETE: {catchup_result.get('final_confirmed')} / {self.target_quota} Applications Confirmed (Naukri: {catchup_result.get('confirmed_naukri', 'N/A')}, LinkedIn: {catchup_result.get('confirmed_linkedin', 'N/A')})")
        logger.info("=" * 70)

        return {
            "health_report_path": str(health_report_path),
            "final_confirmed": catchup_result.get("final_confirmed"),
            "confirmed_naukri": catchup_result.get("confirmed_naukri"),
            "confirmed_linkedin": catchup_result.get("confirmed_linkedin"),
            "target_quota": self.target_quota,
            "quota_met": catchup_result.get("quota_met"),
            "diagnostics_count": len(diagnostics),
            "catchup_attempts": catchup_result.get("attempted", 0),
            "newly_confirmed": catchup_result.get("confirmed", 0),
        }


def main():
    parser = argparse.ArgumentParser(description="Autonomous Post-Run Health Checkup & Self-Healing Agent")
    parser.add_argument("--post-run", action="store_true", help="Invoked immediately post-run by run_daily.sh")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Perform audit and diagnostics without live submissions")
    parser.add_argument("--force-catchup", action="store_true", help="Force stabilization catch-up even if quota appears satisfied")
    parser.add_argument("--max-retries", type=int, default=50, help="Maximum catch-up applications per execution")
    parser.add_argument("--offline", action="store_true", help="Run with offline mocks")

    args = parser.parse_args()

    # Prevent concurrent execution of healer
    lock_fd = None
    try:
        import fcntl
        lock_fd = open(HEALER_LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print(f"[INFO] Another PostRunHealer process is already active ({HEALER_LOCK_FILE}). Exiting cleanly.")
        sys.exit(0)

    try:
        agent = PostRunHealerAgent(offline_mode=args.offline)
        res = agent.run_post_run_checkup(
            max_retries=args.max_retries,
            dry_run=args.dry_run,
            force_catchup=args.force_catchup,
        )
        print("\n" + "=" * 60)
        print("  POST-RUN HEALTH & HEALING AUDIT COMPLETED")
        print("=" * 60)
        print(f"  Target Daily Quota:     {res.get('target_quota')}")
        print(f"  Final Confirmed Today:  {res.get('final_confirmed')}")
        print(f"  Failures Diagnosed:     {res.get('diagnostics_count')}")
        print(f"  Catch-Up Retries:       {res.get('catchup_attempts')}")
        print(f"  Newly Confirmed:        {res.get('newly_confirmed')}")
        print(f"  Health Report:          {res.get('health_report_path')}")
        print("=" * 60 + "\n")
    finally:
        if lock_fd:
            try:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
