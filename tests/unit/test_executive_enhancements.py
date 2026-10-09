import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.models.job import JobListing, ApplicationMethod, JobStatus
from src.models.score import JobScore
from candidate.profile_extractor import get_candidate_truth
from src.models.candidate import CandidateTruth
from src.agents.cover_letter_agent import CoverLetterAgent
from src.agents.outreach_agent import OutreachAgent
from src.agents.ats_filler import AtsPortalFiller


@pytest.fixture
def candidate_truth() -> CandidateTruth:
    return get_candidate_truth()


def test_cover_letter_generation(candidate_truth, tmp_path):
    config = {}
    agent = CoverLetterAgent(candidate_truth, config)
    agent.output_dir = tmp_path

    job = JobListing(
        job_id="test_job_nordic_99",
        title="Lead Cloud Architect",
        company="Devoteam Nordic",
        location="Copenhagen, Denmark",
        url="https://example.com/job/1",
        application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
    )
    score = JobScore(
        job_id="test_job_nordic_99",
        overall_score=90.0,
        architecture_score=95.0,
        cloud_score=90.0,
        oci_score=85.0,
        ai_score=80.0,
        agentic_ai_score=75.0,
        kubernetes_score=85.0,
        security_score=85.0,
        multicloud_score=80.0,
        experience_alignment=90.0,
        skill_alignment=90.0,
        passed_threshold=True,
        strengths=["Oracle Cloud Infrastructure", "Cloud Architecture", "Kubernetes"],
    )

    docx_path, pdf_path = agent.generate_cover_letter(job, score)
    assert docx_path.exists()
    assert pdf_path.exists()
    assert "Devoteam_Nordic" in docx_path.name


def test_outreach_draft_generation(candidate_truth):
    config = {}
    agent = OutreachAgent(candidate_truth, config)
    job = JobListing(
        job_id="test_outreach_1",
        title="Principal Cloud Architect",
        company="Canva Australia",
        location="Sydney, Australia",
        url="https://example.com/job/2",
    )
    score = JobScore(
        job_id="test_outreach_1",
        overall_score=88.0,
        architecture_score=90.0,
        cloud_score=90.0,
        oci_score=80.0,
        ai_score=80.0,
        agentic_ai_score=70.0,
        kubernetes_score=80.0,
        security_score=80.0,
        multicloud_score=80.0,
        experience_alignment=90.0,
        skill_alignment=90.0,
        passed_threshold=True,
    )

    draft = agent.draft_outreach(job, score)
    assert "Canva Australia" in draft.company
    assert "Saket Saurav" in draft.subject
    assert "12 Years Total Enterprise IT Tenure" in draft.inmail_message
    assert "linkedin.com/search" in draft.linkedin_search_url


def test_ats_filler_portal_detection(candidate_truth):
    config = {}
    filler = AtsPortalFiller(candidate_truth, config, offline_mode=True)
    assert filler.is_supported_portal("https://boards.greenhouse.io/stripe/jobs/12345") is True
    assert filler.is_supported_portal("https://jobs.lever.co/canva/67890") is True
    assert filler.is_supported_portal("https://naukri.com/job/123") is False

    job = JobListing(
        job_id="gh_123",
        title="Staff Cloud Engineer",
        company="Stripe",
        location="Dublin, Ireland",
        url="https://boards.greenhouse.io/stripe/jobs/123",
        application_method=ApplicationMethod.EXTERNAL_PORTAL,
    )
    rec = filler.fill_and_apply(job, Path("/tmp/r.docx"), Path("/tmp/r.pdf"))
    assert rec.status == JobStatus.APPLIED_CONFIRMED
    assert "SIM_ATS_gh_123" == rec.confirmation_reference


def test_compensation_intelligence():
    from src.utils.compensation_intelligence import CompensationIntelligence
    job_eur = JobListing(
        job_id="li_eur_test",
        title="Principal Cloud Architect",
        company="Devoteam",
        location="Copenhagen, Denmark (Nordics)",
        url="https://example.com/job/3",
    )
    est = CompensationIntelligence.estimate_compensation(job_eur)
    assert est is not None
    assert "EUR" == est.currency
    assert "€120k – €160k" in est.formatted_band

    job_in = JobListing(
        job_id="nk_in_test",
        title="GenAI Architect",
        company="Infosys",
        location="Bengaluru, India",
        url="https://example.com/job/4",
    )
    est_in = CompensationIntelligence.estimate_compensation(job_in)
    assert est_in is not None
    assert "INR" == est_in.currency
    assert "LPA" in est_in.formatted_band


