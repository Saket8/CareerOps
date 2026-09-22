"""Unit tests for database repositories and models."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories import (
    JobRepository,
    ApplicationRepository,
    ResumeRepository,
    InterviewRepository,
    MarketSignalRepository,
    RunRepository,
)
from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility, ApplicationRecord
from src.models.score import JobScore, JobEvidence


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


def test_job_repo_crud(db_session):
    repo = JobRepository(db_session)
    job = JobListing(
        job_id="test_job_123",
        title="Principal Cloud Architect",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/123",
        salary=JobSalary(
            min_lpa=25.0,
            max_lpa=35.0,
            is_disclosed=True,
            eligibility=SalaryEligibility.ELIGIBLE,
            raw_text="25-35 LPA",
        ),
        status=JobStatus.DISCOVERED,
    )
    saved = repo.save_job(job)
    assert saved.job_id == "test_job_123"
    assert repo.exists("test_job_123") is True
    assert repo.exists_by_company_and_title("Oracle", "Principal Cloud Architect") is True

    # Update status
    repo.update_status("test_job_123", JobStatus.QUALIFIED)
    updated = repo.get("test_job_123")
    assert updated.status == JobStatus.QUALIFIED.value


def test_job_score_and_evidence(db_session):
    job_repo = JobRepository(db_session)
    job = JobListing(
        job_id="test_score_1",
        title="GenAI Platform Architect",
        company="TechCorp",
        location="Noida",
        url="https://naukri.com/job/456",
    )
    job_repo.save_job(job)

    score = JobScore(
        job_id="test_score_1",
        overall_score=88.5,
        architecture_score=90.0,
        cloud_score=85.0,
        oci_score=95.0,
        ai_score=85.0,
        agentic_ai_score=80.0,
        kubernetes_score=90.0,
        security_score=85.0,
        multicloud_score=80.0,
        experience_alignment=95.0,
        skill_alignment=88.0,
        passed_threshold=True,
        match_reasons=["High OCI & Kubernetes alignment", "Strong architecture score"],
        strengths=["OCI", "Kubernetes", "GenAI"],
        gaps=[],
        categories=["CLOUD_ARCHITECTURE", "GENAI_ARCHITECTURE"],
    )
    saved_score = job_repo.save_score(score)
    assert saved_score.overall_score == 88.5

    evidence = JobEvidence(
        job_id="test_score_1",
        observed_facts=["Candidate has 12 yrs exp", "JD asks for OKE and Terraform"],
        inferred_signals=["Role requires enterprise cloud transformation"],
        generated_actions=["Prepare OKE multi-tenant isolation questions"],
        skills_found=["OCI", "OKE", "Terraform", "GenAI"],
        tools_found=["Helm", "Docker", "Prometheus"],
        architecture_patterns=["Air-gapped landing zone"],
    )
    saved_evidence = job_repo.save_evidence(evidence)
    assert len(saved_evidence.skills_found) == 4


def test_application_repo_and_events(db_session):
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)

    job = JobListing(
        job_id="job_app_1",
        title="Cloud Architect",
        company="GlobalInc",
        location="Remote",
        url="https://naukri.com/job/789",
    )
    job_repo.save_job(job)

    record = ApplicationRecord(
        application_id="app_1",
        job_id="job_app_1",
        status=JobStatus.APPLIED,
        dry_run=True,
    )
    saved_app = app_repo.record_application(record)
    assert saved_app.application_id == "app_1"
    assert app_repo.has_applied_to_job("job_app_1") is True

    event = app_repo.log_event("app_1", "APPLICATION_READY", "APPLIED", "Dry run simulation")
    assert event.from_status == "APPLICATION_READY"
    assert event.to_status == "APPLIED"


def test_run_repo(db_session):
    run_repo = RunRepository(db_session)
    run = run_repo.start_run("run_101", run_type="daily", dry_run=True)
    assert run.status == "RUNNING"

    finished = run_repo.finish_run("run_101", status="SUCCESS", jobs_scanned=50, qualified_jobs=10)
    assert finished.status == "SUCCESS"
    assert finished.jobs_scanned == 50
