"""Master Orchestrator coordinating all autonomous career agents and state machine."""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

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
        self.dry_run = bool(config.get("application", {}).get("dry_run", True))
        db_url = config.get("database", {}).get("db_url", "sqlite:///naukri_career_agent.sqlite")
        init_db(db_url)
        self.db_url = db_url

    def run_daily_pipeline(self, force_weekly: bool = False, query_limit: int = 25) -> DailyReportData:
        """Executes the full automated weekday pipeline."""
        start_time = datetime.now(timezone.utc)
        run_id = f"run_{start_time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        date_str = start_time.strftime("%Y-%m-%d")

        logger.info(f"================ STARTING RUN {run_id} (DRY_RUN={self.dry_run}) ================")

        with get_db_session(self.db_url) as session:
            # Repositories
            job_repo = JobRepository(session)
            app_repo = ApplicationRepository(session)
            resume_repo = ResumeRepository(session)
            interview_repo = InterviewRepository(session)
            market_repo = MarketSignalRepository(session)
            run_repo = RunRepository(session)

            # Record run start
            run_repo.start_run(run_id=run_id, run_type="weekly" if force_weekly else "daily", dry_run=self.dry_run)

            # Clients and Agents
            naukri_client = PlaywrightBrowserAdapter(offline_mode=self.offline_mode)
            discovery_agent = DiscoveryAgent(naukri_client, job_repo, self.config)
            qualification_agent = QualificationAgent(job_repo, self.candidate_truth, self.config)
            resume_agent = ResumeAgent(resume_repo, self.candidate_truth, self.config)
            application_agent = ApplicationAgent(
                naukri_client, job_repo, app_repo, resume_repo, self.candidate_truth, self.config
            )
            interview_agent = InterviewAgent(interview_repo, self.candidate_truth)
            market_agent = MarketIntelligenceAgent(job_repo, market_repo, app_repo, self.candidate_truth)
            reporting_agent = ReportingAgent()
            smtp_mailer = SmtpMailer(self.config)

            top_applications = []
            resumes_generated = 0
            applications_attempted = 0
            confirmed_count = 0
            unverified_count = 0
            blocked_count = 0
            failed_count = 0
            external_count = 0
            manual_count = 0
            interview_packs_generated = 0
            strong_matches = 0

            # 1. DISCOVERY & EARLY SALARY FILTERING
            disc_result = discovery_agent.run_discovery(query_limit=query_limit)

            # 2. QUALIFICATION & SCORING
            for job in disc_result.eligible_jobs:
                score, evidence = qualification_agent.evaluate_job(job)

                if score.overall_score >= qualification_agent.high_match_threshold:
                    strong_matches += 1

                # 3. TAILOR RESUME & APPLY FOR QUALIFYING JOBS
                if score.passed_threshold:
                    # Tailor ATS Resume (DOCX & PDF)
                    docx_path, pdf_path, val_report = resume_agent.generate_tailored_resume(job, score)
                    resumes_generated += 1

                    # Process Automated Application
                    outcome = application_agent.process_application(job, score, docx_path, pdf_path)
                    applications_attempted += 1
                    status = outcome.status
                    if status in (JobStatus.APPLIED, JobStatus.APPLIED_CONFIRMED):
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
                    rec = outcome.app_record
                    method = rec.application_method if rec else "Naukri Direct"
                    ref = rec.confirmation_reference if rec else None
                    top_applications.append(
                        TopApplicationItem(
                            company=job.company,
                            role=job.title,
                            salary=job.salary.raw_text or "Not Disclosed",
                            match_score=score.overall_score,
                            key_factors=score.strengths[:3],
                            resume_used=docx_path.name,
                            status=status.value,
                            url=job.url,
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

            # 5. DAILY REPORTING & EMAIL NOTIFICATION
            end_time = datetime.now(timezone.utc)
            daily_data = DailyReportData(
                run_id=run_id,
                date=date_str,
                start_time=start_time,
                end_time=end_time,
                dry_run=self.dry_run,
                jobs_scanned=disc_result.total_found,
                salary_rejected=disc_result.salary_rejected,
                qualified_jobs=len([j for j in disc_result.eligible_jobs if j.status in (JobStatus.QUALIFIED, JobStatus.HIGH_MATCH, JobStatus.APPLIED, JobStatus.APPLIED_CONFIRMED, JobStatus.APPLICATION_READY)]),
                strong_matches=strong_matches,
                resumes_generated=resumes_generated,
                applications_submitted=applications_attempted,
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

            # Send Email
            smtp_mailer.send_report(
                subject=f"Career Agent — Daily Report — {date_str}",
                html_body=d_html_content,
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

        logger.info(f"================ COMPLETED RUN {run_id} ================")
        return daily_data
