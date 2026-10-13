"""Master Orchestrator coordinating all autonomous career agents and state machine."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from src.database.models import ApplicationModel, JobModel
from src.database.connection import get_db_session, init_db
from src.database.repositories import (
    JobRepository,
    ApplicationRepository,
    ResumeRepository,
    InterviewRepository,
    MarketSignalRepository,
    RunRepository,
)
from src.naukri.browser_adapter import NaukriBrowserAdapter
from src.naukri.playwright_adapter import PlaywrightBrowserAdapter
from src.agents.discovery import DiscoveryAgent
from src.agents.qualification import QualificationAgent
from src.agents.resume_agent import ResumeAgent
from src.agents.application import ApplicationAgent
from src.agents.interview_agent import InterviewAgent
from src.agents.market_intelligence import MarketIntelligenceAgent
from src.agents.reporting import ReportingAgent
from src.agents.failure_analysis_agent import FailureAnalysisAgent
from src.email_service.smtp_mailer import SmtpMailer
from src.maintenance.retention_manager import RetentionManager
from candidate.profile_extractor import get_candidate_truth
from src.models.report import DailyReportData, TopApplicationItem, SourceBreakdownItem
from src.models.job import JobStatus, ApplicationMethod, JobListing
from src.models.candidate import CandidateTruth
from src.linkedin import LinkedInAdapter
from src.utils.logger import get_logger

logger = get_logger("orchestrator")


def record_missing_candidate_fact(
    job_id: str,
    company: str,
    title: str,
    missing_fact: str,
    reason: str,
    file_path: Path = Path("data/missing_candidate_facts.json"),
) -> None:
    """Records missing or contradictory candidate facts persistently to disk for future enhancements."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        facts = []
        if file_path.exists():
            import json
            try:
                facts = json.loads(file_path.read_text(encoding="utf-8"))
                if not isinstance(facts, list):
                    facts = []
            except Exception:
                facts = []
        facts.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "company": company,
            "title": title,
            "missing_fact": missing_fact,
            "reason": reason,
        })
        import json
        file_path.write_text(json.dumps(facts, indent=2), encoding="utf-8")
        logger.info(f"Recorded missing candidate fact: '{missing_fact}' ({company} - {title})")
    except Exception as err:
        logger.warning(f"Could not record missing candidate fact to disk: {err}")


def check_submission_gates(
    job: JobListing,
    candidate_truth: CandidateTruth,
    config: Dict[str, Any],
) -> Tuple[bool, str, Optional[str]]:
    """Evaluates salary, employer, location, experience, and candidate-truth gates automatically before submission."""
    # 1. Employer Safety Gate (Current Employer Blocklist)
    blocked = [c.lower().strip() for c in config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])]
    if any(b in job.company.lower() for b in blocked):
        return False, "BLOCKED_EMPLOYER", f"Current employer blocklist: {job.company}"

    # 2. Salary Gate (Minimum Acceptable Floor)
    sal_override = config.get("application", {}).get("min_salary_lpa")
    if sal_override is None:
        sal_override = candidate_truth.candidate.min_acceptable_salary_lpa or candidate_truth.candidate.current_salary_lpa or 30.0
    min_salary = float(sal_override)
    if job.salary and job.salary.is_disclosed and job.salary.max_lpa is not None:
        if job.salary.max_lpa < min_salary:
            return False, "SALARY_BELOW_MINIMUM", f"Salary ({job.salary.max_lpa} LPA) below threshold ({min_salary} LPA)"

    # 3. Location Gate (Preferred & International Relocation Target Alignment)
    job_loc = (job.location or "").lower()
    is_remote = any(m in job_loc or m in (job.work_mode or "").lower() for m in ["remote", "hybrid", "wfh"])
    if not is_remote and candidate_truth.candidate.willing_to_relocate:
        allowed_keywords = [
            "india", "noida", "gurgaon", "delhi", "bengaluru", "bangalore", "pune", "hyderabad",
            "mumbai", "chennai", "europe", "uk", "germany", "netherlands", "switzerland",
            "ireland", "sweden", "denmark", "norway", "finland", "australia", "zealand",
            "united states", "usa", "us", "canada", "singapore", "uae", "dubai"
        ]
        if not any(k in job_loc for k in allowed_keywords):
            return False, "LOCATION_MISMATCH", f"Location '{job.location}' outside target regions"

    # 4. Experience Gate (Profile Tenure Alignment)
    if job.experience_min is not None and job.experience_min > 15.0:
        return False, "EXPERIENCE_MISMATCH", f"Required experience ({job.experience_min} yrs) exceeds profile (12 yrs)"

    # 5. Candidate Truth Gate (Essential Identity Facts)
    cand = candidate_truth.candidate
    if not cand.name or not cand.email or not cand.phone:
        return False, "MISSING_CANDIDATE_FACT", "Essential identity facts (name/email/phone) missing from verified profile"

    return True, "PASSED", None


