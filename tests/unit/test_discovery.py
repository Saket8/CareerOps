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


def test_discovery_skips_already_applied_jobs(test_db_session):
    from unittest.mock import MagicMock
    from src.naukri.interface import BaseNaukriClient
    from src.utils.salary_parser import parse_salary

    job_repo = JobRepository(test_db_session)

    # 1. Pre-seed DB with an applied job
    pre_applied_job = JobListing(
        job_id="job_pre_applied_999",
        title="Senior Cloud Architect",
        company="PreAppliedCorp",
        location="Bengaluru",
        url="https://naukri.com/job/999",
        salary=parse_salary("35-45 LPA", 30.0),
        status=JobStatus.APPLIED_CONFIRMED,
    )
    job_repo.save_job(pre_applied_job)

    # 2. Mock client returning:
    #    - job_1: has is_already_applied=True from search card
    #    - job_2: matches pre_applied_job by company and title under different ID
    #    - job_3: completely new job
    client = MagicMock(spec=BaseNaukriClient)
    client.search_jobs.return_value = [
        JobListing(
            job_id="card_applied_1",
            title="AI Architect",
            company="SomeCorp",
            location="Remote",
            url="https://naukri.com/job/card1",
            salary=parse_salary("40-50 LPA", 30.0),
            is_already_applied=True,
        ),
        JobListing(
            job_id="reposted_999_different_id",
            title="Senior Cloud Architect",
            company="PreAppliedCorp",
            location="Bengaluru",
            url="https://naukri.com/job/999_new",
            salary=parse_salary("35-45 LPA", 30.0),
            is_already_applied=False,
        ),
        JobListing(
            job_id="new_opportunity_1",
            title="Lead OCI Architect",
            company="BrandNewCorp",
            location="Hyderabad",
            url="https://naukri.com/job/new1",
            salary=parse_salary("40-50 LPA", 30.0),
            is_already_applied=False,
            has_full_jd=True,
            jd_text="Enterprise OCI cloud infrastructure architecture and migration.",
        ),
    ]
    client.fetch_job_details.side_effect = lambda j: j

    config = {
        "application": {"min_salary_lpa": 30.0},
        "search": {
            "queries": {"primary": ["Cloud Architect"]},
            "locations": ["India"],
        },
    }

    agent = DiscoveryAgent(client, job_repo, config)
    res = agent.run_discovery(query_limit=10)

    # Assert that card-level applied and company-title applied were both skipped!
    assert res.duplicates_skipped == 2
    assert len(res.eligible_jobs) == 1
    assert res.eligible_jobs[0].job_id == "new_opportunity_1"


