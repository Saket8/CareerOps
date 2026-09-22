"""Application Agent with state machine, idempotency, safety guards, and rate limiting."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from sqlalchemy.orm import Session

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.database.repositories.job_repo import JobRepository
from src.database.repositories.application_repo import ApplicationRepository
from src.database.repositories.resume_repo import ResumeRepository
from src.models.job import JobListing, JobStatus, ApplicationRecord
from src.models.candidate import CandidateTruth
from src.models.score import JobScore
from src.utils.logger import get_logger

logger = get_logger("application_agent")


class ApplicationOutcome:
    def __init__(self, job_id: str, success: bool, status: JobStatus, reason: str = "", app_record: Optional[ApplicationRecord] = None):
        self.job_id = job_id
        self.success = success
        self.status = status
        self.reason = reason
        self.app_record = app_record


class ApplicationAgent:
    """Executes automated job applications enforcing idempotency and safety bounds."""

    def __init__(
        self,
        client: BaseNaukriClient,
        job_repo: JobRepository,
        app_repo: ApplicationRepository,
        resume_repo: ResumeRepository,
        candidate_truth: CandidateTruth,
        config: Dict[str, Any],
    ):
        self.client = client
        self.job_repo = job_repo
        self.app_repo = app_repo
        self.resume_repo = resume_repo
        self.candidate_truth = candidate_truth
        self.config = config

        app_cfg = config.get("application", {})
        self.dry_run = bool(app_cfg.get("dry_run", True))
        self.max_applications_per_day = int(app_cfg.get("max_applications_per_day", 10))

    def process_application(
        self,
        job: JobListing,
        score: JobScore,
        docx_path: Path,
        pdf_path: Path,
    ) -> ApplicationOutcome:
        """Processes and submits a single application with complete guardrails."""
        job_id = job.job_id

        # 1. Idempotency Check: prevent duplicate application
        if self.app_repo.has_applied_to_job(job_id):
            logger.info(f"Idempotency Guard: Application already exists for job {job_id}. Skipping.")
            return ApplicationOutcome(job_id, False, JobStatus.APPLIED, "Duplicate application skipped")

        # 2. Daily Application Limit Check
        applied_today = self.app_repo.count_applications_today()
        if applied_today >= self.max_applications_per_day:
            logger.warning(
                f"Daily Quota Exceeded: {applied_today}/{self.max_applications_per_day} applications submitted today. "
                f"Queueing job {job_id} as APPLICATION_READY."
            )
            self.job_repo.update_status(job_id, JobStatus.APPLICATION_READY)
            return ApplicationOutcome(
                job_id, False, JobStatus.APPLICATION_READY, f"Daily limit of {self.max_applications_per_day} reached"
            )

        # 3. Candidate Truth Question Answering Validation
        answers, has_all_data, missing_field = self._resolve_application_questions()
        if not has_all_data:
            logger.warning(f"Safety Gate: Missing verified candidate fact '{missing_field}' for job {job_id}. Marking NEEDS_DATA.")
            self.job_repo.update_status(job_id, JobStatus.NEEDS_DATA)
            return ApplicationOutcome(job_id, False, JobStatus.NEEDS_DATA, f"Missing verified fact: {missing_field}")

        # Transition to APPLICATION_READY
        self.job_repo.update_status(job_id, JobStatus.APPLICATION_READY)
        app_id = f"app_{job_id}_{int(datetime.now(timezone.utc).timestamp())}"
        self.app_repo.log_event(app_id, "ATS_VALIDATED", "APPLICATION_READY", "Prepared tailored resume and verified answers")

        # 4. Attempt Submission via Client Adapter with Safety Trap
        try:
            resume_version = self.resume_repo.get_by_job_id(job_id)
            version_id = resume_version.version_id if resume_version else None

            record = self.client.submit_application(
                job=job,
                resume_docx_path=str(docx_path),
                resume_pdf_path=str(pdf_path),
                candidate_truth=self.candidate_truth,
                dry_run=self.dry_run,
            )
            record.application_id = app_id
            record.resume_version_id = version_id

            # Save application to repository
            self.app_repo.record_application(record)
            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                "APPLIED",
                f"Application submitted successfully (DRY_RUN={self.dry_run})",
                payload={"confirmation": record.confirmation_reference},
            )

            # Update Job Status
            self.job_repo.update_status(job_id, JobStatus.APPLIED)
            logger.info(
                f"Application successful for '{job.title}' @ {job.company} "
                f"[{'DRY_RUN' if self.dry_run else 'LIVE'} | Ref: {record.confirmation_reference}]"
            )
            return ApplicationOutcome(job_id, True, JobStatus.APPLIED, "Submitted successfully", record)

        except SafetyBarrierException as barrier_err:
            logger.warning(f"Exception Safety Boundary triggered for job {job_id}: {barrier_err}")
            self.job_repo.update_status(job_id, JobStatus.BLOCKED)
            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                "BLOCKED",
                f"Halted at barrier: {barrier_err.barrier_type}",
                payload={"barrier": barrier_err.barrier_type, "message": str(barrier_err)},
            )
            return ApplicationOutcome(job_id, False, JobStatus.BLOCKED, str(barrier_err))

        except Exception as exc:
            logger.error(f"Application error for job {job_id}: {exc}")
            self.job_repo.update_status(job_id, JobStatus.FAILED)
            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                "FAILED",
                f"Unexpected application failure: {exc}",
            )
            return ApplicationOutcome(job_id, False, JobStatus.FAILED, str(exc))

    def _resolve_application_questions(self) -> Tuple[Dict[str, Any], bool, str]:
        """Resolves standard questions strictly against candidate truth."""
        cand = self.candidate_truth.candidate
        
        # Verify required parameters exist
        if not cand.name:
            return {}, False, "candidate.name"
        if not cand.email:
            return {}, False, "candidate.email"
        if not cand.phone:
            return {}, False, "candidate.phone"
        if cand.total_experience_years is None:
            return {}, False, "candidate.total_experience_years"

        answers = {
            "current_location": cand.location,
            "preferred_locations": cand.preferred_locations,
            "total_experience": cand.total_experience_years,
            "cloud_experience": cand.cloud_experience_years,
            "oci_experience": cand.oci_experience_years,
            "notice_period_days": cand.notice_period_days,
            "willingness_to_relocate": cand.willing_to_relocate,
            "work_authorization": cand.work_authorization,
            "current_company": cand.current_organization,
            "current_role": cand.current_role,
        }
        return answers, True, ""
