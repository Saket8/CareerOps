"""Unit tests for QualificationAgent multi-dimensional scoring and evidence extraction."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories.job_repo import JobRepository
from src.agents.qualification import QualificationAgent
from candidate.profile_extractor import get_candidate_truth
from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility


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


def test_high_match_job_scoring(db_session):
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {
        "application": {"match_threshold": 75.0, "high_match_threshold": 85.0}
    }
    agent = QualificationAgent(job_repo, candidate_truth, config)

    high_match_job = JobListing(
        job_id="job_high_1",
        title="Principal Cloud Architect - GenAI Platform",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/high1",
        salary=JobSalary(min_lpa=30.0, max_lpa=45.0, is_disclosed=True, eligibility=SalaryEligibility.ELIGIBLE),
        jd_text="""
        We are seeking a Principal Cloud Solutions Architect with deep expertise in OCI (Oracle Cloud Infrastructure),
        Kubernetes (OKE), and GenAI platform architectures. Responsibilities include architecting enterprise landing zones,
        implementing RAG architecture with local LLMs and LangChain, Model Context Protocol (MCP), securing AI workloads with
        OCI IAM and SAML federation, and automating with Terraform. 12+ years experience required.
        """,
    )
    job_repo.save_job(high_match_job)

    score, evidence = agent.evaluate_job(high_match_job)

    assert score.overall_score >= 85.0
    assert score.passed_threshold is True
    assert high_match_job.status == JobStatus.HIGH_MATCH
    assert "CLOUD_ARCHITECTURE" in score.categories
    assert "GENAI_ARCHITECTURE" in score.categories
    assert len(score.strengths) >= 3

    # Verify Evidence distinction
    assert len(evidence.observed_facts) > 0
    assert len(evidence.inferred_signals) > 0
    assert len(evidence.generated_actions) > 0
    assert any("OCI" in f for f in evidence.skills_found)


def test_irrelevant_job_rejection(db_session):
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {"application": {"match_threshold": 75.0, "high_match_threshold": 85.0}}
    agent = QualificationAgent(job_repo, candidate_truth, config)

    frontend_job = JobListing(
        job_id="job_frontend_1",
        title="Frontend React UI Developer",
        company="WebStudio",
        location="Remote",
        url="https://naukri.com/job/front1",
        jd_text="Requires CSS, HTML, React.js, Tailwind, Vue.js, Figma wireframing for marketing website.",
    )
    job_repo.save_job(frontend_job)

    score, evidence = agent.evaluate_job(frontend_job)

    assert score.overall_score < 75.0
    assert score.passed_threshold is False
    assert frontend_job.status == JobStatus.REJECTED


def test_current_employer_blocked(db_session):
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {
        "application": {"match_threshold": 75.0, "high_match_threshold": 85.0},
        "safety": {"blocked_companies": ["Cognizant", "CTS", "Cognizant Technology Solutions"]},
    }
    agent = QualificationAgent(job_repo, candidate_truth, config)

    cognizant_job = JobListing(
        job_id="job_cognizant_1",
        title="Principal Cloud Architect",
        company="Cognizant Technology Solutions",
        location="Noida",
        url="https://naukri.com/job/cts1",
        jd_text="Enterprise OCI Cloud Architect with Terraform and Kubernetes.",
    )
    job_repo.save_job(cognizant_job)

    score, evidence = agent.evaluate_job(cognizant_job)

    assert score.passed_threshold is False
    assert score.overall_score == 0.0
    assert cognizant_job.status == JobStatus.REJECTED
    assert "Current employer is blocked" in score.gaps[0]


def test_missing_full_jd_confidence_gating(db_session):
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {"application": {"match_threshold": 75.0, "high_match_threshold": 85.0}}
    agent = QualificationAgent(job_repo, candidate_truth, config)

    # Job has senior OCI keywords in title and search query, but NO full JD text (<50 chars)
    card_only_job = JobListing(
        job_id="job_card_only_1",
        title="Senior Principal OCI Cloud Architect - Enterprise Landing Zones",
        company="Global Enterprise",
        location="Bengaluru",
        url="https://naukri.com/job/card1",
        source_query="Oracle Cloud Infrastructure OCI Architect",
        jd_text="Brief snippet",  # Less than 50 chars
        has_full_jd=False,
    )
    job_repo.save_job(card_only_job)

    score, evidence = agent.evaluate_job(card_only_job)

    # Must be confidence-gated below match threshold
    assert score.overall_score <= 74.0
    assert score.passed_threshold is False
    assert any("Full JD text unavailable" in g for g in score.gaps)
    assert any("Preliminary card metadata score" in r for r in score.match_reasons)

