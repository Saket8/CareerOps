"""Unit tests for PostRunHealerAgent and autonomous self-healing stabilization."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, JobModel, ApplicationModel, JobScoreModel, ApplicationFailureAnalysisModel
from src.models.job import JobStatus, ApplicationMethod, JobListing, JobSalary, SalaryEligibility
from src.models.score import JobScore
from src.agents.post_run_healer import PostRunHealerAgent
from src.utils.screening_knowledge import get_screening_knowledge_base
from candidate.profile_extractor import get_candidate_truth


@pytest.fixture
def db_session():
    """In-memory SQLite database session for unit testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_healer_environment_sanitization(tmp_path):
    """Verifies that stale locks and system checks operate cleanly."""
    fake_lock = tmp_path / "fake_lock.lock"
    fake_lock.touch()

    with patch("src.agents.post_run_healer.LOCK_FILE", fake_lock):
        healer = PostRunHealerAgent(offline_mode=True)
        res = healer.sanitize_system_environment()
        assert "memory_available_mb" in res
        assert "swap_used_mb" in res
        assert res["healthy"] is True


def test_healer_log_auditing(tmp_path):
    """Verifies that error patterns, durations, and exit codes are extracted from log lines."""
    fake_cron = tmp_path / "cron_run.log"
    fake_cron.write_text(
        "[2026-10-23 03:23:00 UTC] CareerOps Weekday Pipeline Started\n"
        "[2026-10-23 04:24:00 UTC] CareerOps Run Completed in 3660s with exit code 0\n"
    )

    fake_agent = tmp_path / "career_agent.log"
    fake_agent.write_text(
        "2026-10-23 03:30:00 [ERROR] Locator.click: Timeout 30000ms exceeded. <dialog data-testid='popover-floating'> intercepts pointer events\n"
        "2026-10-23 03:35:00 [WARNING] Modal stalled at step 2: Required screening field unanswered (Salary Expectations)\n"
        "2026-10-23 03:40:00 [INFO] Chatbot Turn 3: Recruiter screening could not be answered because no matching option or input was available\n"
    )

    with patch("src.agents.post_run_healer.CRON_LOG_FILE", fake_cron), \
         patch("src.agents.post_run_healer.AGENT_LOG_FILE", fake_agent):
        healer = PostRunHealerAgent(offline_mode=True)
        audit = healer.audit_run_logs()

        assert audit["last_run_duration_sec"] == 3660
        assert audit["last_run_exit_code"] == 0
        assert "LINKEDIN_POPOVER_INTERCEPTION" in audit["detected_issues"]
        assert "LINKEDIN_FIELD_VALIDATION_ERROR" in audit["detected_issues"]
        assert "NAUKRI_SCREENING_DROPOUT" in audit["detected_issues"]


def test_healer_knowledge_base_auto_learning(db_session):
    """Verifies that diagnosing LinkedIn popover and Naukri notice period auto-updates knowledge base."""
    truth = get_candidate_truth(refresh=False)
    kb = get_screening_knowledge_base()

    # Pre-condition: check knowledge base resolution
    ans_notice = kb.get_answer("What is your official notice period?")
    assert ans_notice == "90 Days"

    # Test learning custom question
    kb.learn_answer("Are you available for 24/7 oncall support?", "Yes")
    assert kb.get_answer("Are you available for 24/7 oncall support?") == "Yes"

    # Test location synonym
    kb.learn_location_synonym("noida", "cyber city gurugram")
    terms = kb.get_compatible_location_terms("noida")
    assert "cyber city gurugram" in terms


def test_healer_database_audit_and_catchup_queue(db_session):
    """Verifies quota shortfall calculation and catchup candidate prioritization."""
    # Seed today's confirmed applications
    today_dt = datetime.now(timezone.utc)
    app1 = ApplicationModel(
        application_id="app_conf_01",
        job_id="job_01",
        status=JobStatus.APPLIED_CONFIRMED.value,
        started_at=today_dt,
        submitted_at=today_dt,
    )
    job1 = JobModel(
        job_id="job_01",
        title="Cloud Architect",
        company="Oracle",
        location="Noida",
        url="https://test.naukri.com/job/01",
        status=JobStatus.APPLIED_CONFIRMED.value,
    )
    db_session.add_all([app1, job1])

    # Seed failed/retry-eligible application
    app2 = ApplicationModel(
        application_id="app_fail_02",
        job_id="job_02",
        status=JobStatus.READY_FOR_RETRY.value,
        started_at=today_dt,
        failure_reason="Timeout 30000ms exceeded: pointer events intercepted",
    )
    job2 = JobModel(
        job_id="job_02",
        title="Principal AI Architect",
        company="Capgemini",
        location="Noida",
        url="https://test.naukri.com/job/02",
        source_platform="naukri",
        status=JobStatus.READY_FOR_RETRY.value,
    )
    score2 = JobScoreModel(job_id="job_02", overall_score=88.5)
    db_session.add_all([app2, job2, score2])
    db_session.commit()

    healer = PostRunHealerAgent(offline_mode=True)
    audit = healer.audit_database_state(db_session)

    assert audit["confirmed_today"] == 1
    assert audit["shortfall"] == healer.target_quota - 1
    assert audit["quota_achieved"] is False


def test_healer_markdown_report_generation():
    """Verifies markdown report generation contains executive sections and health indicators."""
    healer = PostRunHealerAgent(offline_mode=True)

    env_report = {"memory_available_mb": 420, "swap_used_mb": 310, "zombie_browsers_killed": 2, "stale_lock_cleared": False}
    log_audit = {"last_run_duration_sec": 3600, "last_run_exit_code": 0, "detected_issues": ["LINKEDIN_POPOVER_INTERCEPTION"]}
    db_audit = {"confirmed_today": 8, "target_quota": 20, "shortfall": 12, "quota_achieved": False}
    catchup_result = {"initial_confirmed": 8, "final_confirmed": 14, "attempted": 6, "confirmed": 6, "quota_met": False, "details": []}

    md = healer.generate_health_report_markdown(
        env_report=env_report,
        log_audit=log_audit,
        db_audit=db_audit,
        diagnostics=[],
        catchup_result=catchup_result,
    )

    assert "# 🩺 AUTONOMOUS POST-RUN HEALTH & HEALING REPORT" in md
    assert "Daily Confirmed Quota Target:" in md
    assert "**VPS Memory Available:** `420 MB`" in md
    assert "**Zombie Browser Processes Terminated:** `2`" in md
    assert "LINKEDIN_POPOVER_INTERCEPTION" in md
