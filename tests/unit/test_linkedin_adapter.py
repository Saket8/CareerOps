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
