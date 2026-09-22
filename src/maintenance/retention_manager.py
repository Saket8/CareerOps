"""Database and Storage Retention Engine.

Safely purges stale, unapplied jobs, old telemetry runs, and temporary scratch
files while strictly protecting all confirmed applications, live evidence,
master resumes, and active candidate data.
"""

import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Set, Optional

from sqlalchemy import text
from src.database.connection import get_db_session
from src.database.models import (
    JobModel,
    ApplicationModel,
    ResumeVersionModel,
    AgentRunModel,
    MarketSignalModel,
)
from src.utils.logger import get_logger

logger = get_logger("retention_manager")

# Invariant: Statuses that must NEVER be deleted
PROTECTED_JOB_STATUSES = {
    "APPLIED",
    "APPLIED_CONFIRMED",
    "INTERVIEW",
    "OFFER",
    "APPLICATION_READY",
    "QUALIFIED",
    "HIGH_MATCH",
}


class RetentionManager:
    """Manages database pruning, file storage reclamation, and SQLite compacting."""

    def __init__(self, config: Dict[str, Any], base_dir: Optional[Path] = None):
        self.config = config
        self.retention_cfg = config.get("retention", {})
        self.enabled = bool(self.retention_cfg.get("enabled", True))
        self.db_url = config.get("database", {}).get("db_url", "sqlite:///naukri_career_agent.sqlite")
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

        # Thresholds (in days)
        self.unqualified_job_days = int(self.retention_cfg.get("unqualified_job_days", 14))
        self.run_history_days = int(self.retention_cfg.get("run_history_days", 90))
        self.market_signal_days = int(self.retention_cfg.get("market_signal_days", 90))
        self.evidence_scratch_days = int(self.retention_cfg.get("evidence_scratch_days", 14))
        self.draft_resume_days = int(self.retention_cfg.get("draft_resume_days", 30))
        self.log_days = int(self.retention_cfg.get("log_days", 14))
        self.auto_vacuum = bool(self.retention_cfg.get("auto_vacuum_db", True))

    def apply_retention_policy(self, dry_run: bool = False) -> Dict[str, Any]:
        """Executes full database and storage retention cleanup."""
        if not self.enabled:
            logger.info("Retention policy is disabled in configuration. Skipping cleanup.")
            return {"status": "DISABLED", "database": {}, "storage": {}}

        logger.info(f"Initiating retention cleanup policy (DRY_RUN={dry_run})...")
        db_stats = self.clean_database(dry_run=dry_run)
        storage_stats = self.clean_storage(dry_run=dry_run)

        logger.info(
            f"Retention policy complete. DB Purged: {db_stats.get('jobs_purged', 0)} jobs, "
            f"Storage Reclaimed: {storage_stats.get('bytes_reclaimed', 0):,} bytes across "
            f"{storage_stats.get('total_files_deleted', 0)} files."
        )

        return {
            "status": "SUCCESS",
            "dry_run": dry_run,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "database": db_stats,
            "storage": storage_stats,
        }

    def clean_database(self, dry_run: bool = False) -> Dict[str, Any]:
        """Prunes stale unapplied jobs, old runs, and runs VACUUM on SQLite."""
        now = datetime.now(timezone.utc)
        job_cutoff = now - timedelta(days=self.unqualified_job_days)
        run_cutoff = now - timedelta(days=self.run_history_days)
        signal_cutoff = now - timedelta(days=self.market_signal_days)
        resume_cutoff = now - timedelta(days=self.draft_resume_days)

        stats = {
            "jobs_purged": 0,
            "runs_purged": 0,
            "signals_purged": 0,
            "resume_versions_purged": 0,
            "vacuum_executed": False,
        }

        with get_db_session(self.db_url) as session:
            # 1. Identify jobs protected by applications table
            applied_job_ids: Set[str] = {
                app.job_id for app in session.query(ApplicationModel.job_id).all() if app.job_id
            }

            # 2. Query candidates for job pruning
            stale_jobs = (
                session.query(JobModel)
                .filter(
                    JobModel.status.notin_(PROTECTED_JOB_STATUSES),
                    JobModel.created_at < job_cutoff,
                )
                .all()
            )

            to_delete_jobs = [j for j in stale_jobs if j.job_id not in applied_job_ids]
            stats["jobs_purged"] = len(to_delete_jobs)

            if not dry_run and to_delete_jobs:
                for j in to_delete_jobs:
                    session.delete(j)
                session.commit()
                logger.info(f"Purged {len(to_delete_jobs)} stale unapplied jobs from database.")

            # 3. Query old pipeline runs
            stale_runs = session.query(AgentRunModel).filter(AgentRunModel.start_time < run_cutoff).all()
            stats["runs_purged"] = len(stale_runs)
            if not dry_run and stale_runs:
                for r in stale_runs:
                    session.delete(r)
                session.commit()
                logger.info(f"Purged {len(stale_runs)} historical agent runs older than {self.run_history_days} days.")

            # 4. Query old market signals
            stale_signals = (
                session.query(MarketSignalModel)
                .filter(MarketSignalModel.created_at < signal_cutoff)
                .all()
            )
            stats["signals_purged"] = len(stale_signals)
            if not dry_run and stale_signals:
                for s in stale_signals:
                    session.delete(s)
                session.commit()
                logger.info(f"Purged {len(stale_signals)} market signals older than {self.market_signal_days} days.")

            # 5. Query orphaned draft resume versions
            referenced_resume_ids: Set[str] = {
                app.resume_version_id
                for app in session.query(ApplicationModel.resume_version_id).all()
                if app.resume_version_id
            }
            stale_resumes = (
                session.query(ResumeVersionModel)
                .filter(
                    ResumeVersionModel.is_master == False,
                    ResumeVersionModel.created_at < resume_cutoff,
                )
                .all()
            )
            to_delete_resumes = [r for r in stale_resumes if r.version_id not in referenced_resume_ids]
            stats["resume_versions_purged"] = len(to_delete_resumes)
            if not dry_run and to_delete_resumes:
                for r in to_delete_resumes:
                    session.delete(r)
                session.commit()
                logger.info(f"Purged {len(to_delete_resumes)} orphaned draft resume version records.")

        # 6. Reclaim disk space via SQLite VACUUM
        if self.auto_vacuum and not dry_run and "sqlite" in self.db_url.lower():
            try:
                from sqlalchemy import create_engine
                engine = create_engine(self.db_url)
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                    conn.execute(text("VACUUM;"))
                stats["vacuum_executed"] = True
                logger.info("Executed SQLite VACUUM to reclaim disk space.")
            except Exception as e:
                logger.warning(f"Failed to execute VACUUM on database: {e}")

        return stats

    def clean_storage(self, dry_run: bool = False) -> Dict[str, Any]:
        """Prunes stale log files, ephemeral scratch artifacts, and unreferenced draft resumes."""
        now_ts = time.time()
        log_cutoff_ts = now_ts - (self.log_days * 86400)
        scratch_cutoff_ts = now_ts - (7 * 86400)  # 7 days for scratch debug files
        evidence_cutoff_ts = now_ts - (self.evidence_scratch_days * 86400)
        resume_cutoff_ts = now_ts - (self.draft_resume_days * 86400)

        stats = {
            "logs_deleted": 0,
            "scratch_files_deleted": 0,
            "draft_resumes_deleted": 0,
            "evidence_files_deleted": 0,
            "total_files_deleted": 0,
            "bytes_reclaimed": 0,
        }

        # 1. Clean old application logs in logs/
        logs_dir = self.base_dir / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.glob("*.log"):
                try:
                    if log_file.stat().st_mtime < log_cutoff_ts:
                        size = log_file.stat().st_size
                        stats["logs_deleted"] += 1
                        stats["bytes_reclaimed"] += size
                        if not dry_run:
                            log_file.unlink()
                except Exception as e:
                    logger.warning(f"Could not inspect/delete log file {log_file}: {e}")

        # 2. Clean scratch directory
        scratch_dir = self.base_dir / "artifacts" / "scratch"
        if scratch_dir.exists():
            for scratch_file in scratch_dir.iterdir():
                if scratch_file.is_file():
                    try:
                        if scratch_file.stat().st_mtime < scratch_cutoff_ts:
                            size = scratch_file.stat().st_size
                            stats["scratch_files_deleted"] += 1
                            stats["bytes_reclaimed"] += size
                            if not dry_run:
                                scratch_file.unlink()
                    except Exception as e:
                        logger.warning(f"Could not inspect/delete scratch file {scratch_file}: {e}")

        # 3. Clean evidence directory (Strictly protecting confirmed application proofs)
        # Find all protected evidence paths from the database
        protected_evidence_names: Set[str] = set()
        try:
            with get_db_session(self.db_url) as session:
                for app in session.query(ApplicationModel).all():
                    if app.evidence_path:
                        protected_evidence_names.add(Path(app.evidence_path).name.lower())
        except Exception:
            pass

        evidence_dir = self.base_dir / "artifacts" / "evidence"
        if evidence_dir.exists():
            for ev_file in evidence_dir.iterdir():
                if not ev_file.is_file():
                    continue
                name_lower = ev_file.name.lower()
                # Absolute protection for confirmed apply evidence and history screenshots
                if "already_applied" in name_lower or "history" in name_lower or name_lower in protected_evidence_names:
                    continue

                try:
                    if ev_file.stat().st_mtime < evidence_cutoff_ts:
                        size = ev_file.stat().st_size
                        stats["evidence_files_deleted"] += 1
                        stats["bytes_reclaimed"] += size
                        if not dry_run:
                            ev_file.unlink()
                except Exception as e:
                    logger.warning(f"Could not inspect/delete evidence file {ev_file}: {e}")

        # 4. Clean draft resumes in resumes/generated/
        # Master resumes in resumes/master/ are NEVER touched.
        protected_resume_names: Set[str] = set()
        try:
            with get_db_session(self.db_url) as session:
                for app in session.query(ApplicationModel).all():
                    if app.resume_version:
                        protected_resume_names.add(app.resume_version.lower())
                for res in session.query(ResumeVersionModel).filter(ResumeVersionModel.is_master == False).all():
                    if res.file_path_docx:
                        protected_resume_names.add(Path(res.file_path_docx).name.lower())
                    if res.file_path_pdf:
                        protected_resume_names.add(Path(res.file_path_pdf).name.lower())
        except Exception:
            pass

        resumes_gen_dir = self.base_dir / "resumes" / "generated"
        if resumes_gen_dir.exists():
            for res_file in resumes_gen_dir.iterdir():
                if not res_file.is_file():
                    continue
                name_lower = res_file.name.lower()
                # Protect if linked to active application or recent
                if name_lower in protected_resume_names:
                    continue

                try:
                    if res_file.stat().st_mtime < resume_cutoff_ts:
                        size = res_file.stat().st_size
                        stats["draft_resumes_deleted"] += 1
                        stats["bytes_reclaimed"] += size
                        if not dry_run:
                            res_file.unlink()
                except Exception as e:
                    logger.warning(f"Could not inspect/delete draft resume {res_file}: {e}")

        stats["total_files_deleted"] = (
            stats["logs_deleted"]
            + stats["scratch_files_deleted"]
            + stats["draft_resumes_deleted"]
            + stats["evidence_files_deleted"]
        )
        return stats
