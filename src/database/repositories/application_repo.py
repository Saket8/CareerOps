"""Application repository for recording and tracking job application lifecycles."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
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
        """Check if an application was already submitted, confirmed, unverified, or is actively leasing this job."""
        app = self.get_by_job_id(job_id)
        if not app:
            return False
        if app.status in (
            JobStatus.APPLIED.value,
            JobStatus.APPLIED_CONFIRMED.value,
            JobStatus.APPLICATION_READY.value,
            JobStatus.SUBMISSION_UNVERIFIED.value,
        ):
            return True
        # Check active unexpired lease (started within last 15 minutes)
        if app.status in (JobStatus.APPLICATION_STARTED.value, JobStatus.SUBMISSION_ATTEMPTED.value):
            if app.started_at:
                now = datetime.now(timezone.utc)
                started = app.started_at
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                age_minutes = (now - started).total_seconds() / 60.0
                if age_minutes < 15:
                    return True
        return False

    def can_retry_application(
        self,
        job_id: str,
        company: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Audits application history before retrying an ambiguous or failed submission to avoid duplicates.
        Explicitly tracks:
        - Prepared (APPLICATION_READY)
        - In Progress (APPLICATION_STARTED)
        - Confirmed (APPLIED_CONFIRMED)
        - Failed (APPLICATION_FAILED)
        - Submitted-but-unverified (SUBMISSION_UNVERIFIED)
        """
        if company and title and self.has_applied_to_company_and_title(company, title):
            return False, f"Already confirmed application for {title} @ {company}"

        app = self.get_by_job_id(job_id)
        if not app:
            return True, "No prior application record found"

        status = app.status
        if status in (JobStatus.APPLIED_CONFIRMED.value, JobStatus.APPLIED.value):
            return False, f"Application already confirmed (Ref: {app.confirmation_reference})"

        if status == JobStatus.SUBMISSION_UNVERIFIED.value:
            return False, "Application submission is unverified; manual history audit required before retrying to prevent duplicate submission"

        if status == JobStatus.APPLICATION_STARTED.value:
            if app.started_at:
                now = datetime.now(timezone.utc)
                started = app.started_at if app.started_at.tzinfo else app.started_at.replace(tzinfo=timezone.utc)
                age_minutes = (now - started).total_seconds() / 60.0
                if age_minutes < 15:
                    return False, f"Application is currently in progress (lease active: {age_minutes:.1f}m)"

        if status in (JobStatus.APPLICATION_BLOCKED.value, JobStatus.BLOCKED.value):
            return False, f"Application halted by safety gate: {app.failure_reason}"

        return True, "Eligible for submission attempt"

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
            db_app.application_id,
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

    def count_applications_attempted_today(self) -> int:
        """Count all applications submitted or attempted today to enforce daily limits across runs."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            self.session.query(func.count(ApplicationModel.application_id))
            .filter(
                ApplicationModel.started_at >= today_start,
                ApplicationModel.status.in_([
                    JobStatus.APPLIED.value,
                    JobStatus.APPLIED_CONFIRMED.value,
                    JobStatus.APPLICATION_STARTED.value,
                    JobStatus.APPLICATION_FAILED.value,
                    JobStatus.EXTERNAL_APPLICATION_REQUIRED.value,
                    JobStatus.NEEDS_MANUAL_INTERVENTION.value,
                ]),
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
            record.application_id = existing.application_id
            existing.status = status_val
            existing.application_method = method_val
            existing.source_job_url = record.source_job_url
            existing.canonical_job_url = record.canonical_job_url
            existing.application_url = record.application_url
            existing.external_application_url = record.external_application_url
            existing.external_portal = record.external_portal
            existing.started_at = record.started_at or existing.started_at
            if status_val == JobStatus.APPLIED_CONFIRMED.value and not record.submitted_at:
                record.submitted_at = datetime.now(timezone.utc)
            existing.submitted_at = record.submitted_at or (datetime.now(timezone.utc) if status_val == JobStatus.APPLIED_CONFIRMED.value else existing.submitted_at)
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
            submitted_at=record.submitted_at or (datetime.now(timezone.utc) if status_val == JobStatus.APPLIED_CONFIRMED.value else None),
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

    def save_outreach_draft(self, application_id: str, draft_data: Dict[str, Any]) -> None:
        """Saves a recruiter outreach draft in the application database for review.
        Never auto-sent to the recruiter.
        """
        app = self.session.query(ApplicationModel).filter(ApplicationModel.application_id == application_id).first()
        if app:
            if hasattr(app, "outreach_draft"):
                app.outreach_draft = draft_data
            qa = dict(app.questions_answered or {})
            qa["recruiter_outreach_draft"] = draft_data
            app.questions_answered = qa
            self.session.flush()

        self.log_event(
            application_id,
            from_status="OUTREACH_DRAFTED",
            to_status="OUTREACH_PENDING_REVIEW",
            reason="Recruiter outreach draft created and saved for manual review (not auto-sent)",
            payload=draft_data,
        )
        self.session.commit()
