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
                if is_friday:
                    logger.info("Friday detected: Executing Weekly Career Intelligence synthesis...")
                    weekly_data = market_agent.generate_weekly_intelligence()
                    w_md, w_html, w_html_content = reporting_agent.generate_weekly_report(weekly_data)
                    smtp_mailer.send_report(
                        subject=f"Career Agent — Weekly Career Intelligence — {weekly_data.week_number}",
                        html_body=w_html_content,
                    )

                # 5. DAILY REPORTING & EMAIL NOTIFICATION (Today's Cumulative Scope; Zero Yesterday/Historical Backfill)
                end_time = datetime.now(timezone.utc)

                # Aggregate all applications submitted or recorded TODAY (date == date_str) to provide a true Daily Report
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                seen_job_titles = {f"{a.company.lower()}::{a.role.lower()}" for a in top_applications}
                seen_urls = {a.url for a in top_applications if a.url}

                today_apps_query = (
                    session.query(ApplicationModel, JobModel)
                    .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
                    .filter(
                        (ApplicationModel.submitted_at >= today_start) | (ApplicationModel.started_at >= today_start),
                        ApplicationModel.status.in_([
                            JobStatus.APPLIED_CONFIRMED.value,
                            JobStatus.EXTERNAL_APPLICATION_REQUIRED.value,
                        ]),
                    )
                    .order_by(ApplicationModel.submitted_at.desc())
                    .all()
                )

                for app_m, job_m in today_apps_query:
                    job_key = f"{job_m.company.lower()}::{job_m.title.lower()}"
                    portal_url = app_m.external_application_url or job_m.canonical_url or job_m.url
                    if job_key in seen_job_titles or (portal_url and portal_url in seen_urls):
                        continue
                    seen_job_titles.add(job_key)
                    if portal_url:
                        seen_urls.add(portal_url)

                    score_m = job_repo.get_score(job_m.job_id)
                    match_score = score_m.overall_score if score_m else 80.0
                    key_factors = score_m.strengths[:3] if (score_m and score_m.strengths) else ["Direct match for candidate architecture profile"]

                    top_applications.append(
                        TopApplicationItem(
                            company=job_m.company,
                            role=job_m.title,
                            salary=job_m.salary_raw_text or "Not Disclosed",
                            match_score=match_score,
                            key_factors=key_factors,
                            resume_used=app_m.resume_version or "Tailored_Principal_Architect_Resume.pdf",
                            status=app_m.status,
                            url=portal_url or job_m.url,
                            method=app_m.application_method or "NAUKRI_DIRECT",
                            reason=app_m.failure_reason,
                            evidence_path=app_m.evidence_path,
                            confirmation_ref=app_m.confirmation_reference,
                        )
                    )

                # Recompute summary counts strictly from current run's top_applications (including today's cumulative items)
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
                    top_applications=top_applications,
                )

                d_md, d_html, d_html_content = reporting_agent.generate_daily_report(daily_data)

                # Send Email 1: Daily Application Audit Report (skipped in offline test mode)
                if not self.offline_mode:
                    report_subject = f"CareerOps — Daily Application Report — {date_str}"
                    if self.dry_run:
                        report_subject = f"[DRY RUN] {report_subject}"
                    smtp_mailer.send_report(
                        subject=report_subject,
                        html_body=d_html_content,
                    )
                else:
                    logger.info("Offline mode: Skipping email delivery.")

                # Send Email 2: Consolidated Interview Intelligence Dossier (WEEKLY cycle on Friday or when forced)
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

                if should_send_interview and matched_items_for_briefing:
                    logger.info("Generating Weekly Consolidated Interview Intelligence Dossier...")
                    i_docx, i_pdf, i_html_content = interview_agent.generate_consolidated_daily_briefing(
                        matched_items_for_briefing, date_str
                    )
                    attachments = []
                    if i_pdf.exists():
                        attachments.append(i_pdf)
                    if i_docx.exists():
                        attachments.append(i_docx)

                    smtp_mailer.send_report(
                        subject=f"CareerOps — Weekly Consolidated Interview Intelligence Dossier — {date_str}",
                        html_body=i_html_content,
                        attachments=attachments,
                    )

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
