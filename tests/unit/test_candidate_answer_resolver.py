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


def test_resolver_yes_no_vs_duration_intent():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # 1. Cloud: Yes/No vs Duration
    res_yn = resolver.resolve_question("Do you have any experience in cloud ?")
    assert res_yn.can_answer is True
    assert res_yn.answer_value == "Yes"

    res_dur = resolver.resolve_question("How many years of experience do you have in cloud ?")
    assert res_dur.can_answer is True
    assert res_dur.answer_value == "6"

    # 2. OCI: Yes/No vs Duration
    res_oci_yn = resolver.resolve_question("Have you worked on Oracle Cloud Infrastructure (OCI)?")
    assert res_oci_yn.can_answer is True
    assert res_oci_yn.answer_value == "Yes"

    # 3. Python: Yes/No vs Duration
    res_py_yn = resolver.resolve_question("Do you have experience in Python?")
    assert res_py_yn.can_answer is True
    assert res_py_yn.answer_value == "Yes"

    res_py_dur = resolver.resolve_question("How many years of experience in Python?")
    assert res_py_dur.can_answer is True
    assert res_py_dur.answer_value == "5"

    # 4. Total experience: Yes/No vs Duration
    res_tot_yn = resolver.resolve_question("Do you have 10+ years of total experience?")
    assert res_tot_yn.can_answer is True
    assert res_tot_yn.answer_value == "Yes"

    res_tot_dur = resolver.resolve_question("Total years of experience")
    assert res_tot_dur.can_answer is True
    assert res_tot_dur.answer_value == "12"


def test_resolver_expanded_screening_questions():
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # 1. Generative AI with whitespace / punctuation variations
    res_genai = resolver.resolve_question("How many years of experience do you have in Generative Ai?")
    assert res_genai.can_answer is True
    assert res_genai.answer_value == "2"

    res_genai_yn = resolver.resolve_question("Do you have experience in Generative AI?")
    assert res_genai_yn.can_answer is True
    assert res_genai_yn.answer_value == "Yes"

    # 2. AIOps
    res_aiops = resolver.resolve_question("How many years of experience do you have in AIOps?")
    assert res_aiops.can_answer is True
    assert res_aiops.answer_value == "2"

    # 3. System Design & Solutioning
    res_sys = resolver.resolve_question("How many years of experience do you have in System Design and solutioning?")
    assert res_sys.can_answer is True
    assert res_sys.answer_value == "6"

    # 4. Implementation
    res_impl = resolver.resolve_question("How many years of experience do you have in Implementation?")
    assert res_impl.can_answer is True
    assert res_impl.answer_value == "6"

    # 5. Aggregate percentage in highest qualification (B.Tech 70%)
    res_pct = resolver.resolve_question("What is your aggregate percentage in your highest qualification (B.Tech/M.Tech)?")
    assert res_pct.can_answer is True
    assert res_pct.answer_value == "70"

    # 6. Current organization & role
    res_org = resolver.resolve_question("What is your current company / organization?")
    assert res_org.can_answer is True
    assert res_org.answer_value == "Cognizant"

    res_role = resolver.resolve_question("What is your current designation / role?")
    assert res_role.can_answer is True
    assert res_role.answer_value == "Principal Cloud Engineer (OCI) / Manager-Projects"

    # 7. Currently employed
    res_emp = resolver.resolve_question("Are you currently employed / working?")
    assert res_emp.can_answer is True
    assert res_emp.answer_value == "Yes"

    # 8. Enterprise Architecture
    res_ea = resolver.resolve_question("How many years of experience do you have in Enterprise Architecture?")
    assert res_ea.can_answer is True
    assert res_ea.answer_value == "6"

    res_ea_yn = resolver.resolve_question("Do you have experience in Enterprise Architecture?")
    assert res_ea_yn.can_answer is True
    assert res_ea_yn.answer_value == "Yes"

    # 9. Observability & Monitoring
    res_obs = resolver.resolve_question("How many years of experience do you have in Observability?")
    assert res_obs.can_answer is True
    assert res_obs.answer_value == "3"

    res_obs_yn = resolver.resolve_question("Do you have hands-on experience in Observability and Monitoring tools?")
    assert res_obs_yn.can_answer is True
    assert res_obs_yn.answer_value == "Yes"

    # 10. Multi-Cloud (GCP / AWS / Azure)
    res_gcp = resolver.resolve_question("How many years of experience do you have in GCP?")
    assert res_gcp.can_answer is True
    assert res_gcp.answer_value == "3"

    res_gcp_yn = resolver.resolve_question("Do you have experience in Google Cloud Platform (GCP)?")
    assert res_gcp_yn.can_answer is True
    assert res_gcp_yn.answer_value == "Yes"

    # 11. DevOps & Terraform
    res_devops = resolver.resolve_question("How many years of experience do you have in DevOps and CI/CD?")
    assert res_devops.can_answer is True
    assert res_devops.answer_value == "5"

    # 12. Machine Learning / Deep Learning
    res_ml = resolver.resolve_question("How many years of experience do you have in Machine Learning?")
    assert res_ml.can_answer is True
    assert res_ml.answer_value == "2"

    # 13. Offer in Hand / Competing Offers
    res_offer = resolver.resolve_question("Do you have any offer in hand? If yes, mention CTC.")
    assert res_offer.can_answer is True
    assert res_offer.answer_value == "No"

    # 14. Interview Availability
    res_avail = resolver.resolve_question("Interview Availability")
    assert res_avail.can_answer is True
    assert res_avail.answer_value in ("Available", "Yes")

    res_avail_yn = resolver.resolve_question("Are you available to attend interview this week?")
    assert res_avail_yn.can_answer is True
    assert res_avail_yn.answer_value == "Yes"

    # 15. Hybrid Work Model
    res_hybrid = resolver.resolve_question("Are you okay with hybrid work model? (3-4 days from office location)")
    assert res_hybrid.can_answer is True
    assert res_hybrid.answer_value == "Yes"

    # 16. Unlisted Technologies (ServiceNow, SAP, Java) -> Truthful 0 years or No
    res_snow = resolver.resolve_question("How many years of experience do you have in Servicenow?")
    assert res_snow.can_answer is True
    assert res_snow.answer_value == "0"

    res_snow_yn = resolver.resolve_question("Do you have hands-on experience in ServiceNow?")
    assert res_snow_yn.can_answer is True
    assert res_snow_yn.answer_value == "No"

    res_sap = resolver.resolve_question("Years of experience in SAP?")
    assert res_sap.can_answer is True
    assert res_sap.answer_value == "0"


