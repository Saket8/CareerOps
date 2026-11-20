"""Tests for Tier-1 GCC and Cloud Hyperscaler Priority Detection, Scoring Boost, and Queue Prioritization."""

import pytest
from src.utils.tier1_detector import is_tier_1_company, get_tier_1_matched_name
from src.models.job import JobListing, JobSalary, SalaryEligibility
from src.models.score import JobScore
from src.agents.qualification import QualificationAgent
from candidate.profile_extractor import get_candidate_truth


def test_tier1_company_detection():
    # True positives: Tier-1 GCCs & Hyperscalers
    tier1_targets = [
        "Oracle India Pvt. Ltd.",
        "Oracle",
        "Walmart Global Tech India",
        "Walmart",
        "JPMorgan Chase Bank, N.A.",
        "JP Morgan Services India",
        "Goldman Sachs Services Private Limited",
        "Wells Fargo International Solutions",
        "Amazon Web Services",
        "AWS India",
        "Microsoft Corporation India",
        "Google Cloud India",
        "Cisco Systems India",
        "VMware Software India",
        "Optum Global Solutions",
        "UnitedHealth Group",
        "Target Corporation",
        "Fidelity Investments",
        "Barclays Global Service Centre",
        "Morgan Stanley Advantage Services",
        "BNY Mellon Technology",
        "ServiceNow India",
        "Snowflake Computing",
        "Salesforce.com India",
    ]
    for comp in tier1_targets:
        assert is_tier_1_company(comp) is True, f"Failed to detect Tier-1 company: '{comp}'"
        matched = get_tier_1_matched_name(comp)
        assert matched is not None, f"Expected matched name for: '{comp}'"

    # True negatives: IT Services vendors & random entities
    services_firms = [
        "Tata Consultancy Services",
        "Wipro Limited",
        "Infosys",
        "Cognizant Technology Solutions",
        "Sonata Software",
        "Birlasoft",
        "HCL Technologies",
        "Tech Mahindra",
        "LTIMindtree",
        "Mphasis",
        "Hexaware",
    ]
    for comp in services_firms:
        assert is_tier_1_company(comp) is False, f"False positive on services vendor: '{comp}'"


def test_qualification_tier1_boost():
    candidate_truth = get_candidate_truth(refresh=True)

    class MockJobRepo:
        def save_score(self, score): pass
        def save_evidence(self, evidence): pass
        def get(self, job_id): return None
        def update_status(self, job_id, status): pass
        def save_job(self, job): pass

    config = {
        "application": {"match_threshold": 70.0, "high_match_threshold": 85.0},
        "safety": {"blocked_companies": ["cognizant", "cts"], "excluded_job_titles": []},
        "search": {
            "tier_1_priority_companies": [
                "Oracle", "Walmart", "JPMorgan", "Wells Fargo", "Goldman Sachs", "Google", "AWS", "Microsoft"
            ]
        }
    }

    agent = QualificationAgent(job_repo=MockJobRepo(), candidate_truth=candidate_truth, config=config)

    jd_text = """
    We are seeking a Cloud Solutions Architect to join our Enterprise Architecture team.
    Key Responsibilities:
    - Architect scalable cloud infrastructure using OCI or AWS.
    - Design zero trust network topology, landing zones, and IAM federation.
    - Lead Kubernetes container deployments (OKE) and automate infrastructure using Terraform.
    - Modernize cloud operations with AI and GenAI architectures.
    """

    job_tier1 = JobListing(
        job_id="test_walmart_001",
        title="Enterprise Cloud Solutions Architect",
        company="Walmart Global Tech India",
        location="Bengaluru, India",
        url="https://www.naukri.com/job-listings-walmart-001",
        jd_text=jd_text,
        salary=JobSalary(is_disclosed=False, eligibility=SalaryEligibility.UNDISCLOSED),
        experience_min=10.0,
        experience_max=16.0,
    )

    job_services = JobListing(
        job_id="test_services_001",
        title="Enterprise Cloud Solutions Architect",
        company="Generic IT Services Firm",
        location="Noida, India",
        url="https://www.naukri.com/job-listings-services-001",
        jd_text=jd_text,
        salary=JobSalary(is_disclosed=False, eligibility=SalaryEligibility.UNDISCLOSED),
        experience_min=10.0,
        experience_max=16.0,
    )

    score_tier1, evidence_tier1 = agent.evaluate_job(job_tier1)
    score_services, evidence_services = agent.evaluate_job(job_services)

    # 1. Tier 1 overall score should be strictly boosted by 10.0 points
    assert score_tier1.overall_score == min(100.0, round(score_services.overall_score + 10.0, 1))

    # 2. Tier 1 categories should include TIER_1_GCC_HYPERSCALER
    assert "TIER_1_GCC_HYPERSCALER" in score_tier1.categories
    assert "TIER_1_GCC_HYPERSCALER" not in score_services.categories

    # 3. Evidence should record Tier 1 facts and signals
    assert any("Tier-1 GCC / Hyperscaler priority employer" in fact for fact in evidence_tier1.observed_facts)
    assert any("Tier-1 compensation bands" in signal for signal in evidence_tier1.inferred_signals)


