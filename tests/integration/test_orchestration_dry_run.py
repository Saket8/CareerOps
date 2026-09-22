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

    orchestrator = Orchestrator(config=test_config, offline_mode=True)
    
    # Override directories for isolated testing
    # Run daily pipeline with forced weekly intelligence
    daily_report = orchestrator.run_daily_pipeline(force_weekly=True, query_limit=5)

    # 1. Pipeline execution verification
    assert daily_report.jobs_scanned > 0, "Jobs must be scanned"
    assert daily_report.salary_rejected >= 1, "Salary filter must reject jobs < 20 LPA"
    assert daily_report.qualified_jobs >= 1, "Eligible high-tier jobs must qualify"
    assert daily_report.resumes_generated >= 1, "ATS resumes must be generated for qualifying jobs"
    assert daily_report.applications_submitted >= 1, "Applications must be recorded in DRY_RUN mode"
    assert daily_report.interview_packs_generated >= 1, "Interview packs must be created for strong matches"

    # 2. Database state verification
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

        # Verify applied jobs
        applied = [j for j in all_jobs if j.status == JobStatus.APPLIED.value]
        assert len(applied) >= 1

        # Verify interview pack stored
        packs = interview_repo.get_all_packs()
        assert len(packs) >= 1

    # 3. Verify reports generated
    daily_reports = list(Path("reports/daily").glob(f"{daily_report.date}.*"))
    assert len(daily_reports) >= 2  # .md and .html
