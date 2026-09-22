"""Unit tests for DiscoveryAgent deduplication and salary routing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories.job_repo import JobRepository
from src.naukri.browser_adapter import NaukriBrowserAdapter
from src.agents.discovery import DiscoveryAgent
from src.models.job import JobStatus


@pytest.fixture
def test_db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_discovery_agent_run(test_db_session):
    job_repo = JobRepository(test_db_session)
    adapter = NaukriBrowserAdapter(offline_mode=True)
    config = {
        "application": {"min_salary_lpa": 20.0},
        "search": {
            "queries": {
                "primary": ["Cloud GenAI Architect"],
                "oci": ["OCI AI Architect"],
            },
            "locations": ["Noida", "Bengaluru"],
        },
    }

    agent = DiscoveryAgent(adapter, job_repo, config)
    result = agent.run_discovery(query_limit=10)

    assert result.total_found > 0
    assert result.salary_rejected >= 1  # Wipro job with 15-22 LPA
    assert result.salary_eligible >= 3  # Oracle, Deloitte, Accenture, PwC

    # Verify DB state
    all_jobs = job_repo.get_all_jobs()
    assert len(all_jobs) == result.salary_rejected + result.salary_eligible

    # Verify salary rejected job in DB has SALARY_REJECTED status
    rejected_jobs = job_repo.get_jobs_by_status(JobStatus.SALARY_REJECTED)
    assert len(rejected_jobs) >= 1
    assert any("15-22" in j.salary_raw_text for j in rejected_jobs)

    # Verify eligible jobs in DB have SALARY_ELIGIBLE status
    eligible_jobs = job_repo.get_jobs_by_status(JobStatus.SALARY_ELIGIBLE)
    assert len(eligible_jobs) >= 1

    # Rerunning discovery should skip duplicates
    second_run = agent.run_discovery(query_limit=10)
    assert second_run.duplicates_skipped > 0
    assert len(second_run.eligible_jobs) == 0  # No new jobs added
