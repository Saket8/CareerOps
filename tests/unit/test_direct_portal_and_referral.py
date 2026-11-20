"""Unit tests for Direct Career Portal Discovery, Workday ATS Support, and Referral Pack Generation."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.models.job import JobListing, JobStatus, ApplicationMethod, JobSalary, SalaryEligibility
from src.models.score import JobScore
from src.models.candidate import CandidateTruth
from candidate.profile_extractor import get_candidate_truth
from src.agents.direct_portal_discovery import DirectPortalDiscoveryAgent
from src.agents.ats_filler import AtsPortalFiller
from src.agents.referral_pack_agent import ReferralPackAgent


def test_top100_gcc_data_loading():
    """Verify Top 100 GCC and Hyperscaler master dataset loads successfully."""
    repo_mock = MagicMock()
    config = {"safety": {"blocked_companies": ["cognizant"]}}
    agent = DirectPortalDiscoveryAgent(repo_mock, config, offline_mode=True)
    assert agent.top100_data is not None
    assert "entities" in agent.top100_data
    assert len(agent.top100_data["entities"]) == 100
    assert "delhi_ncr_local_targets" in agent.top100_data
    assert len(agent.top100_data["delhi_ncr_local_targets"]) >= 15


def test_greenhouse_lever_curated_discovery():
    """Verify curated neoclouds and international ATS positions are extracted."""
    repo_mock = MagicMock()
    repo_mock.is_already_applied.return_value = False
    repo_mock.has_applied_to_company_and_title.return_value = False
    repo_mock.get.return_value = None

    config = {"safety": {"blocked_companies": ["cognizant"]}}
    agent = DirectPortalDiscoveryAgent(repo_mock, config, offline_mode=False)
    gh_jobs = agent._discover_greenhouse_lever_targets(limit=3)

    assert len(gh_jobs) == 3
    companies = [j.company for j in gh_jobs]
    assert "CoreWeave" in companies
    assert "Nebius" in companies
    assert "Snowflake" in companies
    for j in gh_jobs:
        assert j.source_platform == "direct_career_portal"
        assert j.application_method == ApplicationMethod.EXTERNAL_PORTAL.value


def test_employer_safety_filtering_blocks_current_employer():
    """Verify candidate's current employer (Cognizant) is strictly excluded."""
    repo_mock = MagicMock()
    config = {"safety": {"blocked_companies": ["cognizant", "cts"]}}
    agent = DirectPortalDiscoveryAgent(repo_mock, config, offline_mode=False)

    cognizant_job = JobListing(
        job_id="direct_cts_123",
        title="Cloud Architect",
        company="Cognizant Technology Solutions",
        location="Noida, India",
        url="https://cognizant.wd5.myworkdayjobs.com/careers/123",
        canonical_url="https://cognizant.wd5.myworkdayjobs.com/careers/123",
        jd_text="Cloud Architect opening",
        has_full_jd=True,
    )
    accepted = agent._accept_and_persist(cognizant_job)
    assert accepted is False
    repo_mock.save_job.assert_not_called()


def test_ats_filler_supported_portal_detection():
    """Verify AtsPortalFiller detects Greenhouse, Lever, Workday, Oracle HCM, and Amazon.jobs."""
    assert AtsPortalFiller.is_supported_portal("https://boards.greenhouse.io/coreweave/jobs/123") is True
    assert AtsPortalFiller.is_supported_portal("https://jobs.lever.co/snowflake/456") is True
    assert AtsPortalFiller.is_supported_portal("https://adobe.wd5.myworkdayjobs.com/external_experienced/job/Noida/123") is True
    assert AtsPortalFiller.is_supported_portal("https://barclays.wd3.myworkdayjobs.com/External_Career_Site_Barclays/job/456") is True
    assert AtsPortalFiller.is_supported_portal("https://fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/job/789") is True
    assert AtsPortalFiller.is_supported_portal("https://amazon.jobs/en/jobs/10418263/solutions-architect") is True
    assert AtsPortalFiller.is_supported_portal("https://www.naukri.com/job-listings-123") is False


