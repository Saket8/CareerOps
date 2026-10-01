"""Master Orchestrator coordinating all autonomous career agents and state machine."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

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
from src.email_service.smtp_mailer import SmtpMailer
from src.maintenance.retention_manager import RetentionManager
from candidate.profile_extractor import get_candidate_truth
from src.models.report import DailyReportData, TopApplicationItem
from src.models.job import JobStatus
from src.utils.logger import get_logger

logger = get_logger("orchestrator")


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

                # Record run start immediately
                run_repo.start_run(run_id=run_id, run_type="weekly" if force_weekly else "daily", dry_run=self.dry_run)
                session.commit()

                # Clients and Agents
                min_salary_floor = self.config.get("application", {}).get("min_salary_lpa", 30.0)
                naukri_client = PlaywrightBrowserAdapter(offline_mode=self.offline_mode, min_salary_lpa=min_salary_floor)
                discovery_agent = DiscoveryAgent(naukri_client, job_repo, self.config)
                qualification_agent = QualificationAgent(job_repo, self.candidate_truth, self.config)
                resume_agent = ResumeAgent(resume_repo, self.candidate_truth, self.config)
                application_agent = ApplicationAgent(
                    naukri_client, job_repo, app_repo, resume_repo, self.candidate_truth, self.config
                )
                interview_agent = InterviewAgent(interview_repo, self.candidate_truth)
                market_agent = MarketIntelligenceAgent(job_repo, market_repo, app_repo, self.candidate_truth)
                rep_cfg = self.config.get("reporting", {})
                daily_dir = Path(rep_cfg["daily_dir"]) if "daily_dir" in rep_cfg else Path("reports/daily")
                weekly_dir = Path(rep_cfg["weekly_dir"]) if "weekly_dir" in rep_cfg else Path("reports/weekly")
                reporting_agent = ReportingAgent(daily_dir=daily_dir, weekly_dir=weekly_dir)
                smtp_mailer = SmtpMailer(self.config)

                top_applications = []
                matched_items_for_briefing = []
                resumes_generated = 0
                confirmed_count = 0
                unverified_count = 0
                external_count = 0
                manual_count = 0
                interview_packs_generated = 0
                strong_matches = 0

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
                session.commit()

                # 2. QUALIFICATION & SCORING
                qualifying_jobs = []
                for job in disc_result.eligible_jobs:
                    score, evidence = qualification_agent.evaluate_job(job)

                    if score.overall_score >= qualification_agent.high_match_threshold:
                        strong_matches += 1

                    if score.passed_threshold:
                        qualifying_jobs.append((job, score, evidence))

                # Prioritize top-tier opportunities first
                qualifying_jobs.sort(key=lambda item: item[1].overall_score, reverse=True)
                qualified_jobs_count = len(qualifying_jobs)

                for job, score, evidence in qualifying_jobs:
                    # Pre-flight gate: strictly skip if already applied in DB
                    if job_repo.is_already_applied(job.job_id) or job_repo.has_applied_to_company_and_title(job.company, job.title):
                        logger.info(f"Pre-flight Gate: Candidate already applied to '{job.title}' @ {job.company}. Strictly skipping application attempt.")
                        continue

                    # Tailor ATS Resume (DOCX & PDF)
                    docx_path, pdf_path, val_report = resume_agent.generate_tailored_resume(job, score)
                    resumes_generated += 1

                    # Process Automated Application
                    outcome = application_agent.process_application(job, score, docx_path, pdf_path)
                    rec = outcome.app_record
                    status = outcome.status

                    # If skipped because already applied in previous session, do not count as new or include in report
                    if status == JobStatus.APPLIED or "already applied" in (outcome.reason or "").lower() or (rec and "already applied" in (rec.failure_reason or "").lower()):
                        logger.info(f"Job already applied in past session: '{job.title}' @ {job.company}. Excluded from today's report.")
                        continue

                    matched_items_for_briefing.append((job, score, evidence))

                    applications_attempted += 1
                    if status == JobStatus.APPLIED_CONFIRMED:
                        confirmed_count += 1
                    elif status == JobStatus.SUBMISSION_UNVERIFIED:
                        unverified_count += 1
                    elif status in (JobStatus.APPLICATION_BLOCKED, JobStatus.BLOCKED):
                        blocked_count += 1
                    elif status in (JobStatus.APPLICATION_FAILED, JobStatus.FAILED):
                        failed_count += 1
                    elif status == JobStatus.EXTERNAL_APPLICATION_REQUIRED:
                        external_count += 1
                    elif status == JobStatus.NEEDS_MANUAL_INTERVENTION:
                        manual_count += 1

                    # Top application item with full audit evidence
                    method = rec.application_method if rec else "Naukri Direct"
                    ref = rec.confirmation_reference if rec else None
                    portal_url = (rec.external_application_url if (rec and rec.external_application_url) else job.url)
                    top_applications.append(
                        TopApplicationItem(
                            company=job.company,
                            role=job.title,
                            salary=job.salary.raw_text or "Not Disclosed",
                            match_score=score.overall_score,
                            key_factors=score.strengths[:3],
                            resume_used=docx_path.name,
                            status=status.value,
                            url=portal_url,
                            method=method,
                            reason=rec.failure_reason if (rec and rec.failure_reason) else outcome.reason,
                            evidence_path=rec.evidence_path if rec else None,
                            confirmation_ref=ref,
                        )
                    )

                    # 4. INTERVIEW PREPARATION (For High Matches or Applied Roles)
                    if score.overall_score >= qualification_agent.high_match_threshold or score.architecture_score >= 85.0:
                        interview_agent.generate_interview_pack(job, score, evidence)
                        interview_packs_generated += 1

                    # Commit immediately after each application attempt to isolate transactions
                    session.commit()

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
                failed_count = len([a for a in top_applications if a.status in (JobStatus.APPLICATION_FAILED.value, JobStatus.FAILED.value)])
                external_count = len([a for a in top_applications if a.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value])
                manual_count = len([a for a in top_applications if a.status == JobStatus.NEEDS_MANUAL_INTERVENTION.value])

                total_scanned = disc_result.total_found if disc_result.total_found > 0 else len(top_applications)
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
