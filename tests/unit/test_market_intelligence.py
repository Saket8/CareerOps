"""Unit tests for MarketIntelligenceAgent signal extraction and weekly intelligence."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories import JobRepository, MarketSignalRepository, ApplicationRepository
from src.agents.market_intelligence import MarketIntelligenceAgent
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


def test_market_intelligence_weekly_aggregation(db_session):
    job_repo = JobRepository(db_session)
    market_repo = MarketSignalRepository(db_session)
    app_repo = ApplicationRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)

    agent = MarketIntelligenceAgent(job_repo, market_repo, app_repo, candidate_truth)

    # Populate synthetic jobs with realistic market signals
    jobs_data = [
        ("j1", "Cloud Architect", "Oracle", "25-35 LPA", 25.0, True, "OCI, OKE, Terraform, GenAI"),
        ("j2", "AI Platform Architect", "Deloitte", "30-45 LPA", 30.0, True, "Kubernetes, MCP, LangChain, RAG"),
        ("j3", "Cloud Security Architect", "PwC", "Not Disclosed", None, False, "SAML, SSO, IAM, OCI, Prometheus"),
        ("j4", "Junior Engineer", "Wipro", "12-18 LPA", 12.0, True, "Linux, Python"),
    ]

    for j_id, title, comp, sal_raw, sal_min, disclosed, jd in jobs_data:
        job = JobListing(
            job_id=j_id,
            title=title,
            company=comp,
            location="Noida",
            url=f"https://naukri.com/job/{j_id}",
            salary=JobSalary(
                min_lpa=sal_min,
                is_disclosed=disclosed,
                eligibility=SalaryEligibility.REJECTED if (disclosed and sal_min < 20.0) else (
                    SalaryEligibility.ELIGIBLE if disclosed else SalaryEligibility.UNDISCLOSED
                ),
                raw_text=sal_raw,
            ),
            jd_text=jd,
            source_query="Cloud GenAI Architect",
        )
        job_repo.save_job(job)

    weekly_data = agent.generate_weekly_intelligence("2026-W38")

    assert weekly_data.total_jobs_analyzed == 4
    assert weekly_data.salary_stats["below_20_lpa_rejected"] == 1
    assert weekly_data.salary_stats["undisclosed_count"] == 1
    assert weekly_data.salary_stats["disclosed_count"] == 3

    # Check top skills
    skill_names = [s["name"] for s in weekly_data.recurring_skills]
    assert "OCI" in skill_names or "KUBERNETES" in skill_names

    # Check trends exist
    assert len(weekly_data.trends) > 0

    # Check recommendations
    assert len(weekly_data.recommended_search_queries) > 0
