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

    # Current CTC
    res = resolver.resolve_question("What is your current CTC / salary in Lacs?")
    assert res.can_answer is True
    assert res.answer_value == "30"

    # Expected CTC
    res = resolver.resolve_question("Expected CTC / package?")
    assert res.can_answer is True
    assert res.answer_value in ("30", "35")


def test_resolver_ai_and_python_facts():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # Verified AI experience
    res = resolver.resolve_question("How many years of experience do you have in GenAI / LLM architectures?")
    assert res.can_answer is True
    assert res.answer_value == "2"

    # Verified Python experience
    res = resolver.resolve_question("How many years of experience in Python programming?")
    assert res.can_answer is True
    assert res.answer_value == "5"

    # Verified Kubernetes experience
    res = resolver.resolve_question("Years of experience in Kubernetes / OKE clusters?")
    assert res.can_answer is True
    assert res.answer_value == "5"


def test_resolver_missing_facts_strictly_return_cannot_answer():
    candidate_truth = get_candidate_truth(refresh=True)
    # Explicitly clear fields to test zero-fabrication
    candidate_truth.candidate.kubernetes_experience_years = None
    candidate_truth.candidate.ai_experience_years = None
    candidate_truth.candidate.python_experience_years = None

    resolver = CandidateAnswerResolver(candidate_truth)

    res_k8s = resolver.resolve_question("Kubernetes experience years?")
    assert res_k8s.can_answer is False
    assert "not found in verified candidate facts" in res_k8s.unverified_reason

    res_ai = resolver.resolve_question("GenAI / LLM experience years?")
    assert res_ai.can_answer is False
    assert "not found in verified candidate facts" in res_ai.unverified_reason

    res_py = resolver.resolve_question("Python programming experience years?")
    assert res_py.can_answer is False
    assert "not found in verified candidate facts" in res_py.unverified_reason


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
