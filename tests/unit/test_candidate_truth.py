"""Unit tests for candidate truth layer and resume verification."""

import pytest
from pathlib import Path
from candidate.profile_extractor import get_candidate_truth, verify_facts_against_resume, MASTER_RESUME_PATH


def test_candidate_truth_loading():
    facts = get_candidate_truth(refresh=True)
    assert facts.candidate.name == "Saket Saurav"
    assert facts.candidate.total_experience_years == 12
    assert facts.candidate.cloud_experience_years >= 6
    assert len(facts.certifications) >= 6
    assert len(facts.employment_history) == 4


def test_no_fabrication_against_master_resume():
    facts = get_candidate_truth(refresh=True)
    assert MASTER_RESUME_PATH.exists(), "Master resume must exist"
    assert verify_facts_against_resume(facts, MASTER_RESUME_PATH) is True


def test_certifications_are_verified():
    facts = get_candidate_truth(refresh=True)
    for cert in facts.certifications:
        assert cert.verified is True
        assert cert.source == "resumes/master/Saket_Saurav_OCI.docx"
