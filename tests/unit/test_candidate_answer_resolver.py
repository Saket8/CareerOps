"""Unit tests for CandidateAnswerResolver verifying zero-hallucination truth resolution."""

import pytest
from candidate.profile_extractor import get_candidate_truth
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver


def test_resolver_standard_fields():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # Experience question
    res = resolver.resolve_question("Total years of experience")
    assert res.can_answer is True
    assert str(res.answer_value) in ("10", "12")

    # Notice period
    res = resolver.resolve_question("What is your official notice period in days?")
    assert res.can_answer is True
    assert str(candidate_truth.candidate.notice_period_days) in str(res.answer_value)

    # Current Location
    res = resolver.resolve_question("Current residing location / city")
    assert res.can_answer is True
    assert "Noida" in str(res.answer_value) or "Delhi" in str(res.answer_value)

    # Cloud Experience
    res = resolver.resolve_question("Years of experience in Oracle Cloud Infrastructure (OCI)")
    assert res.can_answer is True
    assert str(int(candidate_truth.candidate.cloud_experience_years)) in str(res.answer_value)


def test_resolver_unverified_question_prevents_hallucination():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # Question about unverified skill / trivia
    res = resolver.resolve_question("Do you have hands-on experience in Cobol mainframes?")
    assert res.can_answer is False
    assert res.answer_value is None
    assert "candidate truth" in res.unverified_reason or "Unverified" in res.unverified_reason

    # Question about unverified credential
    res = resolver.resolve_question("What was your high school graduation GPA percentage?")
    assert res.can_answer is False
    assert res.answer_value is None
