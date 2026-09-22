"""Unit tests for ApplicationAgent idempotency, quota limits, and safety boundaries."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories import JobRepository, ApplicationRepository, ResumeRepository
from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.agents.application import ApplicationAgent
from candidate.profile_extractor import get_candidate_truth
from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility
from src.models.score import JobScore


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_dry_run_application_flow(db_session, tmp_path):
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)
    resume_repo = ResumeRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)

    config = {
        "application": {"dry_run": True, "max_applications_per_day": 5}
    }

    mock_client = MagicMock(spec=BaseNaukriClient)
    from src.models.job import ApplicationRecord
    mock_client.submit_application.return_value = ApplicationRecord(
        application_id="app_test_1",
        job_id="job_app_1",
        status=JobStatus.APPLIED,
        dry_run=True,
        confirmation_reference="MOCK_CONF_12345",
    )

    agent = ApplicationAgent(mock_client, job_repo, app_repo, resume_repo, candidate_truth, config)

    job = JobListing(
        job_id="job_app_1",
        title="Principal Cloud Architect",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/app1",
        status=JobStatus.ATS_VALIDATED,
    )
    job_repo.save_job(job)

    score = JobScore(
        job_id="job_app_1",
        overall_score=88.0,
        architecture_score=90.0,
        cloud_score=90.0,
        oci_score=90.0,
        ai_score=85.0,
        agentic_ai_score=80.0,
        kubernetes_score=85.0,
        security_score=85.0,
        multicloud_score=80.0,
        experience_alignment=90.0,
        skill_alignment=88.0,
        passed_threshold=True,
    )

    docx = tmp_path / "resume.docx"
    pdf = tmp_path / "resume.pdf"
    docx.touch()
    pdf.touch()

    # 1. First run -> successful application
    outcome = agent.process_application(job, score, docx, pdf)
    assert outcome.success is True
    assert outcome.status == JobStatus.APPLIED
    assert app_repo.has_applied_to_job("job_app_1") is True

    # Verify DB job status
    db_job = job_repo.get("job_app_1")
    assert db_job.status == JobStatus.APPLIED.value

    # 2. Duplicate submission -> idempotency guard activates
    outcome_duplicate = agent.process_application(job, score, docx, pdf)
    assert outcome_duplicate.success is False
    assert "duplicate" in outcome_duplicate.reason.lower()


def test_safety_barrier_halts_gracefully(db_session, tmp_path):
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)
    resume_repo = ResumeRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)

    config = {"application": {"dry_run": True, "max_applications_per_day": 5}}

    # Mock client raising CAPTCHA barrier
    mock_client = MagicMock(spec=BaseNaukriClient)
    mock_client.submit_application.side_effect = SafetyBarrierException("CAPTCHA", "Cloudflare Turnstile challenge encountered")

    agent = ApplicationAgent(mock_client, job_repo, app_repo, resume_repo, candidate_truth, config)

    job = JobListing(
        job_id="job_captcha_1",
        title="GenAI Cloud Architect",
        company="SecurityCo",
        location="Noida",
        url="https://naukri.com/job/cap1",
        status=JobStatus.ATS_VALIDATED,
    )
    job_repo.save_job(job)

    score = JobScore(
        job_id="job_captcha_1",
        overall_score=85.0,
        architecture_score=85.0,
        cloud_score=85.0,
        oci_score=85.0,
        ai_score=85.0,
        agentic_ai_score=80.0,
        kubernetes_score=80.0,
        security_score=80.0,
        multicloud_score=80.0,
        experience_alignment=90.0,
        skill_alignment=85.0,
        passed_threshold=True,
    )

    docx = tmp_path / "resume.docx"
    pdf = tmp_path / "resume.pdf"
    docx.touch()
    pdf.touch()

    # Application attempt triggers safety boundary
    outcome = agent.process_application(job, score, docx, pdf)

    assert outcome.success is False
    assert outcome.status == JobStatus.BLOCKED
    assert "CAPTCHA" in outcome.reason

    # DB state must reflect BLOCKED
    db_job = job_repo.get("job_captcha_1")
    assert db_job.status == JobStatus.BLOCKED.value