def test_ats_filler_dry_run_simulation():
    """Verify AtsPortalFiller returns simulated confirmation in dry-run mode."""
    cand_truth = get_candidate_truth()
    config = {"ats_filler": {"auto_submit": True}, "application": {"dry_run": True}}
    filler = AtsPortalFiller(cand_truth, config, offline_mode=False)

    job = JobListing(
        job_id="direct_wd_barclays_1001",
        title="Solutions Architect",
        company="Barclays",
        location="Noida, India",
        url="https://barclays.wd3.myworkdayjobs.com/External/job/1001",
        canonical_url="https://barclays.wd3.myworkdayjobs.com/External/job/1001",
        jd_text="Enterprise Cloud Solutions Architect opening",
        has_full_jd=True,
    )
    rec = filler.fill_and_apply(job, Path("resumes/master/Saket_Saurav_OCI.docx"), Path("resumes/master/Saket_Saurav_Resume.pdf"))
    assert rec.status == JobStatus.APPLIED_CONFIRMED
    assert rec.external_portal == "Workday ATS"
    assert "SIM_ATS" in rec.confirmation_reference


def test_referral_pack_generation_and_candidate_invariants(tmp_path):
    """Verify ReferralPackAgent generates comprehensive referral packs adhering to all candidate invariants."""
    cand_truth = get_candidate_truth()
    config = {}
    agent = ReferralPackAgent(cand_truth, config, base_dir=tmp_path / "interviews")

    job = JobListing(
        job_id="direct_amz_10418263",
        title="Solutions Architect",
        company="Amazon Web Services (AWS)",
        location="Gurugram, India",
        url="https://amazon.jobs/en/jobs/10418263/solutions-architect",
        canonical_url="https://amazon.jobs/en/jobs/10418263/solutions-architect",
        jd_text="AWS Requisition (Job ID: 10418263) for Solutions Architect in Gurugram.",
        has_full_jd=True,
    )
    score = JobScore(
        job_id=job.job_id,
        overall_score=94.5,
        title_score=95.0,
        skill_score=95.0,
        experience_score=95.0,
        role_type_score=95.0,
        architecture_score=95.0,
        cloud_score=95.0,
        oci_score=95.0,
        ai_score=90.0,
        agentic_ai_score=90.0,
        kubernetes_score=90.0,
        security_score=90.0,
        multicloud_score=90.0,
        experience_alignment=95.0,
        skill_alignment=95.0,
        passed_threshold=True,
        strengths=["12 YOE Enterprise IT", "6.5 YOE Cloud & OCI Architecture", "5.0 YOE AI & Agentic Platforms"],
    )

    dummy_docx = tmp_path / "Saket_Saurav_AWS.docx"
    dummy_pdf = tmp_path / "Saket_Saurav_AWS.pdf"
    dummy_docx.write_text("docx", encoding="utf-8")
    dummy_pdf.write_text("pdf", encoding="utf-8")

    pack_file = agent.generate_referral_pack(job, score, dummy_docx, dummy_pdf)
    assert pack_file.exists()

    content = pack_file.read_text(encoding="utf-8")

    # 1. Candidate Invariant Checks
    assert "Saket Saurav" in content
    assert "sauravskt8@gmail.com" in content
    assert "@cognizant.com" not in content  # Strict invariant: never use Cognizant email
    assert "+91-7028481800" in content
    assert "https://www.linkedin.com/in/saket-saurav-31326b57/" in content  # Strict invariant: exact suffix -31326b57/
    assert "https://github.com/Saket8" in content
    assert "12 Years" in content
    assert "6.5 Years" in content
    assert "90 Days" in content
    assert "Nov 2024 – Present" in content

    # 2. Requisition and Pitch Checks
    assert "10418263" in content
    assert "30-Second Internal Employee Referral Pitch" in content
    assert "Direct Hiring Manager / Director Outreach Pitch" in content
    assert "Pre-Resolved ATS Screening Answers" in content
    assert "Direct Career Portal Link" in content
