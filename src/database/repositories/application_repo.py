"""Application repository for recording and tracking job application lifecycles."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import ApplicationModel, ApplicationEventModel, JobModel
from src.models.job import ApplicationRecord, JobStatus


class ApplicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_job_id(self, job_id: str) -> Optional[ApplicationModel]:
        return self.session.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()

    def has_applied_to_job(self, job_id: str) -> bool:
        """Check if an application was already submitted or is actively leasing this job."""
        app = self.get_by_job_id(job_id)
        if not app:
            return False
        return app.status in (
            JobStatus.APPLIED.value,
            JobStatus.APPLIED_CONFIRMED.value,
            JobStatus.APPLICATION_READY.value,
            JobStatus.APPLICATION_STARTED.value,
            JobStatus.SUBMISSION_ATTEMPTED.value,
        )

    def has_applied_to_company_and_title(self, company: str, title: str) -> bool:
        """Check if an application was submitted for the same company and title."""
        return (
            self.session.query(ApplicationModel)
            .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
            .filter(
                func.lower(JobModel.company) == company.lower().strip(),
                func.lower(JobModel.title) == title.lower().strip(),
                ApplicationModel.status.in_([
                    JobStatus.APPLIED.value,
                    JobStatus.APPLIED_CONFIRMED.value,
                    JobStatus.APPLICATION_READY.value,
                    JobStatus.APPLICATION_STARTED.value,
                ]),
            )
            .first()
            is not None
        )

    def commit_preflight_lease(self, record: ApplicationRecord) -> ApplicationModel:
        """Atomically persist and commit an APPLICATION_STARTED pre-flight lease to disk."""
        record.status = JobStatus.APPLICATION_STARTED
        db_app = self.record_application(record, commit=True)
        self.log_event(
            record.application_id,
            "APPLICATION_READY",
            JobStatus.APPLICATION_STARTED.value,
            "Committed pre-flight application lease before browser submission",
        )
        self.session.commit()
        return db_app

    def count_applications_today(self) -> int:
        """Count successful applications submitted today to enforce daily limits."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(func.count(ApplicationModel.application_id))
            .filter(
                ApplicationModel.status.in_([JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value]),
                ApplicationModel.submitted_at >= today_start,
            )
            .scalar()
            or 0
        )

    def record_application(self, record: ApplicationRecord, commit: bool = False) -> ApplicationModel:
        """Create or update an application record with full audit trail."""
        existing = (
            self.session.query(ApplicationModel)
            .filter((ApplicationModel.application_id == record.application_id) | (ApplicationModel.job_id == record.job_id))
            .first()
        )
        status_val = record.status.value if hasattr(record.status, "value") else str(record.status)
        method_val = record.application_method.value if hasattr(record.application_method, "value") else str(record.application_method)

        if existing:
            existing.status = status_val
            existing.application_method = method_val
            existing.source_job_url = record.source_job_url
            existing.canonical_job_url = record.canonical_job_url
            existing.application_url = record.application_url
            existing.external_application_url = record.external_application_url
            existing.external_portal = record.external_portal
            existing.started_at = record.started_at
            existing.submitted_at = record.submitted_at
            existing.resume_version = record.resume_version
            existing.resume_version_id = record.resume_version_id
            existing.questions_detected = record.questions_detected
            existing.questions_answered = record.questions_answered
            existing.confirmation_detected = record.confirmation_detected
            existing.confirmation_text = record.confirmation_text
            existing.confirmation_reference = record.confirmation_reference
            existing.final_url = record.final_url
            existing.verification_method = record.verification_method
            existing.error_code = record.error_code
            existing.error_message = record.error_message
            existing.evidence_path = record.evidence_path
            existing.failure_reason = record.failure_reason
            existing.dry_run = record.dry_run
            if commit:
                self.session.commit()
            else:
                self.session.flush()
            return existing

        db_app = ApplicationModel(
            application_id=record.application_id,
            job_id=record.job_id,
            resume_version_id=record.resume_version_id,
            resume_version=record.resume_version,
            application_method=method_val,
            source_job_url=record.source_job_url,
            canonical_job_url=record.canonical_job_url,
            application_url=record.application_url,
            external_application_url=record.external_application_url,
            external_portal=record.external_portal,
            started_at=record.started_at,
            submitted_at=record.submitted_at,
            status=status_val,
            questions_detected=record.questions_detected,
            questions_answered=record.questions_answered,
            confirmation_detected=record.confirmation_detected,
            confirmation_text=record.confirmation_text,
            confirmation_reference=record.confirmation_reference,
            final_url=record.final_url,
            verification_method=record.verification_method,
            error_code=record.error_code,
            error_message=record.error_message,
            evidence_path=record.evidence_path,
            failure_reason=record.failure_reason,
            dry_run=record.dry_run,
        )
        self.session.add(db_app)
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return db_app

    def release_or_fail_lease(
        self,
        application_id: str,
        from_status: str = "APPLICATION_STARTED",
        to_status: str = "APPLICATION_FAILED",
        reason: str = "Submission aborted or crashed",
    ) -> Optional[ApplicationModel]:
        """Transitions a lease out of active state with disk commit."""
        app = self.session.query(ApplicationModel).filter(ApplicationModel.application_id == application_id).first()
        if app:
            app.status = to_status
            app.failure_reason = reason
            self.log_event(application_id, from_status, to_status, reason)
            self.session.commit()
        return app

    def log_event(self, application_id: str, from_status: str, to_status: str, reason: str = "", payload: Optional[Dict[str, Any]] = None) -> ApplicationEventModel:
        """Log an explicit state transition event."""
        event = ApplicationEventModel(
            application_id=application_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            payload=payload or {},
        )
        self.session.add(event)
        self.session.flush()
        return event

    def get_todays_applications(self) -> List[ApplicationModel]:
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.query(ApplicationModel).filter(ApplicationModel.created_at >= today_start).all()