def test_telegram_notifier(monkeypatch):
    from src.utils.telegram_notifier import TelegramNotifier
    config = {
        "telegram": {
            "enabled": True,
            "bot_token": "mock_token_123",
            "chat_id": "mock_chat_456",
        }
    }
    notifier = TelegramNotifier(config)
    assert notifier.enabled is True
    assert notifier.bot_token == "mock_token_123"

    sent_msgs = []
    def mock_send(text, parse_mode="HTML"):
        sent_msgs.append((text, parse_mode))
        return True

    monkeypatch.setattr(notifier, "send_message", mock_send)

    res_app = notifier.notify_application_submitted(
        company="Snowflake Europe",
        role="Principal Cloud Architect",
        location="Amsterdam, Netherlands",
        platform="LinkedIn Easy Apply",
        match_score=94.5,
        confirmation_ref="SUB_999",
        job_url="https://linkedin.com/jobs/view/123",
        cover_letter=True,
    )
    assert res_app is True
    assert len(sent_msgs) == 1
    assert "Snowflake Europe" in sent_msgs[0][0]
    assert "Cover Letter Attached" in sent_msgs[0][0]

    res_inv = notifier.notify_interview_invite(
        sender="recruiter@canva.com",
        subject="Interview Invitation: Principal Architect",
        company="Canva",
        snippet="We would love to invite you for a round 1 chat",
    )
    assert res_inv is True
    assert len(sent_msgs) == 2
    assert "Recruiter Interview Invitation" in sent_msgs[1][0]

    res_sum = notifier.notify_daily_summary(
        date_str="2026-10-09",
        confirmed_count=4,
        qualified_count=8,
        scanned_count=25,
        dry_run=False,
    )
    assert res_sum is True
    assert len(sent_msgs) == 3
    assert "Daily Pipeline Complete" in sent_msgs[2][0]


def test_recruiter_lead_discovery_and_personalized_outreach(candidate_truth):
    from src.linkedin.adapter import LinkedInAdapter
    config = {}
    li_adapter = LinkedInAdapter(config=config, candidate_truth=candidate_truth, offline_mode=True)
    lead = li_adapter.find_recruiter_lead("NewRocket", "Agentic AI Architect")
    assert lead["found"] is True
    assert "NewRocket" in lead["company"]
    assert "Hiring Lead" in lead["name"]

    outreach_agent = OutreachAgent(candidate_truth, config)
    job = JobListing(
        job_id="test_job_nr_1",
        title="Agentic AI Architect",
        company="NewRocket",
        location="Amsterdam, Netherlands",
        url="https://example.com/job/nr1",
    )
    score = JobScore(
        job_id="test_job_nr_1",
        overall_score=92.5,
        architecture_score=95.0,
        cloud_score=90.0,
        oci_score=90.0,
        ai_score=90.0,
        agentic_ai_score=90.0,
        kubernetes_score=90.0,
        security_score=90.0,
        multicloud_score=90.0,
        experience_alignment=95.0,
        skill_alignment=95.0,
        passed_threshold=True,
    )
    draft = outreach_agent.draft_outreach(job, score, recruiter_lead=lead)
    assert "Hi Hiring Lead," in draft.inmail_message
    assert "Hi Hiring Lead," in draft.cold_email_message
    assert "NewRocket" in draft.hiring_lead_target


def test_linkedin_profile_seo_optimization(candidate_truth):
    from src.linkedin.adapter import LinkedInAdapter
    config = {}
    li_adapter = LinkedInAdapter(config=config, candidate_truth=candidate_truth, offline_mode=True)
    res = li_adapter.optimize_profile_keywords()
    assert res["success"] is True
    assert "Principal Cloud & AI Architect" in res["headline"]
    assert len(res["headline"]) <= 220
    assert res["network_notification"] == "DISABLED"
    assert res["open_to_work_public_badge"] == "NEVER_ENABLED"


def test_discovery_ats_portal_jobs(monkeypatch):
    from src.agents.discovery import DiscoveryAgent
    mock_client = MagicMock()
    mock_repo = MagicMock()
    mock_repo.is_already_applied.return_value = False
    mock_repo.has_applied_to_company_and_title.return_value = False

    agent = DiscoveryAgent(mock_client, mock_repo, config={})
    jobs = agent.discover_ats_portal_jobs(limit=3)
    assert len(jobs) == 3
    assert any("boards.greenhouse.io" in j.url for j in jobs)
    assert any("jobs.lever.co" in j.url for j in jobs)
    assert all(j.application_method == ApplicationMethod.EXTERNAL_PORTAL for j in jobs)


