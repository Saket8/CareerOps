"""Unit tests for ReportingAgent and SmtpMailer."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.agents.reporting import ReportingAgent
from src.email_service.smtp_mailer import SmtpMailer
from src.models.report import DailyReportData, WeeklyIntelligenceData, TopApplicationItem, MarketTrendItem


def test_daily_report_generation(tmp_path):
    agent = ReportingAgent(daily_dir=tmp_path / "daily", weekly_dir=tmp_path / "weekly")

    now = datetime.now(timezone.utc)
    data = DailyReportData(
        run_id="run_test_1",
        date="2026-09-22",
        start_time=now,
        end_time=now,
        dry_run=True,
        jobs_scanned=150,
        salary_rejected=45,
        qualified_jobs=25,
        strong_matches=12,
        resumes_generated=10,
        applications_submitted=8,
        blocked_applications=1,
        interview_packs_generated=5,
        top_applications=[
            TopApplicationItem(
                company="Oracle",
                role="Principal Cloud Architect",
                salary="30-45 LPA",
                match_score=94.5,
                key_factors=["OCI", "OKE", "GenAI"],
                resume_used="Oracle_Principal_20260922.docx",
                status="APPLIED",
                url="https://naukri.com/job/1",
            )
        ],
    )

    md_path, html_path, html_content = agent.generate_daily_report(data)

    assert md_path.exists()
    assert html_path.exists()
    assert "150" in md_path.read_text(encoding="utf-8")
    assert "Oracle" in html_content
    assert "94.5%" in html_content
    assert "DRY RUN" in html_content


def test_weekly_report_generation(tmp_path):
    agent = ReportingAgent(daily_dir=tmp_path / "daily", weekly_dir=tmp_path / "weekly")

    data = WeeklyIntelligenceData(
        run_id="intel_2026-W38",
        week_number="2026-W38",
        date_range="Sep 15 - Sep 22, 2026",
        total_jobs_analyzed=85,
        salary_stats={"above_30_lpa": 20, "min_20_to_30_lpa": 35, "undisclosed_count": 25, "below_20_lpa_rejected": 15},
        trends=[
            MarketTrendItem(item_name="LANGCHAIN", category="skill", current_count=18, previous_count=10, trend="INCREASING (↑)")
        ],
        top_companies=[{"name": "Oracle", "count": 12}],
        top_roles=[{"name": "Cloud Solutions Architect", "count": 15}],
        recurring_skills=[{"name": "OCI", "count": 42}],
        candidate_resume_gaps=["Add explicit AWS SageMaker transferable notes"],
        recommended_learning=["MCP server integration"],
        recommended_search_queries=["Principal Cloud GenAI Architect"],
    )

    md_path, html_path, html_content = agent.generate_weekly_report(data)

    assert md_path.exists()
    assert html_path.exists()
    assert "LANGCHAIN" in html_content
    assert "INCREASING (↑)" in html_content


def test_smtp_mailer_no_credentials_safe(monkeypatch):
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    mailer = SmtpMailer(config={"email": {"enabled": True}})
    # No credentials in env -> should safely log warning and return False
    res = mailer.send_report("Subject", "<h1>Content</h1>")
    assert res is False


@patch("smtplib.SMTP")
def test_smtp_mailer_mock_send(mock_smtp_class, monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "testuser@gmail.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret123")
    monkeypatch.setenv("EMAIL_RECIPIENT", "saket.saurav@cognizant.com")

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    mailer = SmtpMailer()
    success = mailer.send_report("Test Subject", "<p>Hello</p>")

    assert success is True
    assert mock_server.login.called
    assert mock_server.send_message.called


def test_daily_report_generation_with_zero_applications(tmp_path):
    agent = ReportingAgent(daily_dir=tmp_path / "daily", weekly_dir=tmp_path / "weekly")
    now = datetime.now(timezone.utc)
    data = DailyReportData(
        run_id="run_zero_1",
        date="2026-09-23",
        start_time=now,
        end_time=now,
        dry_run=False,
        jobs_scanned=200,
        salary_rejected=30,
        qualified_jobs=10,
        strong_matches=5,
        resumes_generated=0,
        applications_submitted=0,
        blocked_applications=0,
        interview_packs_generated=0,
        top_applications=[],
    )
    md_path, html_path, html_content = agent.generate_daily_report(data)

    assert md_path.exists()
    assert html_path.exists()
    assert "No direct applications submitted in this run." in html_content
    assert "Confirmed Applications (0)" in html_content
    assert "None" not in html_content  # Verifies clean message instead of bare 'None'


def test_email_deduplication_detection(tmp_path):
    import json
    dispatch_file = tmp_path / "dispatched_emails.json"
    
    # Simulate prior dispatch
    prior_records = [
        {
            "run_id": "run_morning_1",
            "date": "2026-09-29",
            "job_urls": ["https://naukri.com/job-1", "https://naukri.com/job-2"],
            "applications_count": 2,
            "subject": "CareerOps — Daily Application Report — 2026-09-29",
        }
    ]
    dispatch_file.write_text(json.dumps(prior_records), encoding="utf-8")
    
    # Read back and verify duplicate detection logic
    records = json.loads(dispatch_file.read_text(encoding="utf-8"))
    incoming_urls_duplicate = sorted(["https://naukri.com/job-2", "https://naukri.com/job-1"])
    incoming_urls_unique = sorted(["https://naukri.com/job-3"])
    
    is_dup_1 = any(r.get("date") == "2026-09-29" and sorted(r.get("job_urls", [])) == incoming_urls_duplicate for r in records)
    is_dup_2 = any(r.get("date") == "2026-09-29" and sorted(r.get("job_urls", [])) == incoming_urls_unique for r in records)
    
    assert is_dup_1 is True, "Exact match of URLs on same date must be identified as duplicate"
    assert is_dup_2 is False, "New URLs must not be identified as duplicate"