def test_queue_sorting_prioritizes_tier1():
    from src.utils.tier1_detector import is_tier_1_company

    items = [
        (JobListing(job_id="1", title="Architect", company="Generic IT Services Firm", location="Noida", url="https://example.com/1"), JobScore(job_id="1", overall_score=85.0, architecture_score=80.0, cloud_score=80.0, oci_score=80.0, ai_score=70.0, agentic_ai_score=70.0, kubernetes_score=80.0, security_score=80.0, multicloud_score=80.0, experience_alignment=80.0, skill_alignment=80.0)),
        (JobListing(job_id="2", title="Cloud Architect", company="Walmart Global Tech", location="Bengaluru", url="https://example.com/2"), JobScore(job_id="2", overall_score=82.0, architecture_score=80.0, cloud_score=80.0, oci_score=80.0, ai_score=70.0, agentic_ai_score=70.0, kubernetes_score=80.0, security_score=80.0, multicloud_score=80.0, experience_alignment=80.0, skill_alignment=80.0)),
        (JobListing(job_id="3", title="Solutions Architect", company="Oracle India", location="Hyderabad", url="https://example.com/3"), JobScore(job_id="3", overall_score=90.0, architecture_score=90.0, cloud_score=90.0, oci_score=90.0, ai_score=70.0, agentic_ai_score=70.0, kubernetes_score=80.0, security_score=80.0, multicloud_score=80.0, experience_alignment=80.0, skill_alignment=80.0)),
        (JobListing(job_id="4", title="Lead Architect", company="Sonata Software", location="Pune", url="https://example.com/4"), JobScore(job_id="4", overall_score=88.0, architecture_score=80.0, cloud_score=80.0, oci_score=80.0, ai_score=70.0, agentic_ai_score=70.0, kubernetes_score=80.0, security_score=80.0, multicloud_score=80.0, experience_alignment=80.0, skill_alignment=80.0)),
    ]

    # Sort queue with Tier-1 priority
    sorted_items = sorted(
        items,
        key=lambda item: (
            1 if is_tier_1_company(item[0].company) else 0,
            item[1].overall_score,
        ),
        reverse=True,
    )

    top_companies = [item[0].company for item in sorted_items]
    # Oracle (90.0) and Walmart (82.0) must be at index 0 and 1 ahead of Sonata (88.0) and Generic (85.0)
    assert top_companies[0] == "Oracle India"
    assert top_companies[1] == "Walmart Global Tech"
    assert top_companies[2] == "Sonata Software"
    assert top_companies[3] == "Generic IT Services Firm"
