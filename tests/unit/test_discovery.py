"""Unit tests for DiscoveryAgent deduplication and salary routing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories.job_repo import JobRepository
from src.naukri.browser_adapter import NaukriBrowserAdapter
from src.agents.discovery import DiscoveryAgent
from src.models.job import JobListing, JobStatus


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


@pytest.fixture
def test_mock_client():
    from unittest.mock import MagicMock
    from src.naukri.interface import BaseNaukriClient
    from src.utils.salary_parser import parse_salary

    client = MagicMock(spec=BaseNaukriClient)

    def mock_search(query, locations=None, experience_min=None, experience_max=None, limit=25):
        sample_jobs = [
            (
                "job_test_001",
                "Lead Cloud Architect",
                "Oracle India",
                "Bengaluru",
                "35-50 Lacs P.A.",
                "12-16 Yrs",
                "https://www.naukri.com/job-listings-job_test_001",
                "Lead enterprise cloud architecture on OCI.",
            ),
            (
                "job_test_002",
                "Principal GenAI Architect",
                "Deloitte",
                "Gurgaon",
                "40-60 LPA",
                "11-15 Yrs",
                "https://www.naukri.com/job-listings-job_test_002",
                "Enterprise GenAI architecture with LLMs and Kubernetes.",
            ),
            (
                "job_test_003",
                "Associate Cloud Engineer",
                "Wipro",
                "Noida",
                "12-18 Lacs P.A.",  # Below 20 LPA threshold (max 18 < 20)
                "5-8 Yrs",
                "https://www.naukri.com/job-listings-job_test_003",
                "Junior cloud administration.",
            ),
            (
                "job_test_004",
                "Enterprise Solutions Architect",
                "Accenture",
                "Bengaluru",
                "Not Disclosed",  # Undisclosed is eligible
                "12-18 Yrs",
                "https://www.naukri.com/job-listings-job_test_004",
                "Multi-cloud enterprise solutions architecture.",
            ),
        ]
        results = []
        for j_id, title, comp, loc, sal_raw, exp_raw, url, jd in sample_jobs:
            sal = parse_salary(sal_raw, min_threshold_lpa=20.0)
            listing = JobListing(
                job_id=j_id,
                title=title,
                company=comp,
                location=loc,
                salary=sal,
                experience_required=exp_raw,
                url=url,
                description_raw=jd,
                description_cleaned=jd,
                discovered_via_query=query,
                status=JobStatus.DISCOVERED,
            )
            results.append(listing)
        return results[:limit]

    client.search_jobs.side_effect = mock_search
    client.fetch_job_details.side_effect = lambda j: j
    return client


def test_discovery_agent_run(test_db_session, test_mock_client):
    job_repo = JobRepository(test_db_session)
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

    agent = DiscoveryAgent(test_mock_client, job_repo, config)
    result = agent.run_discovery(query_limit=10)

    assert result.total_found > 0
    assert result.salary_rejected >= 1  # Wipro job with 12-18 LPA
    assert result.salary_eligible >= 3  # Oracle, Deloitte, Accenture, PwC

    # Verify DB state
    all_jobs = job_repo.get_all_jobs()
    assert len(all_jobs) == result.salary_rejected + result.salary_eligible

    # Verify salary rejected job in DB has SALARY_REJECTED status
    rejected_jobs = job_repo.get_jobs_by_status(JobStatus.SALARY_REJECTED)
    assert len(rejected_jobs) >= 1
    assert any("12-18" in j.salary_raw_text for j in rejected_jobs)

    # Verify eligible jobs in DB have SALARY_ELIGIBLE status
    eligible_jobs = job_repo.get_jobs_by_status(JobStatus.SALARY_ELIGIBLE)
    assert len(eligible_jobs) >= 1

    # Rerunning discovery should skip duplicates
    second_run = agent.run_discovery(query_limit=10)
    assert second_run.duplicates_skipped > 0
    assert len(second_run.eligible_jobs) == 0  # No new jobs added