def get_source_label(job: JobListing, ats_filler_obj: Any = None) -> str:
    """Classifies job into canonical platform source: Naukri, LinkedIn, or ATS Portal."""
    if job.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY or "linkedin" in (job.source_platform or "").lower() or "linkedin" in (job.url or "").lower():
        return "LinkedIn"
    if (ats_filler_obj and ats_filler_obj.is_supported_portal(job.url)) or "ats" in (job.source_platform or "").lower() or "greenhouse" in (job.url or "").lower() or "lever" in (job.url or "").lower():
        return "ATS Portal"
    return "Naukri"


class Orchestrator:
    """Coordinates discovery, qualification, ATS resume tailoring, application, interview prep, and reporting."""

    def __init__(self, config: Dict[str, Any], offline_mode: bool = False):
        self.config = config
        self.offline_mode = offline_mode
        self.candidate_truth = get_candidate_truth()
        self.dry_run = bool(config.get("application", {}).get("dry_run", False))
        db_url = config.get("database", {}).get("db_url", "sqlite:///naukri_career_agent.sqlite")
        init_db(db_url)
        self.db_url = db_url

    def run_daily_pipeline(
        self,
        force_weekly: bool = False,
        force_interview: bool = False,
        query_limit: int = 25,
    ) -> DailyReportData:
        """Executes the full automated weekday pipeline."""
        start_time = datetime.now(timezone.utc)
        run_id = f"run_{start_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        date_str = start_time.strftime("%Y-%m-%d")

        logger.info(f"================ STARTING RUN {run_id} (DRY_RUN={self.dry_run}) ================")

        # Initialize tracking metrics for fault-tolerant telemetry
        jobs_scanned_count = 0
        salary_rejected_count = 0
        qualified_jobs_count = 0
        applications_attempted = 0
        blocked_count = 0
        failed_count = 0

        try:
            with get_db_session(self.db_url) as session:
                # Repositories
                job_repo = JobRepository(session)
                app_repo = ApplicationRepository(session)
                resume_repo = ResumeRepository(session)
                interview_repo = InterviewRepository(session)
                market_repo = MarketSignalRepository(session)
                run_repo = RunRepository(session)

                # Record run start immediately and compute baseline duration target
                run_repo.start_run(run_id=run_id, run_type="weekly" if force_weekly else "daily", dry_run=self.dry_run)
                session.commit()
                avg_duration_sec = run_repo.get_average_duration_seconds()
                logger.info(f"Historical average pipeline run duration: {avg_duration_sec:.1f}s")

                # Track measurable metrics by source platform
                source_counts = {
                    "Naukri": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
                    "LinkedIn": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
                    "ATS Portal": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
                }

                # Clients and Agents
                sal_floor_val = self.config.get("application", {}).get("min_salary_lpa")
                if sal_floor_val is None:
                    sal_floor_val = self.candidate_truth.candidate.min_acceptable_salary_lpa or self.candidate_truth.candidate.current_salary_lpa or 30.0
                min_salary_floor = float(sal_floor_val)
                naukri_client = PlaywrightBrowserAdapter(offline_mode=self.offline_mode, min_salary_lpa=min_salary_floor)
                discovery_agent = DiscoveryAgent(naukri_client, job_repo, self.config)
                qualification_agent = QualificationAgent(job_repo, self.candidate_truth, self.config)
                resume_agent = ResumeAgent(resume_repo, self.candidate_truth, self.config)
                application_agent = ApplicationAgent(
                    naukri_client, job_repo, app_repo, resume_repo, self.candidate_truth, self.config
                )
                li_cfg = self.config.get("linkedin", {})
                li_enabled = bool(li_cfg.get("enabled", True))
                linkedin_adapter = (
                    LinkedInAdapter(
                        config=self.config,
                        candidate_truth=self.candidate_truth,
                        offline_mode=self.offline_mode,
                    )
                    if li_enabled
                    else None
                )
                interview_agent = InterviewAgent(interview_repo, self.candidate_truth)
                market_agent = MarketIntelligenceAgent(job_repo, market_repo, app_repo, self.candidate_truth)

                # Advanced Executive & Automation Agents
                from src.agents.cover_letter_agent import CoverLetterAgent
                from src.agents.outreach_agent import OutreachAgent
                from src.agents.ats_filler import AtsPortalFiller
                from src.email_service.inbound_email_tracker import InboundEmailTracker

                cover_letter_agent = CoverLetterAgent(self.candidate_truth, self.config)
                outreach_agent = OutreachAgent(self.candidate_truth, self.config)
                ats_filler = AtsPortalFiller(self.candidate_truth, self.config, offline_mode=self.offline_mode)
                inbound_tracker = InboundEmailTracker(self.config)

                rep_cfg = self.config.get("reporting", {})
                daily_dir = Path(rep_cfg["daily_dir"]) if "daily_dir" in rep_cfg else Path("reports/daily")
                weekly_dir = Path(rep_cfg["weekly_dir"]) if "weekly_dir" in rep_cfg else Path("reports/weekly")
                reporting_agent = ReportingAgent(daily_dir=daily_dir, weekly_dir=weekly_dir)
                smtp_mailer = SmtpMailer(self.config)

                from src.utils.telegram_notifier import TelegramNotifier
                telegram_notifier = TelegramNotifier(self.config)

                top_applications = []
                matched_items_for_briefing = []
                resumes_generated = 0
                confirmed_count = 0
                unverified_count = 0
                external_count = 0
                manual_count = 0
                interview_packs_generated = 0
                strong_matches = 0
                drafts_dispatched_telegram = 0

                # 0. PROFILE RESUME REFRESH (Re-upload master CV on weekday morning run to maintain Resdex rank)
                profile_refresh_status = None
                if not self.dry_run and not self.offline_mode and self.config.get("resume", {}).get("reupload_daily", True):
                    try:
                        master_cv_path = self.config.get("resume", {}).get("source_path", "resumes/master/Saket_Saurav_OCI.docx")
                        logger.info(f"Executing daily profile CV re-upload to refresh Naukri Resdex freshness: {master_cv_path}")
                        refresh_res = naukri_client.refresh_profile_resume(master_cv_path)
                        if refresh_res.get("success"):
                            profile_refresh_status = f"SUCCESS ({refresh_res.get('file', 'CV Re-uploaded')})"
                            logger.info(f"Naukri profile CV refresh successful: {profile_refresh_status}")
                        else:
                            profile_refresh_status = f"FAILED: {refresh_res.get('error', 'Unknown error')}"
                            logger.warning(f"Naukri profile CV refresh warning: {profile_refresh_status}")
                    except Exception as p_err:
                        profile_refresh_status = f"ERROR: {p_err}"
                        logger.warning(f"Non-fatal exception during profile CV refresh: {p_err}")

                # 1. DISCOVERY & EARLY SALARY FILTERING
                disc_result = discovery_agent.run_discovery(query_limit=query_limit)
                jobs_scanned_count = disc_result.total_found
                salary_rejected_count = disc_result.salary_rejected
                source_counts["Naukri"]["discovered"] += disc_result.total_found
                session.commit()

                # 1b. LINKEDIN INTERNATIONAL DISCOVERY (Europe, Nordics, Australia, US, India)
                li_discovered_jobs = []
                if linkedin_adapter:
                    try:
                        logger.info("Executing LinkedIn international Easy Apply discovery across target regions (Europe, Nordics, Australia, US, India)...")
                        li_limit = min(query_limit, 10)
                        li_discovered_jobs = linkedin_adapter.discover_jobs(limit_per_query=li_limit)
                        jobs_scanned_count += len(li_discovered_jobs)
                        source_counts["LinkedIn"]["discovered"] += len(li_discovered_jobs)
                        for lj in li_discovered_jobs:
                            job_repo.save_job(lj)
                        session.commit()
                    except Exception as li_err:
                        logger.error(f"LinkedIn discovery error: {li_err}")

                # 1c. DIRECT ATS PORTAL DISCOVERY (Greenhouse, Lever)
                ats_discovered_jobs = []
                try:
                    logger.info("Discovering direct Greenhouse and Lever ATS opportunities...")
                    ats_discovered_jobs = discovery_agent.discover_ats_portal_jobs(limit=5)
                    jobs_scanned_count += len(ats_discovered_jobs)
                    source_counts["ATS Portal"]["discovered"] += len(ats_discovered_jobs)
                    for aj in ats_discovered_jobs:
                        job_repo.save_job(aj)
                    session.commit()
                except Exception as ats_err:
                    logger.warning(f"ATS portal discovery note: {ats_err}")

                # 2. QUALIFICATION & SCORING
                eligible_jobs_pool = list(disc_result.eligible_jobs) + li_discovered_jobs + ats_discovered_jobs
                qualifying_jobs = []
                for job in eligible_jobs_pool:
                    score, evidence = qualification_agent.evaluate_job(job)

                    if score.overall_score >= qualification_agent.high_match_threshold:
                        strong_matches += 1

                    if score.passed_threshold:
                        qualifying_jobs.append((job, score, evidence))
                        src_name = get_source_label(job, ats_filler)
                        source_counts[src_name]["qualified"] += 1

                # Prioritize top-tier opportunities first
                qualifying_jobs.sort(key=lambda item: item[1].overall_score, reverse=True)
                qualified_jobs_count = len(qualifying_jobs)

                # Read run limit guards from configuration
                app_cfg = self.config.get("application", {})
                max_apps_per_day = int(app_cfg.get("max_applications_per_day", 25))
                max_duration_sec = float(app_cfg.get("max_run_duration_seconds", 3600))  # Default 60 min ceiling

                for job, score, evidence in qualifying_jobs:
                    # Enforce daily application ceiling
                    if applications_attempted >= max_apps_per_day:
                        logger.info(
                            f"Daily application cap reached ({applications_attempted}/{max_apps_per_day}). "
                            "Halting further submissions for this run to prevent overload."
                        )
                        break

                    # Enforce pipeline duration ceiling (time limit guard)
                    elapsed_now = (datetime.now(timezone.utc) - start_time).total_seconds()
                    if elapsed_now >= max_duration_sec:
                        logger.warning(
                            f"Execution time limit reached ({elapsed_now:.0f}s >= {max_duration_sec:.0f}s). "
                            "Gracefully wrapping up run to prevent lingering processes."
                        )
                        break

                    src_name = get_source_label(job, ats_filler)

                    # 1. Careful Status & Retry Rules: audit history before retrying an ambiguous submission to avoid duplicates
                    can_retry, retry_reason = app_repo.can_retry_application(job.job_id, job.company, job.title)
                    if not can_retry or job_repo.is_already_applied(job.job_id):
                        logger.info(f"Retry Guard: Skipping '{job.title}' @ {job.company} ({retry_reason})")
                        source_counts[src_name]["skipped"] += 1
                        continue

                    # 2. Automated Submission Gates (salary, employer, location, experience, candidate-truth)
                    passed_gates, gate_type, gate_reason = check_submission_gates(job, self.candidate_truth, self.config)
                    if not passed_gates:
                        logger.warning(f"Submission Gate [{gate_type}] halted '{job.title}' @ {job.company}: {gate_reason}")
                        if gate_type == "MISSING_CANDIDATE_FACT":
                            record_missing_candidate_fact(job.job_id, job.company, job.title, gate_reason, "Submission halted on missing candidate truth fact")
                            job_repo.update_status(job.job_id, JobStatus.NEEDS_DATA)
                            session.commit()
                        source_counts[src_name]["skipped"] += 1
                        continue

                    # Tailor ATS Resume (DOCX & PDF)
                    docx_path, pdf_path, val_report = resume_agent.generate_tailored_resume(job, score)
                    resumes_generated += 1

                    # Generate Executive Cover Letter & Recruiter Outreach Draft for High-Matches (>= 80%) or International roles
                    cover_letter_doc = None
                    cl_pdf_path = None
                    outreach_draft = None
                    try:
                        if score.overall_score >= 80.0:
                            cl_docx, cl_pdf = cover_letter_agent.generate_cover_letter(job, score)
                            cl_pdf_path = cl_pdf if cl_pdf.exists() else cl_docx
                            cover_letter_doc = str(cl_pdf_path)

                            # Strategy 1: Discover specific recruiter/hiring lead on LinkedIn
                            recruiter_lead = None
                            if linkedin_adapter:
                                try:
                                    recruiter_lead = linkedin_adapter.find_recruiter_lead(job.company, job.title)
                                except Exception as rl_err:
                                    logger.debug(f"Recruiter lead discovery note: {rl_err}")

                            outreach_draft = outreach_agent.draft_outreach(job, score, recruiter_lead=recruiter_lead)
                            if outreach_draft:
                                # Dispatch draft to Telegram channel ONLY for high-value recruiter one-to-one message drafts with direct link
                                tg_cfg = self.config.get("telegram", {})
                                min_draft_score = float(tg_cfg.get("min_match_score_for_draft", 85.0))
                                max_draft_alerts = int(tg_cfg.get("max_draft_alerts_per_run", 5))

                                if score.overall_score >= min_draft_score and drafts_dispatched_telegram < max_draft_alerts:
                                    try:
                                        sent_tg = telegram_notifier.notify_recruiter_draft(
                                            company=job.company,
                                            role=job.title,
                                            contact_source=outreach_draft.hiring_lead_target or "Talent Acquisition",
                                            job_url=job.url,
                                            match_rationale=", ".join(score.strengths[:3]) if score.strengths else "High architectural alignment",
                                            pitch=outreach_draft.inmail_message,
                                            inmail_url=outreach_draft.linkedin_search_url,
                                        )
                                        if sent_tg:
                                            drafts_dispatched_telegram += 1
                                    except Exception as tg_draft_err:
                                        logger.debug(f"Telegram draft notification note: {tg_draft_err}")
                    except Exception as cl_err:
                        logger.warning(f"Cover letter / outreach drafting note: {cl_err}")

                    # Process Automated Application (Naukri Direct, LinkedIn Easy Apply, or Greenhouse/Lever ATS)
                    applications_attempted += 1
                    source_counts[src_name]["attempted"] += 1

                    if job.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY and linkedin_adapter:
                        rec = linkedin_adapter.apply_easy_apply(job, score, docx_path, pdf_path, cover_letter_path=cl_pdf_path)
                        status = rec.status
                        outcome_reason = rec.failure_reason
                        app_repo.record_application(rec)
                        job_repo.update_status(job.job_id, status)
                        session.commit()
                    elif ats_filler.is_supported_portal(job.url):
                        logger.info(f"Detected supported Greenhouse/Lever board for {job.title} @ {job.company}. Invoking AtsPortalFiller...")
                        rec = ats_filler.fill_and_apply(job, docx_path, pdf_path)
                        status = rec.status
                        outcome_reason = rec.failure_reason
                        app_repo.record_application(rec)
                        job_repo.update_status(job.job_id, status)
                        session.commit()
                    else:
                        outcome = application_agent.process_application(job, score, docx_path, pdf_path)
                        rec = outcome.app_record
                        status = outcome.status
                        outcome_reason = outcome.reason

                    # Save outreach draft into database for human review (never auto-sent)
                    if outreach_draft and rec:
                        try:
                            draft_payload = {
                                "job_id": job.job_id,
                                "company": job.company,
                                "role": job.title,
                                "contact_target": outreach_draft.hiring_lead_target,
                                "job_url": job.url,
                                "linkedin_search_url": outreach_draft.linkedin_search_url,
                                "subject": outreach_draft.subject,
                                "inmail_message": outreach_draft.inmail_message,
                                "cold_email_message": outreach_draft.cold_email_message,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "status": "SAVED_FOR_REVIEW_NOT_SENT",
                            }
                            app_repo.save_outreach_draft(rec.application_id, draft_payload)
                        except Exception as draft_save_err:
                            logger.debug(f"Outreach draft persistence note: {draft_save_err}")

                    # If skipped because already applied in previous session, do not count as new or include in report
                    if status == JobStatus.APPLIED or "already applied" in (outcome_reason or "").lower() or (rec and "already applied" in (rec.failure_reason or "").lower()):
                        logger.info(f"Job already applied in past session: '{job.title}' @ {job.company}. Excluded from today's report.")
                        source_counts[src_name]["skipped"] += 1
                        continue

                    matched_items_for_briefing.append((job, score, evidence))

                    if status == JobStatus.APPLIED_CONFIRMED:
                        confirmed_count += 1
                        source_counts[src_name]["confirmed"] += 1
                        try:
                            telegram_notifier.notify_application_submitted(
                                company=job.company,
                                role=job.title,
                                location=job.location,
                                platform=method if 'method' in locals() else job.source_platform.capitalize(),
                                match_score=score.overall_score,
                                confirmation_ref=rec.confirmation_reference if rec else None,
                                job_url=job.url,
                                cover_letter=bool(cover_letter_doc),
                            )
                        except Exception as tg_err:
                            logger.debug(f"Telegram notification note: {tg_err}")
                    elif status == JobStatus.SUBMISSION_UNVERIFIED:
                        unverified_count += 1
                        source_counts[src_name]["failed"] += 1
                    elif status in (JobStatus.APPLICATION_BLOCKED, JobStatus.BLOCKED):
                        blocked_count += 1
                        source_counts[src_name]["failed"] += 1
                    elif status in (JobStatus.APPLICATION_FAILED, JobStatus.FAILED):
                        failed_count += 1
                        source_counts[src_name]["failed"] += 1
                    elif status == JobStatus.EXTERNAL_APPLICATION_REQUIRED:
                        external_count += 1
                    elif status == JobStatus.NEEDS_MANUAL_INTERVENTION:
                        manual_count += 1
                        source_counts[src_name]["failed"] += 1

                    # Top application item with full audit evidence and executive collateral
                    if rec:
                        method = rec.application_method
                    elif job.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY:
                        method = "LinkedIn Easy Apply"
                    elif ats_filler.is_supported_portal(job.url):
                        method = "Greenhouse/Lever ATS"
                    else:
                        method = "Naukri Direct"
                    ref = rec.confirmation_reference if rec else None
                    portal_url = (rec.external_application_url if (rec and rec.external_application_url) else job.url)
                    # Compute market compensation intelligence estimation if undisclosed
                    from src.utils.compensation_intelligence import CompensationIntelligence
                    comp_est = CompensationIntelligence.estimate_compensation(job)
                    salary_display = (
                        job.salary.raw_text
                        if (job.salary and job.salary.is_disclosed and job.salary.raw_text and "not disclosed" not in job.salary.raw_text.lower())
                        else (comp_est.formatted_band if comp_est else "Not Disclosed")
                    )

                    top_applications.append(
                        TopApplicationItem(
                            company=job.company,
                            role=job.title,
                            salary=salary_display,
                            match_score=score.overall_score,
                            key_factors=score.strengths[:3],
                            resume_used=docx_path.name,
                            status=status.value,
                            url=portal_url,
                            method=method,
                            reason=rec.failure_reason if (rec and rec.failure_reason) else outcome_reason,
                            evidence_path=rec.evidence_path if rec else None,
                            confirmation_ref=ref,
                            cover_letter_path=cover_letter_doc,
                            outreach_target=outreach_draft.hiring_lead_target if outreach_draft else None,
                            outreach_inmail=outreach_draft.inmail_message if outreach_draft else None,
                            outreach_search_url=outreach_draft.linkedin_search_url if outreach_draft else None,
                        )
                    )

                    # 4. INTERVIEW PREPARATION (For High Matches or Applied Roles)
                    if score.overall_score >= qualification_agent.high_match_threshold or score.architecture_score >= 85.0:
                        interview_agent.generate_interview_pack(job, score, evidence)
                        interview_packs_generated += 1

                    # Commit immediately after each application attempt to isolate transactions
                    session.commit()

                # 3b. Autonomous Failure Analysis & Self-Healing Agent
                try:
                    failure_agent = FailureAnalysisAgent(session, self.candidate_truth, self.config)
                    failure_diagnostics = failure_agent.analyze_and_heal_run(run_id=run_id)
                    logger.info(f"Self-healing complete. Diagnosed and resolved {len(failure_diagnostics)} application cases.")

                    # Map diagnostics to top_applications so report reflects true filter rejections
                    diag_map = {d.job_id: d for d in failure_diagnostics}
                    for item in top_applications:
                        matched_diag = None
                        for jid, d in diag_map.items():
                            if d.company.lower() == item.company.lower() and d.job_title.lower() == item.role.lower():
                                matched_diag = d
                                break
                        if matched_diag:
                            if matched_diag.root_cause_category in ("DIVERSITY_PROGRAM_RESTRICTION", "EXPERIENCE_THRESHOLD_RESTRICTION"):
                                item.status = "DISQUALIFIED_BY_SCREENING"
                                item.reason = matched_diag.analysis_summary
                            elif matched_diag.root_cause_category == "LOCATION_SYNONYM_MISMATCH":
                                item.status = "READY_FOR_RETRY"
                                item.reason = "Location synonym learned; queued for autonomous retry."

                    session.commit()
                except Exception as fa_err:
                    logger.error(f"Failure analysis and self-healing error: {fa_err}")

                # 3c. Inbound Recruiter Email & Interview Invitation Scan
                try:
                    if not self.offline_mode:
                        inbound_msgs = inbound_tracker.scan_inbox(max_messages=20)
                        if inbound_msgs:
                            logger.info(f"Inbound Email Tracker detected {len(inbound_msgs)} recruiter messages.")
                            for rmsg in inbound_msgs:
                                if rmsg.category == "INTERVIEW":
                                    telegram_notifier.notify_interview_invite(
                                        sender=rmsg.sender,
                                        subject=rmsg.subject,
                                        company=rmsg.matched_company,
                                        snippet=rmsg.snippet,
                                    )
                except Exception as inb_err:
                    logger.debug(f"Inbound email scan note: {inb_err}")

                # Check if Friday (weekday 4 in python 0=Mon, 4=Fri) or forced weekly run
                is_friday = start_time.weekday() == 4 or force_weekly
                weekly_html_content = ""
                weekly_week_number = ""
                if is_friday:
                    logger.info("Friday detected: Executing Weekly Career Intelligence synthesis...")
                    weekly_data = market_agent.generate_weekly_intelligence()
                    w_md, w_html, weekly_html_content = reporting_agent.generate_weekly_report(weekly_data)
                    weekly_week_number = weekly_data.week_number

                # 5. DAILY REPORTING & EMAIL NOTIFICATION (Run-Scoped; Zero Duplicate Backfill)
                end_time = datetime.now(timezone.utc)

                # Summary counts strictly computed from current run's processed items
                confirmed_count = len([a for a in top_applications if a.status == JobStatus.APPLIED_CONFIRMED.value])
                unverified_count = len([a for a in top_applications if a.status == JobStatus.SUBMISSION_UNVERIFIED.value])
                blocked_count = len([a for a in top_applications if a.status in (JobStatus.APPLICATION_BLOCKED.value, JobStatus.BLOCKED.value)])
                failed_count = len([a for a in top_applications if a.status in (JobStatus.APPLICATION_FAILED.value, JobStatus.FAILED.value) and a.status != "DISQUALIFIED_BY_SCREENING"])
                external_count = len([a for a in top_applications if a.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value])
                manual_count = len([a for a in top_applications if a.status == JobStatus.NEEDS_MANUAL_INTERVENTION.value and a.status != "READY_FOR_RETRY"])

                total_scanned = disc_result.total_found if disc_result.total_found > 0 else len(top_applications)
                source_breakdown = [
                    SourceBreakdownItem(
                        source=src,
                        discovered=counts["discovered"],
                        qualified=counts["qualified"],
                        attempted=counts["attempted"],
                        confirmed=counts["confirmed"],
                        skipped=counts["skipped"],
                        failed=counts["failed"],
                    )
                    for src, counts in source_counts.items()
                ]

                daily_data = DailyReportData(
                    run_id=run_id,
                    date=date_str,
                    start_time=start_time,
                    end_time=end_time,
                    dry_run=self.dry_run,
                    jobs_scanned=total_scanned,
                    salary_rejected=disc_result.salary_rejected,
                    qualified_jobs=len([j for j in disc_result.eligible_jobs if j.status in (JobStatus.QUALIFIED, JobStatus.HIGH_MATCH, JobStatus.APPLIED, JobStatus.APPLIED_CONFIRMED, JobStatus.APPLICATION_READY)]) or len(top_applications),
                    strong_matches=strong_matches or len(top_applications),
                    resumes_generated=resumes_generated or len(top_applications),
                    applications_submitted=applications_attempted or len(top_applications),
                    applications_confirmed=confirmed_count,
                    applications_unverified=unverified_count,
                    applications_external=external_count,
                    applications_manual_intervention=manual_count,
                    blocked_applications=blocked_count,
                    failed_applications=failed_count,
                    interview_packs_generated=interview_packs_generated,
                    profile_refresh_status=profile_refresh_status,
                    top_applications=top_applications,
                    source_breakdown=source_breakdown,
                )

                d_md, d_html, d_html_content = reporting_agent.generate_daily_report(daily_data)

                # Prepare Consolidated Interview Intelligence Dossier (WEEKLY cycle on Friday or when forced)
                should_send_interview = force_interview or is_friday

                # Strict zero-dummy filter on matched items
                import re
                matched_items_for_briefing = [
                    item for item in matched_items_for_briefing
                    if re.match(r"^\d+$", str(item[0].job_id)) and not ("job_oci_" in item[0].url or "nk_" in item[0].url)
                ]

                # Backfill for weekly interview briefing if scheduled/forced but no new applies in current single run
                if should_send_interview and not matched_items_for_briefing:
                    recent_applied = job_repo.get_jobs_by_status(JobStatus.APPLIED_CONFIRMED)
                    if not recent_applied:
                        recent_applied = [j for j in job_repo.get_jobs_by_status(JobStatus.APPLIED) if re.match(r"^\d+$", str(j.job_id))]
                    for r_job in recent_applied[:15]:
                        if not re.match(r"^\d+$", str(r_job.job_id)) or "job_oci_" in r_job.url or "nk_" in r_job.url:
                            continue
                        listing = r_job.to_listing() if hasattr(r_job, "to_listing") else r_job
                        r_score, r_evidence = qualification_agent.evaluate_job(listing)
                        matched_items_for_briefing.append((listing, r_score, r_evidence))

                interview_attachments = []
                interview_html_snippet = ""
                if should_send_interview and matched_items_for_briefing:
                    logger.info("Generating Weekly Consolidated Interview Intelligence Dossier...")
                    i_docx, i_pdf, i_html_content = interview_agent.generate_consolidated_daily_briefing(
                        matched_items_for_briefing, date_str
                    )
                    if i_pdf.exists():
                        interview_attachments.append(i_pdf)
                    if i_docx.exists():
                        interview_attachments.append(i_docx)
                    interview_html_snippet = f"""
                    <div style="background:#f0fdf4;padding:20px;border-radius:8px;border:1px solid #bbf7d0;margin-top:24px;">
                        <h3 style="color:#166534;margin-top:0;">🎯 Weekly Interview Intelligence Dossier Attached</h3>
                        <p style="color:#15803d;margin-bottom:8px;">
                            Attached to this email are the consolidated candidate interview briefing packages in PDF and DOCX format:
                        </p>
                        <ul style="color:#166534;margin-bottom:0;">
                            <li><strong>{i_pdf.name}</strong> — Print-ready executive dossier</li>
                            <li><strong>{i_docx.name}</strong> — Editable reference documentation</li>
                        </ul>
                    </div>
                    """

                # Email Deduplication & Uniqueness Guard
                has_actionable_applications = any(
                    a.status in (JobStatus.APPLIED_CONFIRMED.value, JobStatus.EXTERNAL_APPLICATION_REQUIRED.value)
                    for a in top_applications
                )

                # Check email dispatch history checkpoint file to guarantee uniqueness
                dispatch_history_path = Path("artifacts/dispatched_emails.json")
                dispatched_records = []
                if dispatch_history_path.exists():
                    try:
                        import json
                        dispatched_records = json.loads(dispatch_history_path.read_text(encoding="utf-8"))
                        if not isinstance(dispatched_records, list):
                            dispatched_records = []
                    except Exception as json_err:
                        logger.warning(f"Could not load dispatched email history: {json_err}")
                        dispatched_records = []

                # Current run's application signatures
                current_job_urls = sorted([a.url for a in top_applications if a.url])

                # Check if an identical set of applications was already emailed today
                is_duplicate_email = False
                for rec in dispatched_records:
                    if rec.get("date") == date_str:
                        rec_urls = sorted(rec.get("job_urls", []))
                        if rec_urls and rec_urls == current_job_urls:
                            is_duplicate_email = True
                            break

                should_send_email = True
                if self.offline_mode:
                    should_send_email = False
                    logger.info("Offline mode: Skipping email delivery.")
                elif is_duplicate_email:
                    should_send_email = False
                    logger.warning(
                        f"Email suppressed: An identical report for these {len(current_job_urls)} applications "
                        f"was already delivered on {date_str}. Suppressing duplicate email."
                    )
                elif not has_actionable_applications and not (is_friday and weekly_html_content):
                    should_send_email = False
                    logger.info(
                        "Email suppressed: Zero new confirmed or external applications in this run. "
                        "Skipping email to ensure candidate inbox receives only unique application notifications."
                    )

                if should_send_email:
                    if is_friday:
                        report_subject = f"CareerOps — Daily Application & Weekly Intelligence Report — {date_str}"
                    else:
                        report_subject = f"CareerOps — Daily Application Report — {date_str}"

                    if self.dry_run:
                        report_subject = f"[DRY RUN] {report_subject}"

                    # Compose unified single HTML body
                    combined_html_parts = [d_html_content]
                    if interview_html_snippet:
                        combined_html_parts.append(interview_html_snippet)
                    if is_friday and weekly_html_content:
                        combined_html_parts.append(f"""
                        <hr style="border:0;border-top:2px solid #e2e8f0;margin:40px 0 20px 0;" />
                        <div style="background:#f8fafc;padding:24px;border-radius:12px;border:1px solid #cbd5e1;margin-top:24px;">
                            <h2 style="color:#0f172a;margin-top:0;font-size:20px;">📊 Career Agent — Weekly Career Intelligence ({weekly_week_number})</h2>
                            {weekly_html_content}
                        </div>
                        """)
                    final_html_body = "\n".join(combined_html_parts)

                    smtp_mailer.send_report(
                        subject=report_subject,
                        html_body=final_html_body,
                        attachments=interview_attachments,
                    )

                    # Record dispatch to guarantee deduplication
                    try:
                        import json
                        dispatched_records.append({
                            "run_id": run_id,
                            "date": date_str,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "job_urls": current_job_urls,
                            "applications_count": confirmed_count,
                            "subject": report_subject,
                        })
                        dispatch_history_path.parent.mkdir(parents=True, exist_ok=True)
                        dispatch_history_path.write_text(
                            json.dumps(dispatched_records[-60:], indent=2), encoding="utf-8"
                        )
                        logger.info(f"Recorded email dispatch checkpoint for run {run_id} to {dispatch_history_path}.")
                    except Exception as hist_err:
                        logger.warning(f"Could not record email dispatch history: {hist_err}")

                # Push daily executive pipeline summary to Telegram with source breakdown
                try:
                    telegram_notifier.notify_daily_summary(
                        date_str=date_str,
                        confirmed_count=confirmed_count,
                        qualified_count=daily_data.qualified_jobs,
                        scanned_count=daily_data.jobs_scanned,
                        dry_run=self.dry_run,
                        source_summary={item.source: item.confirmed for item in source_breakdown},
                    )
                except Exception as tg_err:
                    logger.warning(f"Could not send Telegram daily summary: {tg_err}")

                # Check if observed duration missed historical baseline and notify if delayed
                actual_duration = (end_time - start_time).total_seconds()
                if actual_duration > (avg_duration_sec * 1.5) and actual_duration > 600:
                    try:
                        telegram_notifier.notify_run_delay_or_failure(
                            run_id=run_id,
                            status="DELAYED",
                            elapsed_seconds=actual_duration,
                            target_seconds=avg_duration_sec,
                        )
                    except Exception as tg_delay_err:
                        logger.warning(f"Could not send Telegram run delay alert: {tg_delay_err}")

                # Record run finish in DB
                run_repo.finish_run(
                    run_id=run_id,
                    status="SUCCESS",
                    jobs_scanned=daily_data.jobs_scanned,
                    salary_rejected=daily_data.salary_rejected,
                    qualified_jobs=daily_data.qualified_jobs,
                    applications_submitted=daily_data.applications_submitted,
                    blocked_count=blocked_count,
                    failed_count=failed_count,
                )

        except Exception as exc:
            logger.error(f"Pipeline failure in run {run_id}: {exc}", exc_info=True)
            # Push instant failure notice via Telegram
            try:
                telegram_notifier.notify_run_delay_or_failure(
                    run_id=run_id,
                    status="FAILED",
                    error_msg=str(exc),
                    elapsed_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                    target_seconds=avg_duration_sec if 'avg_duration_sec' in locals() else 900.0,
                )
            except Exception:
                pass

            try:
                with get_db_session(self.db_url) as err_session:
                    err_run_repo = RunRepository(err_session)
                    err_run_repo.finish_run(
                        run_id=run_id,
                        status="FAILED",
                        jobs_scanned=jobs_scanned_count,
                        salary_rejected=salary_rejected_count,
                        qualified_jobs=qualified_jobs_count,
                        applications_submitted=applications_attempted,
                        blocked_count=blocked_count,
                        failed_count=failed_count + 1,
                    )
            except Exception as finish_err:
                logger.warning(f"Could not record FAILED status for run {run_id}: {finish_err}")
            raise
        finally:
            # 6. RETENTION CLEANUP (Purge stale unapplied data, old logs, compact DB outside main session)
            try:
                retention_mgr = RetentionManager(self.config)
                retention_mgr.apply_retention_policy(dry_run=self.dry_run)
            except Exception as ret_err:
                logger.warning(f"Retention policy cleanup warning: {ret_err}")

        logger.info(f"================ COMPLETED RUN {run_id} ================")
        return daily_data
