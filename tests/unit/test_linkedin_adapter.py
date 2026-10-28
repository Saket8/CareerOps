"""Unit tests for LinkedInAdapter international discovery and Easy Apply automation."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.linkedin.adapter import LinkedInAdapter
from src.models.job import JobListing, JobStatus, ApplicationMethod
from src.models.candidate import CandidateTruth
from candidate.profile_extractor import get_candidate_truth


@pytest.fixture
def candidate_truth() -> CandidateTruth:
    return get_candidate_truth()


@pytest.fixture
def mock_config() -> dict:
    return {
        "linkedin": {
            "enabled": True,
            "auto_submit": True,
            "max_applications_per_day": 10,
            "user_data_dir": "/tmp/mock_li_profile",
            "auth_state_path": "artifacts/linkedin_auth.json",
            "target_regions": [
                {"name": "Europe", "location": "Europe"},
                {"name": "Nordics", "location": "Nordics"},
                {"name": "Australia", "location": "Australia"},
                {"name": "United States", "location": "United States"},
            ],
            "queries": [
                "OCI Architect",
                "Cloud Architect",
            ],
        },
        "application": {
            "dry_run": True,
        },
    }


def test_linkedin_adapter_initialization(mock_config, candidate_truth):
    adapter = LinkedInAdapter(config=mock_config, candidate_truth=candidate_truth, offline_mode=True)
    assert adapter.auto_submit is True
    assert adapter.offline_mode is True
    assert adapter.answer_resolver is not None


def test_linkedin_offline_discovery_returns_sample_jobs(mock_config, candidate_truth):
    adapter = LinkedInAdapter(config=mock_config, candidate_truth=candidate_truth, offline_mode=True)
    jobs = adapter.discover_jobs(limit_per_query=5)
    assert len(jobs) >= 1
    assert all(j.source_platform == "linkedin" for j in jobs)
    assert all(j.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY for j in jobs)


def test_linkedin_apply_easy_apply_simulated(mock_config, candidate_truth, tmp_path):
    adapter = LinkedInAdapter(config=mock_config, candidate_truth=candidate_truth, offline_mode=True)
    job = JobListing(
        job_id="li_12345678",
        title="Lead Cloud Architect",
        company="Devoteam",
        location="Copenhagen, Denmark (Nordics)",
        work_mode="onsite",
        url="https://www.linkedin.com/jobs/view/12345678/",
        source_platform="linkedin",
        application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
        jd_text="Devoteam provides full employer visa sponsorship and comprehensive relocation assistance package for international candidates to relocate to Denmark.",
    )
    score_mock = MagicMock()
    docx = tmp_path / "resume.docx"
    docx.touch()
    pdf = tmp_path / "resume.pdf"
    pdf.touch()

    rec = adapter.apply_easy_apply(job, score_mock, docx, pdf)
    assert rec.status == JobStatus.APPLIED_CONFIRMED
    assert rec.confirmation_reference == f"SIM_LI_{job.job_id}"
    assert rec.application_method == ApplicationMethod.LINKEDIN_EASY_APPLY.value


def test_visa_relocation_gate_positive_cases():
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_pass_1",
        title="Staff OCI Architect",
        company="Global Cloud Corp",
        location="Amsterdam, Netherlands",
        url="https://www.linkedin.com/jobs/view/100001/",
        jd_text="We offer full visa sponsorship for international candidates and generous relocation assistance package to Amsterdam.",
    )
    passed, reason = VisaRelocationGate.evaluate(job)
    assert passed is True
    assert "PASSED" in reason


def test_visa_relocation_gate_rejects_negative_sponsorship():
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_neg_spon_1",
        title="Cloud Architect",
        company="Local EU Bank",
        location="Frankfurt, Germany",
        url="https://www.linkedin.com/jobs/view/100002/",
        jd_text="Applicants must be authorized to work in Germany without sponsorship. Relocation assistance provided.",
    )
    passed, reason = VisaRelocationGate.evaluate(job)
    assert passed is False
    assert "VISA_SPONSORSHIP_EXCLUDED" in reason


def test_visa_relocation_gate_rejects_negative_relocation():
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_neg_reloc_1",
        title="Cloud Architect",
        company="Remote Tech",
        location="London, UK",
        url="https://www.linkedin.com/jobs/view/100003/",
        jd_text="We offer visa sponsorship. No relocation assistance or package is provided.",
    )
    passed, reason = VisaRelocationGate.evaluate(job)
    assert passed is False
    assert "RELOCATION_EXCLUDED" in reason


def test_visa_relocation_gate_rejects_missing_sponsorship_or_relocation():
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job_no_spon = JobListing(
        job_id="li_miss_spon_1",
        title="OCI Solutions Architect",
        company="Enterprise Corp",
        location="Sydney, Australia",
        url="https://www.linkedin.com/jobs/view/100004/",
        jd_text="Architect enterprise cloud solutions. Relocation support available. 10+ years experience required.",
    )
    passed, reason = VisaRelocationGate.evaluate(job_no_spon)
    assert passed is False
    assert "MISSING_VISA_SPONSORSHIP" in reason

    job_no_reloc = JobListing(
        job_id="li_miss_reloc_1",
        title="OCI Solutions Architect",
        company="Enterprise Corp",
        location="Sydney, Australia",
        url="https://www.linkedin.com/jobs/view/100005/",
        jd_text="Architect enterprise cloud solutions. We provide visa sponsorship. 10+ years experience required.",
    )
    passed, reason = VisaRelocationGate.evaluate(job_no_reloc)
    assert passed is False
    assert "MISSING_RELOCATION" in reason


def test_visa_relocation_gate_allows_domestic_india():
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job_india = JobListing(
        job_id="li_india_1",
        title="OCI Cloud Architect",
        company="Oracle India",
        location="Bengaluru, Karnataka, India",
        url="https://www.linkedin.com/jobs/view/100006/",
        jd_text="Seeking Cloud Architect for Bengaluru office. Competitive salary and benefits.",
    )
    passed, reason = VisaRelocationGate.evaluate(job_india)
    assert passed is True
    assert "Domestic India" in reason or "PASSED" in reason


def test_linkedin_apply_easy_apply_rejects_unqualified(mock_config, candidate_truth, tmp_path):
    adapter = LinkedInAdapter(config=mock_config, candidate_truth=candidate_truth, offline_mode=True)
    job = JobListing(
        job_id="li_no_spon",
        title="Cloud Architect",
        company="Sydney Corp",
        location="Sydney, Australia",
        work_mode="onsite",
        url="https://www.linkedin.com/jobs/view/999111/",
        source_platform="linkedin",
        application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
        jd_text="Australian citizens only. No visa sponsorship or relocation assistance.",
    )
    score_mock = MagicMock()
    docx = tmp_path / "resume.docx"
    docx.touch()
    pdf = tmp_path / "resume.pdf"
    pdf.touch()

    rec = adapter.apply_easy_apply(job, score_mock, docx, pdf)
    assert rec.status == JobStatus.REJECTED
    assert "VISA_SPONSORSHIP_EXCLUDED" in rec.failure_reason


def test_visa_relocation_gate_disabled_allows_domestic():
    """Verify that when a user customizes config with require_visa_sponsorship=False and require_relocation=False, domestic roles pass."""
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job_india = JobListing(
        job_id="li_india_custom",
        title="OCI Cloud Architect",
        company="Oracle India",
        location="Bengaluru, Karnataka, India",
        url="https://www.linkedin.com/jobs/view/100007/",
        jd_text="Seeking Cloud Architect for Bengaluru office.",
    )
    custom_li_config = {
        "require_visa_sponsorship": False,
        "require_relocation": False,
    }
    passed, reason = VisaRelocationGate.evaluate(job_india, custom_li_config)
    assert passed is True
    assert "PASSED" in reason


def test_candidate_answer_resolver_international_relocation(candidate_truth):
    from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
    resolver = CandidateAnswerResolver(candidate_truth, strict_truth_only=False)

    # Relocation
    res_reloc = resolver.resolve_question("Are you willing to relocate to Europe or Nordic countries?")
    assert res_reloc.can_answer is True
    assert res_reloc.answer_value in ("Yes", "Open to Relocation")

    # Onsite
    res_onsite = resolver.resolve_question("Are you willing to work on-site at customer location?")
    assert res_onsite.can_answer is True
    assert res_onsite.answer_value in ("Yes", "Available")

    # AI Experience
    res_ai = resolver.resolve_question("How many years of experience in Generative AI / LLM?")
    assert res_ai.can_answer is True
    assert res_ai.answer_value == "5"

    # OCI Experience
    res_oci = resolver.resolve_question("How many years of experience in Oracle Cloud Infrastructure (OCI)?")
    assert res_oci.can_answer is True
    assert res_oci.answer_value in ("6.5", "6", "7")


def test_visa_relocation_gate_optional_relocation():
    """Verify that when require_relocation is False, roles with visa sponsorship pass without needing relocation text."""
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_visa_only",
        title="Senior Cloud Architect",
        company="Nordic Tech AB",
        location="Stockholm, Sweden",
        url="https://www.linkedin.com/jobs/view/200001/",
        jd_text="Enterprise cloud transformations. We provide work visa sponsorship for qualified international candidates.",
    )
    custom_cfg = {"require_visa_sponsorship": True, "require_relocation": False}
    passed, reason = VisaRelocationGate.evaluate(job, custom_cfg)
    assert passed is True
    assert "PASSED" in reason


def test_visa_relocation_gate_query_intent_passes():
    """Verify that a role discovered via targeted visa query passes when require_relocation is False."""
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_query_visa",
        title="OCI Solutions Architect",
        company="Global Enterprise",
        location="Amsterdam, Netherlands",
        url="https://www.linkedin.com/jobs/view/200002/",
        jd_text="Lead cloud infrastructure architecture. Excellent compensation and benefits.",
        source_query="OCI Architect visa sponsorship",
    )
    custom_cfg = {"require_visa_sponsorship": True, "require_relocation": False}
    passed, reason = VisaRelocationGate.evaluate(job, custom_cfg)
    assert passed is True
    assert "PASSED" in reason


def test_visa_relocation_gate_negative_exclusion_overrides_query():
    """Verify that negative exclusion clauses strictly reject even if query targeted visa sponsorship."""
    from src.utils.visa_relocation_gate import VisaRelocationGate

    job = JobListing(
        job_id="li_neg_override",
        title="Cloud Architect",
        company="Bank of London",
        location="London, United Kingdom",
        url="https://www.linkedin.com/jobs/view/200003/",
        jd_text="Applicants must have existing right to work without sponsorship. No visa sponsorship available.",
        source_query="Cloud Architect visa sponsorship",
    )
    custom_cfg = {"require_visa_sponsorship": True, "require_relocation": False}
    passed, reason = VisaRelocationGate.evaluate(job, custom_cfg)
    assert passed is False
    assert "VISA_SPONSORSHIP_EXCLUDED" in reason
