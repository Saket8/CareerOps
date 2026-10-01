"""Run repository for recording agent execution cycles, statistics, and audits."""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.database.models import AgentRunModel


class RunRepository:
    def __init__(self, session: Session):
        self.session = session

    def start_run(self, run_id: str, run_type: str = "daily", dry_run: bool = True) -> AgentRunModel:
        run = AgentRunModel(
            run_id=run_id,
            run_type=run_type,
            start_time=datetime.now(timezone.utc),
            status="RUNNING",
            dry_run=dry_run,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_run(
        self,
        run_id: str,
        status: str = "SUCCESS",
        jobs_scanned: int = 0,
        salary_rejected: int = 0,
        qualified_jobs: int = 0,
        applications_submitted: int = 0,
        blocked_count: int = 0,
        failed_count: int = 0,
        error_summary: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> Optional[AgentRunModel]:
        run = self.session.query(AgentRunModel).filter(AgentRunModel.run_id == run_id).first()
        if run:
            run.end_time = datetime.now(timezone.utc)
            run.status = status
            run.jobs_scanned = jobs_scanned
            run.salary_rejected = salary_rejected
            run.qualified_jobs = qualified_jobs
            run.applications_submitted = applications_submitted
            run.blocked_count = blocked_count
            run.failed_count = failed_count
            run.error_summary = error_summary
            if metadata_json:
                run.metadata_json = metadata_json
            self.session.flush()
        return run

    def get_run(self, run_id: str) -> Optional[AgentRunModel]:
        return self.session.query(AgentRunModel).filter(AgentRunModel.run_id == run_id).first()

    def get_latest_runs(self, limit: int = 10) -> List[AgentRunModel]:
        return self.session.query(AgentRunModel).order_by(AgentRunModel.start_time.desc()).limit(limit).all()