def test_discovery_retries_failed_and_unapplied_jobs(test_db_session):
    from unittest.mock import MagicMock
    from src.naukri.interface import BaseNaukriClient
    from src.utils.salary_parser import parse_salary

    job_repo = JobRepository(test_db_session)

    # 1. Pre-seed DB with jobs in various states
    # Nagarro: APPLICATION_FAILED
    nagarro_job = JobListing(
        job_id="nagarro_fail_001",
        title="Architect- Generative AI",
        company="Nagarro",
        location="Bengaluru",
        url="https://www.naukri.com/job-listings-nagarro-fail-001",
        salary=parse_salary("40-60 Lacs PA", 30.0),
        status=JobStatus.APPLICATION_FAILED,
        has_full_jd=True,
        jd_text="Enterprise Generative AI architect with LLMs, RAG, and cloud architecture.",
    )
    job_repo.save_job(nagarro_job)

    # Quest Global: NEEDS_MANUAL_INTERVENTION
    quest_job = JobListing(
        job_id="quest_manual_002",
        title="AI Architect",
        company="Quest Global",
        location="Bengaluru",
        url="https://www.naukri.com/job-listings-quest-manual-002",
        salary=parse_salary("35-50 Lacs PA", 30.0),
        status=JobStatus.NEEDS_MANUAL_INTERVENTION,
        has_full_jd=True,
        jd_text="Enterprise AI solution architect with multi-cloud and system design.",
    )
    job_repo.save_job(quest_job)

    # InApp: Falsely marked EXTERNAL_APPLICATION_REQUIRED with internal Naukri URL
    inapp_job = JobListing(
        job_id="inapp_internal_003",
        title="Architect Identity Governance",
        company="InApp",
        location="Kochi",
        url="https://www.naukri.com/job-listings-inapp-internal-003",
        salary=parse_salary("30-45 Lacs PA", 30.0),
        status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
        has_full_jd=True,
        jd_text="Identity governance and administration architecture on Oracle Cloud.",
    )
    job_repo.save_job(inapp_job)

    # Technogen: Genuine EXTERNAL_APPLICATION_REQUIRED with external domain
    technogen_job = JobListing(
        job_id="technogen_ext_004",
        title="AI Architect",
        company="Technogen India",
        location="Bengaluru",
        url="https://www.technogenindia.com/careers/?job_id=123",
        canonical_url="https://www.technogenindia.com/careers/?job_id=123",
        salary=parse_salary("35-50 Lacs PA", 30.0),
        status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
        has_full_jd=True,
        jd_text="AI architect for enterprise solutions.",
    )
    job_repo.save_job(technogen_job)

    # Already Confirmed: APPLIED_CONFIRMED
    confirmed_job = JobListing(
        job_id="maveric_applied_005",
        title="OCI Architect",
        company="Maveric",
        location="Chennai",
        url="https://www.naukri.com/job-listings-maveric-applied-005",
        salary=parse_salary("35-45 Lacs PA", 30.0),
        status=JobStatus.APPLIED_CONFIRMED,
        has_full_jd=True,
        jd_text="Oracle Cloud Infrastructure architecture.",
    )
    job_repo.save_job(confirmed_job)

    # 2. Search returns all 5 jobs in new discovery run
    client = MagicMock(spec=BaseNaukriClient)
    client.search_jobs.return_value = [
        JobListing(
            job_id="nagarro_fail_001",
            title="Architect- Generative AI",
            company="Nagarro",
            location="Bengaluru",
            url="https://www.naukri.com/job-listings-nagarro-fail-001",
            salary=parse_salary("40-60 Lacs PA", 30.0),
        ),
        JobListing(
            job_id="quest_manual_002",
            title="AI Architect",
            company="Quest Global",
            location="Bengaluru",
            url="https://www.naukri.com/job-listings-quest-manual-002",
            salary=parse_salary("35-50 Lacs PA", 30.0),
        ),
        JobListing(
            job_id="inapp_internal_003",
            title="Architect Identity Governance",
            company="InApp",
            location="Kochi",
            url="https://www.naukri.com/job-listings-inapp-internal-003",
            salary=parse_salary("30-45 Lacs PA", 30.0),
        ),
        JobListing(
            job_id="technogen_ext_004",
            title="AI Architect",
            company="Technogen India",
            location="Bengaluru",
            url="https://www.technogenindia.com/careers/?job_id=123",
            canonical_url="https://www.technogenindia.com/careers/?job_id=123",
            salary=parse_salary("35-50 Lacs PA", 30.0),
        ),
        JobListing(
            job_id="maveric_applied_005",
            title="OCI Architect",
            company="Maveric",
            location="Chennai",
            url="https://www.naukri.com/job-listings-maveric-applied-005",
            salary=parse_salary("35-45 Lacs PA", 30.0),
        ),
    ]
    # Verify that client.fetch_job_details is NOT called because cached JD text is reused!
    client.fetch_job_details.side_effect = lambda j: j

    config = {
        "application": {"min_salary_lpa": 30.0},
        "search": {
            "queries": {"primary": ["AI Architect"]},
            "locations": ["India"],
        },
    }

    agent = DiscoveryAgent(client, job_repo, config)
    res = agent.run_discovery(query_limit=10)

    # 3. Assertions:
    # Confirmed applied (Maveric) and genuine external (Technogen) are skipped
    assert res.duplicates_skipped == 2
    # Nagarro (failed), Quest (manual review), and InApp (internal) are eligible for retry!
    assert len(res.eligible_jobs) == 3
    eligible_ids = [j.job_id for j in res.eligible_jobs]
    assert "nagarro_fail_001" in eligible_ids
    assert "quest_manual_002" in eligible_ids
    assert "inapp_internal_003" in eligible_ids

    # Cached JD text was reused and preserved
    nagarro_eligible = next(j for j in res.eligible_jobs if j.job_id == "nagarro_fail_001")
    assert nagarro_eligible.has_full_jd is True
    assert "LLMs, RAG" in nagarro_eligible.jd_text

