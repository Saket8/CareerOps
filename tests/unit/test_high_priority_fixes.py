"""Unit tests verifying the 7 high-priority system refinements:
1. Precise Sponsorship & Work Auth Truth
2. Automated Submission Gates & Missing Fact Recording
3. End-to-End Run Time Tracking & Target Notifications
4. Recruiter Outreach Draft Review (Never Auto-Send) & DB Persistence
5. Master CV Selection on LinkedIn
6. Careful Status and Retry Rules (preventing duplicates on unverified/ambiguous applications)
7. Measurable Results Reporting by Source Platform
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

from candidate.profile_extractor import get_candidate_truth
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.models.job import JobListing, JobSalary, SalaryEligibility, JobStatus, ApplicationRecord, ApplicationMethod
from src.models.score import JobScore
from src.models.report import DailyReportData, SourceBreakdownItem
from src.agents.orchestrator import check_submission_gates, record_missing_candidate_fact, get_source_label
from src.database.connection import get_db_session, init_db
from src.database.models import Base, AgentRunModel, ApplicationModel, JobModel
from src.database.repositories.run_repo import RunRepository
from src.database.repositories.application_repo import ApplicationRepository
from src.utils.telegram_notifier import TelegramNotifier
from src.agents.reporting import ReportingAgent


# ============================================================================
# Fix 1: Precise Sponsorship Truth
# ============================================================================

def test_sponsorship_truth_international_vs_domestic():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth, strict_truth_only=True)

    # 1. International inquiry: Requires sponsorship -> Yes
    res_spon_intl = resolver.resolve_question("Will you now or in the future require visa sponsorship?")
    assert res_spon_intl.can_answer is True
    assert res_spon_intl.answer_value == "Yes"

    res_spon_us = resolver.resolve_question("Do you require employer sponsorship for a work visa in the United States?")
    assert res_spon_us.can_answer is True
    assert res_spon_us.answer_value == "Yes"

    # 2. International inquiry: Currently authorized to work here -> No
    res_auth_intl = resolver.resolve_question("Are you currently authorized to work here?")
    assert res_auth_intl.can_answer is True
    assert res_auth_intl.answer_value == "No"

    res_auth_eu = resolver.resolve_question("Are you legally authorized to work in Germany / European Union?")
    assert res_auth_eu.can_answer is True
    assert res_auth_eu.answer_value == "No"

    # 3. Domestic India inquiry: Authorized -> Yes, Requires Sponsorship -> No
    res_auth_india = resolver.resolve_question("Are you legally authorized to work in India?")
    assert res_auth_india.can_answer is True
    assert res_auth_india.answer_value == "Yes"

    res_spon_india = resolver.resolve_question("Will you require visa sponsorship to work in India?")
    assert res_spon_india.can_answer is True
    assert res_spon_india.answer_value == "No"

    # 4. Citizenship questions
    res_cit_in = resolver.resolve_question("Are you an Indian citizen?")
    assert res_cit_in.can_answer is True
    assert res_cit_in.answer_value == "Yes"

    res_cit_us = resolver.resolve_question("Are you a US citizen or Green Card holder?")
    assert res_cit_us.can_answer is True
    assert res_cit_us.answer_value == "No"


# ============================================================================
# Fix 2: Automated Submission Gates & Missing Fact Recording
# ============================================================================

def test_automated_submission_gates_and_missing_fact_recording(tmp_path):
    candidate_truth = get_candidate_truth(refresh=True)
    config = {
        "safety": {"blocked_companies": ["cognizant", "cts"]},
        "application": {"min_salary_lpa": 30.0},
    }

    # Gate A: Current Employer Blocklist
    blocked_job = JobListing(
        job_id="job_cts_01",
        title="Principal Cloud Architect",
        company="Cognizant Technology Solutions",
        location="Noida, India",
        url="https://example.com/job1",
    )
    passed, gate_type, reason = check_submission_gates(blocked_job, candidate_truth, config)
    assert passed is False
    assert gate_type == "BLOCKED_EMPLOYER"

    # Gate B: Salary Below Floor
    low_sal_job = JobListing(
        job_id="job_low_01",
        title="Cloud Architect",
        company="TechCorp",
        location="Noida, India",
        salary=JobSalary(min_lpa=20.0, max_lpa=25.0, is_disclosed=True, raw_text="20-25 LPA"),
        url="https://example.com/job2",
    )
    passed, gate_type, reason = check_submission_gates(low_sal_job, candidate_truth, config)
    assert passed is False
    assert gate_type == "SALARY_BELOW_MINIMUM"

    # Gate C: Experience Requirement Exceeding Profile (12 yrs)
    exp_job = JobListing(
        job_id="job_exp_01",
        title="Distinguished VP Cloud Architect",
        company="EnterpriseX",
        location="Noida, India",
        experience_min=18.0,
        url="https://example.com/job3",
    )
    passed, gate_type, reason = check_submission_gates(exp_job, candidate_truth, config)
    assert passed is False
    assert gate_type == "EXPERIENCE_MISMATCH"

    # Gate D: Valid Role Passing All Gates
    valid_job = JobListing(
        job_id="job_valid_01",
        title="Principal OCI Architect",
        company="NewRocket",
        location="Amsterdam, Netherlands",
        salary=JobSalary(is_disclosed=False, raw_text="Undisclosed"),
        url="https://example.com/job4",
    )
    passed, gate_type, reason = check_submission_gates(valid_job, candidate_truth, config)
    assert passed is True
    assert gate_type == "PASSED"

    # Missing fact recording persistence
    missing_facts_file = tmp_path / "missing_candidate_facts.json"
    record_missing_candidate_fact(
        job_id="job_test_miss",
        company="Acme Corp",
        title="Staff Engineer",
        missing_fact="German B2 Language Proficiency",
        reason="Required German B2 not in verified candidate truth",
        file_path=missing_facts_file,
    )
    assert missing_facts_file.exists()
    data = json.loads(missing_facts_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["missing_fact"] == "German B2 Language Proficiency"
    assert data[0]["company"] == "Acme Corp"


# ============================================================================
# Fix 3: End-to-End Run Time Tracking & Target Notifications
# ============================================================================

def test_run_time_tracking_and_target_notifications():
    db_url = "sqlite:///:memory:"
    init_db(db_url)

    with get_db_session(db_url) as session:
        run_repo = RunRepository(session)
        now = datetime.now(timezone.utc)

        # Populate two historical successful runs (duration: 300s and 600s -> avg 450s)
        run1 = AgentRunModel(
            run_id="run_past_1",
            status="SUCCESS",
            start_time=now - timedelta(seconds=1200),
            end_time=now - timedelta(seconds=900),
        )
        run2 = AgentRunModel(
            run_id="run_past_2",
            status="SUCCESS",
            start_time=now - timedelta(seconds=800),
            end_time=now - timedelta(seconds=200),
        )
        session.add_all([run1, run2])
        session.commit()

        avg_dur = run_repo.get_average_duration_seconds()
        assert avg_dur == pytest.approx(450.0, rel=1e-2)

    # Test Telegram delay and failure notification payloads
    mock_sent = []
    notifier = TelegramNotifier({"telegram": {"enabled": True, "bot_token": "mock", "chat_id": "mock"}})
    notifier.send_message = lambda text, parse_mode="HTML": mock_sent.append(text) or True

    # Test delay alert
    notifier.notify_run_delay_or_failure(
        run_id="run_delayed_test",
        status="DELAYED",
        elapsed_seconds=1200,
        target_seconds=450,
    )
    assert len(mock_sent) == 1
    assert "Run Execution Delayed" in mock_sent[0]
    assert "Target: 7 min" in mock_sent[0]

    # Test failure alert
    notifier.notify_run_delay_or_failure(
        run_id="run_failed_test",
        status="FAILED",
        error_msg="Database connection timed out during submission",
        elapsed_seconds=320,
    )
    assert len(mock_sent) == 2
    assert "Pipeline Run Failure Alert" in mock_sent[1]
    assert "Database connection timed out" in mock_sent[1]


# ============================================================================
# Fix 4: Recruiter Outreach Draft Review (Never Auto-Send) & DB Persistence
# ============================================================================

def test_recruiter_outreach_draft_review_and_persistence():
    db_url = "sqlite:///:memory:"
    init_db(db_url)

    mock_telegram = []
    notifier = TelegramNotifier({"telegram": {"enabled": True, "bot_token": "mock", "chat_id": "mock"}})
    notifier.send_message = lambda text, parse_mode="HTML": mock_telegram.append(text) or True

    # 1. Dispatch draft for human review via Telegram
    notifier.notify_recruiter_draft(
        company="NewRocket",
        role="Principal Cloud Architect",
        contact_source="Sarah Jenkins (Director of Talent Acquisition)",
        job_url="https://www.linkedin.com/jobs/view/123456",
        match_rationale="88% Match | 12 Yrs Tenure | 6.5 Yrs OCI Architecture",
        pitch="Hi Sarah,\nI noticed NewRocket is scaling its cloud platform architecture...",
        inmail_url="https://www.linkedin.com/in/sarah-jenkins",
    )
    assert len(mock_telegram) == 1
    draft_msg = mock_telegram[0]
    assert "Recruiter Outreach Draft for Review" in draft_msg
    assert "NewRocket" in draft_msg
    assert "Sarah Jenkins" in draft_msg
    assert "Not sent to recruiter automatically" in draft_msg

    # 2. Persist draft into database
    with get_db_session(db_url) as session:
        # Create a job and application
        job = JobModel(job_id="job_nr_1", title="Principal Cloud Architect", company="NewRocket", location="Amsterdam, Netherlands", url="https://example.com")
        session.add(job)
        session.flush()

        app_repo = ApplicationRepository(session)
        rec = ApplicationRecord(
            application_id="app_nr_1",
            job_id="job_nr_1",
            status=JobStatus.APPLIED_CONFIRMED,
        )
        app_repo.record_application(rec, commit=True)

        draft_data = {
            "role": "Principal Cloud Architect",
            "contact_target": "Sarah Jenkins",
            "pitch": "Hi Sarah...",
            "status": "SAVED_FOR_REVIEW",
        }
        app_repo.save_outreach_draft("app_nr_1", draft_data)

        # Verify draft was saved without auto-sending
        db_app = app_repo.get_by_job_id("job_nr_1")
        assert db_app.outreach_draft == draft_data
        assert db_app.questions_answered.get("recruiter_outreach_draft") == draft_data


# ============================================================================
# Fix 6: Careful Status and Retry Rules (Prevent Duplicate Submissions)
# ============================================================================

def test_careful_status_and_retry_rules():
    db_url = "sqlite:///:memory:"
    init_db(db_url)

    with get_db_session(db_url) as session:
        job1 = JobModel(job_id="job_retry_1", title="Cloud Architect", company="Infosys", location="Noida, India", url="https://example.com/1")
        job2 = JobModel(job_id="job_retry_2", title="DevOps Lead", company="TCS", location="Bengaluru, India", url="https://example.com/2")
        job3 = JobModel(job_id="job_retry_3", title="Solutions Architect", company="Wipro", location="Pune, India", url="https://example.com/3")
        session.add_all([job1, job2, job3])
        session.flush()

        app_repo = ApplicationRepository(session)

        # 1. Confirmed application cannot be retried
        app_confirmed = ApplicationRecord(
            application_id="app_1",
            job_id="job_retry_1",
            status=JobStatus.APPLIED_CONFIRMED,
            confirmation_reference="CONF-12345",
        )
        app_repo.record_application(app_confirmed, commit=True)
        can_retry_1, reason_1 = app_repo.can_retry_application("job_retry_1", "Infosys", "Cloud Architect")
        assert can_retry_1 is False
        assert "already confirmed" in reason_1.lower()

        # 2. Submitted-but-unverified application CANNOT be automatically retried (prevents duplicate submission)
        app_unverified = ApplicationRecord(
            application_id="app_2",
            job_id="job_retry_2",
            status=JobStatus.SUBMISSION_UNVERIFIED,
        )
        app_repo.record_application(app_unverified, commit=True)
        can_retry_2, reason_2 = app_repo.can_retry_application("job_retry_2", "TCS", "DevOps Lead")
        assert can_retry_2 is False
        assert "unverified" in reason_2.lower()
        assert app_repo.has_applied_to_job("job_retry_2") is True

        # 3. Fresh job with no prior application CAN be processed
        can_retry_3, reason_3 = app_repo.can_retry_application("job_retry_3", "Wipro", "Solutions Architect")
        assert can_retry_3 is True


# ============================================================================
# Fix 7: Measurable Results Reporting by Source Platform
# ============================================================================

def test_source_breakdown_reporting_and_telegram_summary(tmp_path):
    source_breakdown = [
        SourceBreakdownItem(source="Naukri", discovered=80, qualified=12, attempted=6, confirmed=6, skipped=6, failed=0),
        SourceBreakdownItem(source="LinkedIn", discovered=15, qualified=5, attempted=3, confirmed=3, skipped=2, failed=0),
        SourceBreakdownItem(source="ATS Portal", discovered=5, qualified=2, attempted=1, confirmed=1, skipped=1, failed=0),
    ]

    now = datetime.now(timezone.utc)
    daily_data = DailyReportData(
        run_id="run_metrics_test",
        date="2026-10-09",
        start_time=now,
        end_time=now + timedelta(seconds=420),
        jobs_scanned=100,
        salary_rejected=30,
        qualified_jobs=19,
        applications_submitted=10,
        applications_confirmed=10,
        source_breakdown=source_breakdown,
    )

    # 1. Report generation
    reporting_agent = ReportingAgent(daily_dir=tmp_path / "daily", weekly_dir=tmp_path / "weekly")
    md_path, html_path, html_body = reporting_agent.generate_daily_report(daily_data)

    md_content = md_path.read_text(encoding="utf-8")
    assert "Application Results by Source Platform" in md_content
    assert "| Naukri | 80 | 12 | 6 | 6 | 6 | 0 |" in md_content
    assert "| LinkedIn | 15 | 5 | 3 | 3 | 2 | 0 |" in md_content
    assert "| ATS Portal | 5 | 2 | 1 | 1 | 1 | 0 |" in md_content
    assert "| **Total** | **100** | **19** | **10** | **10** | **9** | **0** |" in md_content

    assert "Results by Platform" in html_body
    assert "Naukri" in html_body
    assert "LinkedIn" in html_body

    # 2. Telegram summary includes source summary
    mock_telegram = []
    notifier = TelegramNotifier({"telegram": {"enabled": True, "bot_token": "mock", "chat_id": "mock"}})
    notifier.send_message = lambda text, parse_mode="HTML": mock_telegram.append(text) or True

    notifier.notify_daily_summary(
        date_str="2026-10-09",
        confirmed_count=10,
        qualified_count=19,
        scanned_count=100,
        dry_run=False,
        source_summary={item.source: item.confirmed for item in source_breakdown},
    )
    assert len(mock_telegram) == 1
    summary_text = mock_telegram[0]
    assert "Source Breakdown (Confirmed):" in summary_text
    assert "Naukri: <b>6</b>" in summary_text
    assert "LinkedIn: <b>3</b>" in summary_text
    assert "ATS Portal: <b>1</b>" in summary_text
