"""Unit tests for consolidated daily interview intelligence briefing and external opportunities reporting."""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
import pytest

from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility
from src.models.score import JobScore, JobEvidence
from src.models.report import DailyReportData, TopApplicationItem
from src.models.candidate import CandidateTruth, CandidateProfile
from src.database.repositories.interview_repo import InterviewRepository
from src.agents.interview_agent import InterviewAgent
from src.agents.reporting import ReportingAgent
from src.email_service.smtp_mailer import SmtpMailer
from candidate.profile_extractor import get_candidate_truth


@pytest.fixture
def mock_candidate_truth():
    return get_candidate_truth()


@pytest.fixture
def sample_matched_jobs():
    j1 = JobListing(
        job_id="job_oci_001",
        title="Principal OCI Cloud Architect",
        company="Enterprise Cloud Corp",
        location="Pan India",
        salary=JobSalary(min_lpa=35.0, max_lpa=55.0, is_disclosed=True, raw_text="₹35 - 55 LPA"),
        url="https://www.naukri.com/job-listings-oci-architect",
        jd_text="Enterprise OCI architecture, DRG transit routing, private OKE, FSS storage, Terraform modules.",
    )
    s1 = JobScore(
        job_id="job_oci_001",
        overall_score=94.0,
        architecture_score=95.0,
        cloud_score=95.0,
        oci_score=98.0,
        ai_score=85.0,
        agentic_ai_score=80.0,
        kubernetes_score=92.0,
        security_score=94.0,
        multicloud_score=90.0,
        experience_alignment=95.0,
        skill_alignment=96.0,
        passed_threshold=True,
        strengths=["Deep OCI landing zone expertise", "Private OKE platforms", "6 Oracle Certifications"],
        gaps=[],
    )
    e1 = JobEvidence(job_id="job_oci_001", observed_facts=["Requires 10+ yrs enterprise cloud architecture"])

    j2 = JobListing(
        job_id="job_ai_002",
        title="Principal Agentic AI & GenAI Platform Architect",
        company="Global AI Systems",
        location="Pan India",
        salary=JobSalary(is_disclosed=False, raw_text="Not Disclosed"),
        url="https://www.naukri.com/job-listings-ai-architect",
        jd_text="Agentic AI frameworks, Model Context Protocol (MCP), LangChain, local LLM orchestration, zero-trust cloud.",
    )
    s2 = JobScore(
        job_id="job_ai_002",
        overall_score=91.0,
        architecture_score=90.0,
        cloud_score=88.0,
        oci_score=85.0,
        ai_score=95.0,
        agentic_ai_score=96.0,
        kubernetes_score=88.0,
        security_score=90.0,
        multicloud_score=85.0,
        experience_alignment=92.0,
        skill_alignment=94.0,
        passed_threshold=True,
        strengths=["Model Context Protocol (MCP)", "LangChain / ChatOps", "Air-gapped LLM deployments"],
        gaps=[],
    )
    e2 = JobEvidence(job_id="job_ai_002", observed_facts=["Requires MCP, LangChain, local LLMOps"])

    return [(j1, s1, e1), (j2, s2, e2)]


def test_consolidated_daily_briefing_generation(tmp_path, mock_candidate_truth, sample_matched_jobs):
    reports_dir = tmp_path / "reports" / "interviews"
    agent = InterviewAgent(
        interview_repo=None,
        candidate_truth=mock_candidate_truth,
        base_dir=tmp_path / "interviews",
        reports_dir=reports_dir,
    )

    date_str = "2026-09-22"
    docx_path, pdf_path, html_summary = agent.generate_consolidated_daily_briefing(sample_matched_jobs, date_str)

    # Verify DOCX was created and is non-empty
    assert docx_path.exists()
    assert docx_path.stat().st_size > 5000
    assert docx_path.name == f"Daily_Interview_Intelligence_{date_str}.docx"

    # Verify HTML summary contains both companies
    assert "Enterprise Cloud Corp" in html_summary
    assert "Global AI Systems" in html_summary
    assert "CareerOps — Daily Consolidated Interview Intelligence Briefing" in html_summary


def test_smtp_mailer_attachment_support(tmp_path):
    from unittest.mock import patch, MagicMock

    test_pdf = tmp_path / "test_report.pdf"
    test_pdf.write_bytes(b"%PDF-1.4 mock pdf content")

    test_docx = tmp_path / "test_report.docx"
    test_docx.write_bytes(b"mock docx content")

    config = {
        "email": {
            "enabled": True,
            "smtp_server": "smtp.gmail.com",
            "default_recipient": "sauravskt8@gmail.com",
        }
    }

    mailer = SmtpMailer(config)
    mailer.username = "test_user@example.com"
    mailer.password = "test_pass"

    with patch("smtplib.SMTP") as mock_smtp:
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        res = mailer.send_report(
            subject="Test Consolidated Briefing",
            html_body="<h1>Briefing</h1>",
            attachments=[test_pdf, test_docx],
        )

        assert res is True
        assert mock_server.send_message.called
        sent_msg = mock_server.send_message.call_args[0][0]
        # Verify mixed multipart with attachments
        assert sent_msg.is_multipart()
        filenames = [part.get_filename() for part in sent_msg.get_payload() if part.get_filename()]
        assert "test_report.pdf" in filenames
        assert "test_report.docx" in filenames


def test_reporting_agent_renders_external_opportunities(tmp_path):
    reporting_agent = ReportingAgent(daily_dir=tmp_path / "reports" / "daily", weekly_dir=tmp_path / "reports" / "weekly")

    date_str = "2026-09-22"
    data = DailyReportData(
        run_id="run_test_123",
        date=date_str,
        start_time=datetime.now(timezone.utc),
        end_time=datetime.now(timezone.utc),
        dry_run=False,
        jobs_scanned=10,
        salary_rejected=2,
        qualified_jobs=4,
        top_applications=[
            TopApplicationItem(
                company="External Mega Corp",
                role="Principal Solutions Architect",
                salary="₹45 - 65 LPA",
                match_score=92.5,
                key_factors=["Cloud modernization", "Zero trust security", "Multi-cloud architecture"],
                resume_used="Mega_Corp_Resume.docx",
                status="EXTERNAL_APPLICATION_REQUIRED",
                url="https://careers.externalmegacorp.com/jobs/123",
                method="EXTERNAL_PORTAL",
                reason="Direct company career portal submission required",
            )
        ],
    )

    md_file, html_file, html_content = reporting_agent.generate_daily_report(data)

    assert md_file.exists()
    assert html_file.exists()

    # Verify Markdown contains External Opportunities section
    md_text = md_file.read_text(encoding="utf-8")
    assert "⭐ HIGH-VALUE EXTERNAL OPPORTUNITIES" in md_text
    assert "External Mega Corp" in md_text
    assert "Apply on Company Portal ↗" in md_text
    assert "https://careers.externalmegacorp.com/jobs/123" in md_text

    # Verify HTML contains External Opportunities styled card
    assert "⭐ High-Value External Opportunities" in html_content
    assert "External Mega Corp" in html_content
    assert "Apply on Company Portal &rarr;" in html_content
    assert "https://careers.externalmegacorp.com/jobs/123" in html_content
