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


def test_junior_intern_job_experience_gate(db_session):
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {"application": {"match_threshold": 75.0, "high_match_threshold": 85.0}}
    agent = QualificationAgent(job_repo, candidate_truth, config)

    # NotionAce-like intern job: 0-0 years experience, cloud keywords
    intern_job = JobListing(
        job_id="job_intern_1",
        title="Cloud Engineer Intern",
        company="NotionAce Solutions",
        location="Remote",
        url="https://naukri.com/job/intern1",
        experience_min=0.0,
        experience_max=0.0,
        experience_raw="0-0 Yrs",
        jd_text="Looking for enthusiastic Cloud Engineer Interns trained in AWS, Azure, GCP, or OCI. Knowledge of Linux and scripting.",
        has_full_jd=True,
    )
    job_repo.save_job(intern_job)

    score, evidence = agent.evaluate_job(intern_job)

    assert score.passed_threshold is False
    assert score.overall_score <= 65.0
    assert intern_job.status == JobStatus.REJECTED
    assert any("junior/entry-level experience" in g for g in score.gaps)


def test_genai_architect_skill_first_qualification(db_session):
    """Test that a pure GenAI Architect role qualifies on AI/Architecture without being penalized for lacking K8s/Exadata."""
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {"application": {"match_threshold": 70.0, "high_match_threshold": 85.0}}
    agent = QualificationAgent(job_repo, candidate_truth, config)

    genai_job = JobListing(
        job_id="job_genai_arch_1",
        title="GenAI Architect",
        company="Tech Mahindra",
        location="Bengaluru",
        url="https://naukri.com/job/genai1",
        experience_min=8.0,
        experience_max=15.0,
        experience_raw="8-15 Yrs",
        jd_text="""
        Looking for a GenAI Architect with deep expertise in Large Language Models (LLMs), RAG systems,
        LangChain, Prompt Engineering, agentic workflows, fine-tuning, and enterprise architecture design.
        Candidate will design generative AI solutions, integrate local and cloud models, and lead architecture teams.
        """,
        has_full_jd=True,
    )
    job_repo.save_job(genai_job)

    score, evidence = agent.evaluate_job(genai_job)

    # Core AI skill is high (>=80%) and title matches target role -> must qualify with high score
    assert score.passed_threshold is True
    assert score.overall_score >= 80.0
    assert genai_job.status in (JobStatus.QUALIFIED, JobStatus.HIGH_MATCH)
    assert "GENAI_ARCHITECTURE" in score.categories


def test_snowflake_databricks_domain_gate_rejection(db_session):
    """Test that Snowflake and Databricks architect roles are rejected by Domain Gate."""
    job_repo = JobRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {"application": {"match_threshold": 70.0, "high_match_threshold": 85.0}}
    agent = QualificationAgent(job_repo, candidate_truth, config)

    snowflake_job = JobListing(
        job_id="job_snowflake_1",
        title="Snowflake Architect with Cortex AI",
        company="Genpact",
        location="Noida",
        url="https://naukri.com/job/snow1",
        experience_min=10.0,
        experience_max=16.0,
        experience_raw="10-16 Yrs",
        jd_text="Looking for Snowflake Architect with deep experience in Snowflake data warehouse, Cortex AI, Snowpark, and SQL.",
        has_full_jd=True,
    )
    job_repo.save_job(snowflake_job)

    databricks_job = JobListing(
        job_id="job_databricks_1",
        title="RSA Databricks Architect",
        company="Celebal Technologies",
        location="Jaipur",
        url="https://naukri.com/job/data1",
        experience_min=10.0,
        experience_max=15.0,
        experience_raw="10-15 Yrs",
        jd_text="Looking for Databricks Architect with PySpark, Delta Lake, Lakehouse architecture, and Unity Catalog.",
        has_full_jd=True,
    )
    job_repo.save_job(databricks_job)

    score_s, _ = agent.evaluate_job(snowflake_job)
    score_d, _ = agent.evaluate_job(databricks_job)

    assert score_s.passed_threshold is False
    assert snowflake_job.status == JobStatus.REJECTED
    assert any("Snowflake/Databricks specialization" in g for g in score_s.gaps)

    assert score_d.passed_threshold is False
    assert databricks_job.status == JobStatus.REJECTED
    assert any("Snowflake/Databricks specialization" in g for g in score_d.gaps)



