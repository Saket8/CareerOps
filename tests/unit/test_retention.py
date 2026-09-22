"""Unit tests for database and storage retention engine."""

import os
import time
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.database.models import (
    Base,
    JobModel,
    ApplicationModel,
    ResumeVersionModel,
    AgentRunModel,
    MarketSignalModel,
)
from src.maintenance.retention_manager import RetentionManager, PROTECTED_JOB_STATUSES


@pytest.fixture
def temp_env():
    """Sets up a temporary isolated directory structure and SQLite database for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    db_path = temp_dir / "test_retention.sqlite"
    db_url = f"sqlite:///{db_path}"

    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    # Subdirectories
    (temp_dir / "logs").mkdir()
    (temp_dir / "artifacts" / "scratch").mkdir(parents=True)
    (temp_dir / "artifacts" / "evidence").mkdir(parents=True)
    (temp_dir / "resumes" / "master").mkdir(parents=True)
    (temp_dir / "resumes" / "generated").mkdir(parents=True)

    config = {
        "database": {"db_url": db_url},
        "retention": {
            "enabled": True,
            "unqualified_job_days": 14,
            "run_history_days": 90,
            "market_signal_days": 90,
            "evidence_scratch_days": 14,
            "draft_resume_days": 30,
            "log_days": 14,
            "auto_vacuum_db": True,
        },
    }

    yield temp_dir, config, Session, db_url

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_retention_protects_applied_jobs(temp_env):
    temp_dir, config, Session, db_url = temp_env
    session = Session()

    old_date = datetime.now(timezone.utc) - timedelta(days=45)

    # 1. Stale rejected job (Should be deleted)
    j_rejected = JobModel(
        job_id="job_rej_001",
        title="Unqualified Role",
        company="Old Corp",
        location="Remote",
        url="https://naukri.com/1",
        status="SALARY_REJECTED",
        created_at=old_date,
    )
    # 2. Old applied job (Must be PROTECTED)
    j_applied = JobModel(
        job_id="job_app_001",
        title="Principal Architect",
        company="Good Corp",
        location="Remote",
        url="https://naukri.com/2",
        status="APPLIED_CONFIRMED",
        created_at=old_date,
    )
    # 3. Old job with linked application (Must be PROTECTED even if status were DISCOVERED)
    j_linked = JobModel(
        job_id="job_linked_001",
        title="Solutions Architect",
        company="Tech Corp",
        location="Remote",
        url="https://naukri.com/3",
        status="DISCOVERED",
        created_at=old_date,
    )
    app_linked = ApplicationModel(
        application_id="app_001",
        job_id="job_linked_001",
        status="APPLIED_CONFIRMED",
        created_at=old_date,
    )

    session.add_all([j_rejected, j_applied, j_linked, app_linked])
    session.commit()
    session.close()

    mgr = RetentionManager(config, base_dir=temp_dir)
    db_stats = mgr.clean_database(dry_run=False)

    assert db_stats["jobs_purged"] == 1

    # Verify state in DB
    verify_session = Session()
    remaining_ids = {j.job_id for j in verify_session.query(JobModel).all()}
    assert "job_rej_001" not in remaining_ids
    assert "job_app_001" in remaining_ids
    assert "job_linked_001" in remaining_ids
    verify_session.close()


def test_retention_purges_old_runs_and_signals(temp_env):
    temp_dir, config, Session, db_url = temp_env
    session = Session()

    old_date = datetime.now(timezone.utc) - timedelta(days=120)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)

    old_run = AgentRunModel(run_id="run_old_1", start_time=old_date, status="SUCCESS")
    recent_run = AgentRunModel(run_id="run_new_1", start_time=recent_date, status="SUCCESS")

    old_signal = MarketSignalModel(signal_date="2025-01-01", item_name="Docker", category="skill", created_at=old_date)
    recent_signal = MarketSignalModel(signal_date="2026-09-01", item_name="OCI", category="platform", created_at=recent_date)

    session.add_all([old_run, recent_run, old_signal, recent_signal])
    session.commit()
    session.close()

    mgr = RetentionManager(config, base_dir=temp_dir)
    stats = mgr.clean_database(dry_run=False)

    assert stats["runs_purged"] == 1
    assert stats["signals_purged"] == 1

    verify_session = Session()
    assert verify_session.query(AgentRunModel).filter_by(run_id="run_old_1").first() is None
    assert verify_session.query(AgentRunModel).filter_by(run_id="run_new_1").first() is not None
    assert verify_session.query(MarketSignalModel).filter_by(item_name="Docker").first() is None
    assert verify_session.query(MarketSignalModel).filter_by(item_name="OCI").first() is not None
    verify_session.close()


def test_storage_cleanup_protects_evidence_and_deletes_stale_files(temp_env):
    temp_dir, config, Session, db_url = temp_env

    now_ts = time.time()
    old_mtime = now_ts - (25 * 86400)  # 25 days old
    recent_mtime = now_ts - (2 * 86400) # 2 days old

    # 1. Log files
    old_log = temp_dir / "logs" / "old.log"
    old_log.write_text("old logs")
    os.utime(old_log, (old_mtime, old_mtime))

    recent_log = temp_dir / "logs" / "recent.log"
    recent_log.write_text("recent logs")
    os.utime(recent_log, (recent_mtime, recent_mtime))

    # 2. Evidence files:
    # Protected: contains 'already_applied'
    proof_ev = temp_dir / "artifacts" / "evidence" / "123456_already_applied.png"
    proof_ev.write_bytes(b"image proof")
    os.utime(proof_ev, (old_mtime, old_mtime))

    # Unprotected scratch evidence
    temp_ev = temp_dir / "artifacts" / "evidence" / "inspect_temp_screen.png"
    temp_ev.write_bytes(b"temp screenshot")
    os.utime(temp_ev, (old_mtime, old_mtime))

    # 3. Master resume in resumes/master/ (Must NEVER be touched)
    master_docx = temp_dir / "resumes" / "master" / "Master_Resume.docx"
    master_docx.write_bytes(b"master resume")
    os.utime(master_docx, (old_mtime, old_mtime))

    # 4. Generated resumes
    draft_resume = temp_dir / "resumes" / "generated" / "Draft_Corp_20260101.docx"
    draft_resume.write_bytes(b"draft resume")
    os.utime(draft_resume, (now_ts - (40 * 86400), now_ts - (40 * 86400)))

    mgr = RetentionManager(config, base_dir=temp_dir)
    storage_stats = mgr.clean_storage(dry_run=False)

    assert storage_stats["logs_deleted"] == 1
    assert not old_log.exists()
    assert recent_log.exists()

    assert storage_stats["evidence_files_deleted"] == 1
    assert not temp_ev.exists()
    assert proof_ev.exists()  # Live proof screenshot strictly preserved!

    assert master_docx.exists()  # Master resume untouched
    assert not draft_resume.exists()  # Stale draft deleted


def test_retention_dry_run_does_not_delete(temp_env):
    temp_dir, config, Session, db_url = temp_env
    session = Session()

    old_date = datetime.now(timezone.utc) - timedelta(days=50)
    j_rejected = JobModel(
        job_id="job_dry_001",
        title="Old Rejection",
        company="Dry Run Corp",
        location="Remote",
        url="https://naukri.com/dry",
        status="REJECTED",
        created_at=old_date,
    )
    session.add(j_rejected)
    session.commit()
    session.close()

    old_log = temp_dir / "logs" / "dry_test.log"
    old_log.write_text("dry log")
    os.utime(old_log, (time.time() - (30 * 86400), time.time() - (30 * 86400)))

    mgr = RetentionManager(config, base_dir=temp_dir)
    res = mgr.apply_retention_policy(dry_run=True)

    assert res["status"] == "SUCCESS"
    assert res["dry_run"] is True
    assert res["database"]["jobs_purged"] == 1
    assert res["storage"]["logs_deleted"] == 1

    # In dry-run, items must still exist!
    verify_session = Session()
    assert verify_session.query(JobModel).filter_by(job_id="job_dry_001").first() is not None
    verify_session.close()
    assert old_log.exists()
