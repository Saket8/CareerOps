"""End-to-end integration test verifying complete agent pipeline in DRY_RUN mode."""

import pytest
import shutil
from pathlib import Path
from src.agents.orchestrator import Orchestrator
from src.models.job import JobStatus
from src.database.connection import get_db_session
from src.database.repositories import JobRepository, ApplicationRepository, ResumeRepository, InterviewRepository


def test_end_to_end_dry_run_pipeline(tmp_path):
    test_db = tmp_path / "test_career_agent.sqlite"
    resumes_dir = tmp_path / "resumes" / "generated"
    interviews_dir = tmp_path / "interviews"
    reports_daily_dir = tmp_path / "reports" / "daily"
    reports_weekly_dir = tmp_path / "reports" / "weekly"

    test_config = {
        "database": {"db_url": f"sqlite:///{test_db}"},
        "application": {
            "match_threshold": 75.0,
            "high_match_threshold": 85.0,
            "min_salary_lpa": 20.0,
            "dry_run": True,
            "max_applications_per_day": 10,
        },
        "resume": {
            "output_dir": str(resumes_dir),
            "generate_pdf": True,
            "generate_docx": True,
        },
        "reporting": {
            "daily_dir": str(reports_daily_dir),
            "weekly_dir": str(reports_weekly_dir),
        },
        "email": {"enabled": False},
        "search": {
            "queries": {
                "primary": ["Cloud GenAI Architect"],
                "oci": ["OCI AI Architect"],
            },
            "locations": ["Noida", "Bengaluru"],
            "experience_range": {"min_years": 10, "max_years": 16},
        },
    }

    from unittest.mock import patch
    from src.naukri.playwright_adapter import PlaywrightBrowserAdapter
    from src.models.job import JobListing
    from src.utils.salary_parser import parse_salary

    def mock_search(self, query, locations=None, experience_min=None, experience_max=None, limit=25):
        sample_jobs = [
            (
                "job_test_001",
                "Principal Cloud Solutions Architect - GenAI Platform",
                "Oracle India",
                "Bengaluru",
                "35-50 Lacs P.A.",
                "12-16 Yrs",
                "https://www.naukri.com/job-listings-job_test_001",
                """We are seeking a Principal Cloud Solutions Architect with deep expertise in OCI (Oracle Cloud Infrastructure),
                Kubernetes (OKE), and GenAI platform architectures. Responsibilities include architecting enterprise landing zones,
                implementing RAG architecture with local LLMs and LangChain, Model Context Protocol (MCP), securing AI workloads with
                OCI IAM and SAML federation, and automating with Terraform. 12+ years experience required.""",
            ),
            (
                "job_test_002",
                "Lead AI Solutions Architect",
                "Deloitte",
                "Gurgaon",
                "40-60 LPA",
                "11-15 Yrs",
                "https://www.naukri.com/job-listings-job_test_002",
                """Design enterprise GenAI architectures, LLMOps pipelines, Agentic workflows using LangChain, LangGraph, and Kubernetes.
                Lead multi-cloud security, vector databases, and scalable inference serving on OCI and AWS.""",
            ),
            (
                "job_test_003",
                "Associate Cloud Engineer",
                "Wipro",
                "Noida",
                "15-22 Lacs P.A.",  # Below 20 LPA threshold
                "5-8 Yrs",
                "https://www.naukri.com/job-listings-job_test_003",
                "Junior cloud administration.",
            ),
            (
                "job_test_004",
                "Enterprise Cloud Solutions Architect",
                "Accenture",
                "Bengaluru",
                "Not Disclosed",
                "12-18 Yrs",
                "https://www.naukri.com/job-listings-job_test_004",
                """Multi-cloud enterprise solutions architecture on OCI and AWS.
                Enterprise landing zones, Kubernetes clusters, and infrastructure automation.""",
            ),
        ]
        results = []
        for j_id, title, comp, loc, sal_raw, exp_raw, url, jd in sample_jobs:
            sal = parse_salary(sal_raw, min_threshold_lpa=30.0)
            listing = JobListing(
                job_id=j_id,
                title=title,
                company=comp,
                location=loc,
                salary=sal,
                experience_required=exp_raw,
                url=url,
                jd_text=jd,
                description_raw=jd,
                description_cleaned=jd,
                discovered_via_query=query,
                status=JobStatus.DISCOVERED,
            )
            results.append(listing)
        return results[:limit]

    with patch.object(PlaywrightBrowserAdapter, "search_jobs", mock_search):
        orchestrator = Orchestrator(config=test_config, offline_mode=True)
        daily_report = orchestrator.run_daily_pipeline(force_weekly=True, query_limit=5)

    # 1. Pipeline execution verification
    assert daily_report.jobs_scanned > 0, "Jobs must be scanned"
    assert daily_report.salary_rejected >= 1, "Salary filter must reject jobs < 30 LPA"
    assert daily_report.qualified_jobs >= 1, "Eligible high-tier jobs must qualify"
    assert daily_report.resumes_generated >= 1, "ATS resumes must be generated for qualifying jobs"
    assert daily_report.applications_confirmed == 0, "Zero dummy applies confirmed in DRY_RUN"
    assert daily_report.interview_packs_generated >= 1, "Interview packs must be created for strong matches"

    # 2. Database state verification: Zero dummy applies stored
    with get_db_session(f"sqlite:///{test_db}") as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        resume_repo = ResumeRepository(session)
        interview_repo = InterviewRepository(session)

        all_jobs = job_repo.get_all_jobs()
        assert len(all_jobs) > 0
        assert len(all_jobs) <= daily_report.jobs_scanned

        # Verify salary rejected job
        rejected = [j for j in all_jobs if j.status == JobStatus.SALARY_REJECTED.value]
        assert len(rejected) >= 1
        assert "15-22" in rejected[0].salary_raw_text

        # Strict Zero-Dummy Invariant: In DRY_RUN, zero jobs should be marked APPLIED
        applied = [j for j in all_jobs if j.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value)]
        assert len(applied) == 0, "Zero dummy applies invariant: No job must reach APPLIED in DRY_RUN mode"

        # Prepared jobs must remain in APPLICATION_READY
        ready_jobs = [j for j in all_jobs if j.status == JobStatus.APPLICATION_READY.value]
        assert len(ready_jobs) >= 1, "Prepared applications must remain APPLICATION_READY"

        # Verify interview pack stored
        packs = interview_repo.get_all_packs()
        assert len(packs) >= 1

    # 3. Verify reports generated
    daily_reports = list(Path(reports_daily_dir).glob(f"{daily_report.date}*"))
    assert len(daily_reports) >= 2  # .md and .html
