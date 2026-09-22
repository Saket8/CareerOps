"""Application repository for recording and tracking job application lifecycles."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import ApplicationModel, ApplicationEventModel
from src.models.job import ApplicationRecord, JobStatus


class ApplicationRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_job_id(self, job_id: str) -> Optional[ApplicationModel]:
        return self.session.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()

    def has_applied_to_job(self, job_id: str) -> bool:
        """Check if an application was already submitted or is active for this job."""
        app = self.get_by_job_id(job_id)
        if not app:
            return False
        return app.status in (JobStatus.APPLIED.value, JobStatus.APPLICATION_READY.value)

    def count_applications_today(self) -> int:
        """Count successful applications submitted today to enforce daily limits."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(func.count(ApplicationModel.application_id))
            .filter(
                ApplicationModel.status == JobStatus.APPLIED.value,
                ApplicationModel.submitted_at >= today_start,
            )
            .scalar()
            or 0
        )

    def record_application(self, record: ApplicationRecord) -> ApplicationModel:
        """Create or update an application record."""
        existing = self.session.query(ApplicationModel).filter(ApplicationModel.application_id == record.application_id).first()
        if existing:
            existing.status = record.status.value
            existing.submitted_at = record.submitted_at
            existing.resume_version_id = record.resume_version_id
            existing.confirmation_reference = record.confirmation_reference
            existing.questions_answered = record.questions_answered
            existing.failure_reason = record.failure_reason
            existing.dry_run = record.dry_run
            self.session.flush()
            return existing

        db_app = ApplicationModel(
            application_id=record.application_id,
            job_id=record.job_id,
            resume_version_id=record.resume_version_id,
            submitted_at=record.submitted_at,
            status=record.status.value,
            application_method=record.application_method,
            confirmation_reference=record.confirmation_reference,
            questions_answered=record.questions_answered,
            failure_reason=record.failure_reason,
            dry_run=record.dry_run,
        )
        self.session.add(db_app)
        self.session.flush()
        return db_app

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