def test_resolver_new_chatbot_screening_questions():
    """Validates the 9 newly mapped candidate screening questions from live recruiter chatbots."""
    candidate_truth = get_candidate_truth(refresh=True)
    resolver = CandidateAnswerResolver(candidate_truth)

    # 1. Relevant as an Architect
    res = resolver.resolve_question("Relevant as an Architect")
    assert res.can_answer is True
    assert res.answer_value == "6"

    # 2. Client Interaction
    res = resolver.resolve_question("How many years of experience do you have in Client Interaction?")
    assert res.can_answer is True
    assert res.answer_value == "10"

    # 3. AIML normalization
    res = resolver.resolve_question("How many years of experience do you have in Aiml?")
    assert res.can_answer is True
    assert res.answer_value == "2"

    # 4. Contract / 12 Months Contract
    res = resolver.resolve_question("Are you open for 12 Months Contract?")
    assert res.can_answer is True
    assert res.answer_value == "Yes"

    # 5. Oracle PaaS
    res = resolver.resolve_question("How many years of experience do you have in Oracle Paas?")
    assert res.can_answer is True
    assert res.answer_value == "6"

    # 6. Full Name as per Aadhar
    res = resolver.resolve_question("Full Name as per Aadhar? First Name?  Middle Name ? Last Name?")
    assert res.can_answer is True
    assert res.answer_value == "Saket Saurav"

    # 7. Snowflake from scratch
    res = resolver.resolve_question("Have you worked on setting up Snowflake accounts, warehouses, and databases from scratch?")
    assert res.can_answer is True
    assert res.answer_value == "Yes"

    # 8. Highest Educational Qualification
    res = resolver.resolve_question("Highest Educational Qualification")
    assert res.can_answer is True
    assert "Bachelor of Technology" in res.answer_value or "B.Tech" in res.answer_value

    # 9. Databricks
    res = resolver.resolve_question("What is your years of experience in Databricks")
    assert res.can_answer is True
    assert res.answer_value == "4"






