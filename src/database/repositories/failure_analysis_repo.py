"""Repository for application failure analyses and self-healing telemetry."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from src.database.models import ApplicationFailureAnalysisModel
from src.utils.logger import get_logger

logger = get_logger("failure_analysis_repo")


class FailureAnalysisRepository:
    """Manages persistence of application failure diagnostics and self-healing events."""

    def __init__(self, session: Session):
        self.session = session

    def record_analysis(
        self,
        job_id: str,
        company: str,
        job_title: str,
        failure_status: str,
        root_cause_category: str,
        analysis_summary: str,
        application_id: Optional[str] = None,
        run_id: Optional[str] = None,
        job_url: Optional[str] = None,
        raw_failure_reason: Optional[str] = None,
        screening_questions: Optional[List[Any]] = None,
        screening_answers: Optional[Dict[str, Any]] = None,
        evidence_path: Optional[str] = None,
        self_healing_action: Optional[str] = None,
        self_healing_details: Optional[Dict[str, Any]] = None,
        healing_status: str = "RESOLVED",
        retry_eligible: bool = False,
    ) -> ApplicationFailureAnalysisModel:
        """Records a failure analysis and self-healing action, updating existing record if present."""
        existing = (
            self.session.query(ApplicationFailureAnalysisModel)
            .filter(ApplicationFailureAnalysisModel.job_id == job_id)
            .first()
        )

        if existing:
            existing.company = company
            existing.job_title = job_title
            existing.failure_status = failure_status
            existing.root_cause_category = root_cause_category
            existing.analysis_summary = analysis_summary
            existing.application_id = application_id or existing.application_id
            existing.run_id = run_id or existing.run_id
            existing.job_url = job_url or existing.job_url
            existing.raw_failure_reason = raw_failure_reason or existing.raw_failure_reason
            existing.screening_questions = screening_questions or existing.screening_questions or []
            existing.screening_answers = screening_answers or existing.screening_answers or {}
            existing.evidence_path = evidence_path or existing.evidence_path
            existing.self_healing_action = self_healing_action or existing.self_healing_action
            existing.self_healing_details = self_healing_details or existing.self_healing_details or {}
            existing.healing_status = healing_status
            existing.retry_eligible = retry_eligible
            existing.updated_at = datetime.now(timezone.utc)
            self.session.flush()
            logger.info(f"Updated failure analysis for job {job_id} ({company} - {job_title}): {root_cause_category}")
            return existing

        record = ApplicationFailureAnalysisModel(
            job_id=job_id,
            application_id=application_id,
            run_id=run_id,
            company=company,
            job_title=job_title,
            job_url=job_url,
            failure_status=failure_status,
            raw_failure_reason=raw_failure_reason,
            screening_questions=screening_questions or [],
            screening_answers=screening_answers or {},
            evidence_path=evidence_path,
            root_cause_category=root_cause_category,
            analysis_summary=analysis_summary,
            self_healing_action=self_healing_action,
            self_healing_details=self_healing_details or {},
            healing_status=healing_status,
            retry_eligible=retry_eligible,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.flush()
        logger.info(f"Recorded new failure analysis for job {job_id} ({company} - {job_title}): {root_cause_category}")
        return record

    def get_by_job_id(self, job_id: str) -> Optional[ApplicationFailureAnalysisModel]:
        """Fetches the failure analysis record for a specific job."""
        return (
            self.session.query(ApplicationFailureAnalysisModel)
            .filter(ApplicationFailureAnalysisModel.job_id == job_id)
            .first()
        )

    def get_by_run_id(self, run_id: str) -> List[ApplicationFailureAnalysisModel]:
        """Fetches all failure analyses recorded during a specific run."""
        return (
            self.session.query(ApplicationFailureAnalysisModel)
            .filter(ApplicationFailureAnalysisModel.run_id == run_id)
            .all()
        )

    def get_all(self, limit: int = 100) -> List[ApplicationFailureAnalysisModel]:
        """Fetches the latest failure analyses across all runs."""
        return (
            self.session.query(ApplicationFailureAnalysisModel)
            .order_by(ApplicationFailureAnalysisModel.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_unhealed(self) -> List[ApplicationFailureAnalysisModel]:
        """Fetches all failures that are still pending healing or requiring manual review."""
        return (
            self.session.query(ApplicationFailureAnalysisModel)
            .filter(ApplicationFailureAnalysisModel.healing_status.in_(["PENDING", "ACTION_REQUIRED", "UNRESOLVED"]))
            .all()
        )
