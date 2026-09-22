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
        status=JobStatus.APPLICATION_READY,
        dry_run=True,
        confirmation_detected=False,
        confirmation_reference=None,
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

    # 1. First run -> Prepared in dry run, zero dummy applies
    outcome = agent.process_application(job, score, docx, pdf)
    assert outcome.success is False  # Dry run never claims applied
    assert outcome.status == JobStatus.APPLICATION_READY
    assert app_repo.has_applied_to_job("job_app_1") is True

    # Verify DB job status stays APPLICATION_READY
    db_job = job_repo.get("job_app_1")
    assert db_job.status == JobStatus.APPLICATION_READY.value

    # 2. Duplicate submission -> idempotency guard activates
    outcome_duplicate = agent.process_application(job, score, docx, pdf)
    assert outcome_duplicate.success is False
    assert "duplicate" in outcome_duplicate.reason.lower()


def _make_score(job_id: str) -> JobScore:
    return JobScore(
        job_id=job_id,
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


def test_live_application_flow(db_session, tmp_path):
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)
    resume_repo = ResumeRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)

    config = {"application": {"dry_run": False, "max_applications_per_day": 5}}

    mock_client = MagicMock(spec=BaseNaukriClient)
    from src.models.job import ApplicationRecord
    mock_client.submit_application.return_value = ApplicationRecord(
        application_id="app_live_1",
        job_id="job_live_1",
        status=JobStatus.APPLIED_CONFIRMED,
        dry_run=False,
        confirmation_detected=True,
        confirmation_reference="NAUKRI_LIVE_98765",
    )

    agent = ApplicationAgent(mock_client, job_repo, app_repo, resume_repo, candidate_truth, config)

    job = JobListing(
        job_id="job_live_1",
        title="Principal Cloud Architect",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/live1",
        status=JobStatus.ATS_VALIDATED,
    )
    job_repo.save_job(job)

    score = _make_score("job_live_1")

    docx = tmp_path / "resume.docx"
    pdf = tmp_path / "resume.pdf"
    docx.touch()
    pdf.touch()

    outcome = agent.process_application(job, score, docx, pdf)
    assert outcome.success is True
    assert outcome.status == JobStatus.APPLIED_CONFIRMED
    db_job = job_repo.get("job_live_1")
    assert db_job.status == JobStatus.APPLIED_CONFIRMED.value


def test_dummy_confirmation_rejected(db_session, tmp_path):
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)
    resume_repo = ResumeRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)

    config = {"application": {"dry_run": False, "max_applications_per_day": 5}}

    mock_client = MagicMock(spec=BaseNaukriClient)
    from src.models.job import ApplicationRecord
    mock_client.submit_application.return_value = ApplicationRecord(
        application_id="app_dummy_1",
        job_id="job_dummy_1",
        status=JobStatus.APPLIED,
        dry_run=False,
        confirmation_detected=True,
        confirmation_reference="MOCK_CONF_FAKE123",
    )

    agent = ApplicationAgent(mock_client, job_repo, app_repo, resume_repo, candidate_truth, config)

    job = JobListing(
        job_id="job_dummy_1",
        title="Principal Cloud Architect",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/dummy1",
        status=JobStatus.ATS_VALIDATED,
    )
    job_repo.save_job(job)

    score = _make_score("job_dummy_1")
    docx = tmp_path / "resume.docx"
    pdf = tmp_path / "resume.pdf"
    docx.touch()
    pdf.touch()

    outcome = agent.process_application(job, score, docx, pdf)
    assert outcome.success is False
    assert outcome.status == JobStatus.APPLICATION_FAILED
    assert "dummy" in outcome.reason.lower()
    db_job = job_repo.get("job_dummy_1")
    assert db_job.status == JobStatus.APPLICATION_FAILED.value


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
    assert outcome.status in (JobStatus.BLOCKED, JobStatus.APPLICATION_BLOCKED)
    assert "CAPTCHA" in outcome.reason

    # DB state must reflect BLOCKED / APPLICATION_BLOCKED
    db_job = job_repo.get("job_captcha_1")
    assert db_job.status in (JobStatus.BLOCKED.value, JobStatus.APPLICATION_BLOCKED.value)
