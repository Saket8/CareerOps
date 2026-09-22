"""Application Agent with state machine, idempotency, safety guards, and rate limiting."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from sqlalchemy.orm import Session

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.database.repositories.job_repo import JobRepository
from src.database.repositories.application_repo import ApplicationRepository
from src.database.repositories.resume_repo import ResumeRepository
from src.models.job import JobListing, JobStatus, ApplicationRecord, ApplicationMethod
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
        self.dry_run = bool(app_cfg.get("dry_run", False))
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

        # 0. Employer Safety Gate (Current Employer Blocklist)
        blocked_companies = [
            c.lower().strip() for c in self.config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])
        ]
        if any(b in job.company.lower() for b in blocked_companies):
            logger.critical(
                f"CRITICAL SAFETY GATE: Prevented application to current employer '{job.company}' (Job: {job.title})"
            )
            self.job_repo.update_status(job_id, JobStatus.REJECTED)
            return ApplicationOutcome(job_id, False, JobStatus.REJECTED, f"Blocked current employer: {job.company}")

        # 0b. External Portal Opportunities Handling (Does not consume direct on-platform apply quota)
        if job.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED:
            app_rec = self.app_repo.get_by_job_id(job_id)
            if not app_rec:
                app_id = f"app_{job_id}_{int(datetime.now(timezone.utc).timestamp())}"
                app_record = ApplicationRecord(
                    application_id=app_id,
                    job_id=job.job_id,
                    application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
                    source_job_url=job.url,
                    canonical_job_url=getattr(job, "canonical_job_url", None) or job.url,
                    external_application_url=getattr(job, "external_url", None) or job.url,
                    external_portal="External Career Portal",
                    started_at=datetime.now(timezone.utc),
                    status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                    failure_reason="Application must be completed on external company career portal",
                    dry_run=self.dry_run,
                )
                self.app_repo.record_application(app_record)
            else:
                app_record = ApplicationRecord(
                    application_id=app_rec.application_id,
                    job_id=app_rec.job_id,
                    application_method=app_rec.application_method,
                    source_job_url=app_rec.source_job_url,
                    canonical_job_url=app_rec.canonical_job_url,
                    external_application_url=app_rec.external_application_url or job.url,
                    external_portal=app_rec.external_portal or "External Career Portal",
                    started_at=app_rec.started_at or datetime.now(timezone.utc),
                    status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                    failure_reason="Application must be completed on external company career portal",
                    dry_run=self.dry_run,
                )
            return ApplicationOutcome(
                job_id, True, JobStatus.EXTERNAL_APPLICATION_REQUIRED, "External company career portal application required", app_record
            )

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

        # 4. Pre-Flight Atomic Lease Persistence (Durability Invariant)
        self.job_repo.update_status(job_id, JobStatus.APPLICATION_READY)
        app_id = f"app_{job_id}_{int(datetime.now(timezone.utc).timestamp())}"
        resume_version = self.resume_repo.get_by_job_id(job_id)
        version_id = resume_version.version_id if resume_version else None

        preflight_record = ApplicationRecord(
            application_id=app_id,
            job_id=job.job_id,
            resume_version_id=version_id,
            application_method=ApplicationMethod.NAUKRI_DIRECT.value,
            source_job_url=job.url,
            canonical_job_url=getattr(job, "canonical_job_url", None) or job.url,
            started_at=datetime.now(timezone.utc),
            status=JobStatus.APPLICATION_STARTED,
            dry_run=self.dry_run,
        )
        self.app_repo.record_application(preflight_record)
        self.job_repo.update_status(job_id, JobStatus.APPLICATION_STARTED)
        self.app_repo.log_event(app_id, "ATS_VALIDATED", "APPLICATION_READY", "Prepared tailored resume and verified answers")
        self.app_repo.log_event(app_id, "APPLICATION_READY", "APPLICATION_STARTED", "Acquired pre-flight application lease before browser submission")

        # 5. Attempt Submission via Client Adapter with Safety Trap
        try:
            record = self.client.submit_application(
                job=job,
                resume_docx_path=str(docx_path),
                resume_pdf_path=str(pdf_path),
                candidate_truth=self.candidate_truth,
                dry_run=self.dry_run,
            )
            record.application_id = app_id
            record.resume_version_id = version_id

            # Determine concrete status from record
            raw_status = record.status.value if hasattr(record.status, "value") else str(record.status)
            try:
                final_status = JobStatus(raw_status)
            except ValueError:
                final_status = JobStatus.APPLICATION_FAILED

            # Strict Zero-Dummy Invariant:
            # 1. At no point can a dummy/mock apply reference be confirmed
            if record.confirmation_reference and any(record.confirmation_reference.startswith(p) for p in ("MOCK_", "SIM_")):
                logger.error(
                    f"Dummy confirmation detected ({record.confirmation_reference}) for {job_id}. "
                    f"Rejecting dummy apply per zero-dummy policy."
                )
                final_status = JobStatus.APPLICATION_FAILED
                record.status = JobStatus.APPLICATION_FAILED
                record.confirmation_detected = False
                record.confirmation_reference = None
                record.failure_reason = "Rejected dummy confirmation reference (Zero dummy apply policy enforced)"

            # 2. In dry-run mode, live submission is skipped and job status stays APPLICATION_READY
            if self.dry_run:
                final_status = JobStatus.APPLICATION_READY
                record.status = JobStatus.APPLICATION_READY
                record.confirmation_detected = False
                record.confirmation_reference = None
                is_confirmed = False
            else:
                is_confirmed = (
                    final_status in (JobStatus.APPLIED_CONFIRMED, JobStatus.APPLIED)
                    and record.confirmation_detected
                    and bool(record.confirmation_reference)
                )
                if is_confirmed:
                    final_status = JobStatus.APPLIED_CONFIRMED
                    record.status = JobStatus.APPLIED_CONFIRMED

            # Save application to repository
            self.app_repo.record_application(record)

            event_status = final_status.value
            event_desc = f"Application workflow completed: {final_status.value} (DRY_RUN={self.dry_run})"
            if record.failure_reason:
                event_desc += f" - {record.failure_reason}"

            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                event_status,
                event_desc,
                payload={
                    "confirmation": record.confirmation_reference,
                    "method": record.application_method,
                    "status": final_status.value,
                },
            )

            # Update Job Status
            self.job_repo.update_status(job_id, final_status)
            if is_confirmed:
                logger.info(
                    f"Application CONFIRMED for '{job.title}' @ {job.company} "
                    f"[LIVE | Ref: {record.confirmation_reference}]"
                )
                return ApplicationOutcome(job_id, True, final_status, "Submitted successfully and confirmed", record)
            else:
                logger.warning(
                    f"Application NOT confirmed for '{job.title}' @ {job.company}: {final_status.value} - {record.failure_reason}"
                )
                return ApplicationOutcome(job_id, False, final_status, record.failure_reason or final_status.value, record)

        except SafetyBarrierException as barrier_err:
            logger.warning(f"Exception Safety Boundary triggered for job {job_id}: {barrier_err}")
            self.job_repo.update_status(job_id, JobStatus.APPLICATION_BLOCKED)
            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                "APPLICATION_BLOCKED",
                f"Halted at barrier: {barrier_err.barrier_type}",
                payload={"barrier": barrier_err.barrier_type, "message": str(barrier_err)},
            )
            return ApplicationOutcome(job_id, False, JobStatus.APPLICATION_BLOCKED, str(barrier_err))

        except Exception as exc:
            logger.error(f"Application error for job {job_id}: {exc}")
            self.job_repo.update_status(job_id, JobStatus.APPLICATION_FAILED)
            self.app_repo.log_event(
                app_id,
                "APPLICATION_READY",
                "APPLICATION_FAILED",
                f"Unexpected application failure: {exc}",
            )
            return ApplicationOutcome(job_id, False, JobStatus.APPLICATION_FAILED, str(exc))

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
