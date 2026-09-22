"""Unit tests for salary parser enforcing range ceiling (max >= threshold) eligibility rules."""

import pytest
from src.utils.salary_parser import parse_salary
from src.models.job import SalaryEligibility


@pytest.mark.parametrize(
    "raw_salary, expected_eligibility, expected_min, expected_disclosed",
    [
        # Accepted Disclosed Ranges (max >= 20)
        ("20-30 Lacs P.A.", SalaryEligibility.ELIGIBLE, 20.0, True),
        ("25-40 LPA", SalaryEligibility.ELIGIBLE, 25.0, True),
        ("30 Lacs+ P.A.", SalaryEligibility.ELIGIBLE, 30.0, True),
        ("₹ 22,00,000 - 35,00,000 P.A.", SalaryEligibility.ELIGIBLE, 22.0, True),
        ("20 - 25 Lacs", SalaryEligibility.ELIGIBLE, 20.0, True),
        # Range starting below 20 but ceiling >= 20 is accepted
        ("18-30 LPA", SalaryEligibility.ELIGIBLE, 18.0, True),
        ("15-25 Lacs P.A.", SalaryEligibility.ELIGIBLE, 15.0, True),
        ("10-20 LPA", SalaryEligibility.ELIGIBLE, 10.0, True),
        ("15,00,000 - 45,00,000 PA", SalaryEligibility.ELIGIBLE, 15.0, True),
        
        # Rejected Disclosed Ranges (max < 20)
        ("12-18 Lacs P.A.", SalaryEligibility.REJECTED, 12.0, True),
        ("10-16 Lacs P.A.", SalaryEligibility.REJECTED, 10.0, True),
        ("8-15 LPA", SalaryEligibility.REJECTED, 8.0, True),
        ("14 - 19 Lacs", SalaryEligibility.REJECTED, 14.0, True),

        # Undisclosed Salaries (Allowed for analysis)
        ("Not Disclosed", SalaryEligibility.UNDISCLOSED, None, False),
        ("Not disclosed by recruiter", SalaryEligibility.UNDISCLOSED, None, False),
        ("Undisclosed", SalaryEligibility.UNDISCLOSED, None, False),
        ("Best in Industry", SalaryEligibility.UNDISCLOSED, None, False),
        ("", SalaryEligibility.UNDISCLOSED, None, False),
        (None, SalaryEligibility.UNDISCLOSED, None, False),
    ],
)
def test_salary_parsing_cases(raw_salary, expected_eligibility, expected_min, expected_disclosed):
    result = parse_salary(raw_salary, min_threshold_lpa=20.0)
    assert result.eligibility == expected_eligibility
    assert result.is_disclosed == expected_disclosed
    if expected_min is not None:
        assert result.min_lpa == expected_min
    else:
        assert result.min_lpa is None


def test_rejection_reason_is_populated():
    result = parse_salary("12-18 Lacs P.A.", min_threshold_lpa=20.0)
    assert result.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹20.0 LPA" in result.rejection_reason


def test_salary_parsing_with_25lpa_floor():
    # Range exceeding 25 LPA is eligible
    res_25 = parse_salary("25-40 LPA", min_threshold_lpa=25.0)
    assert res_25.eligibility == SalaryEligibility.ELIGIBLE
    assert res_25.min_lpa == 25.0

    # Range starting below 25 but exceeding 25 is eligible
    res_overlap = parse_salary("20-35 Lacs P.A.", min_threshold_lpa=25.0)
    assert res_overlap.eligibility == SalaryEligibility.ELIGIBLE
    assert res_overlap.min_lpa == 20.0

    # Range where max < 25 is strictly rejected
    res_reject = parse_salary("15-22 Lacs P.A.", min_threshold_lpa=25.0)
    assert res_reject.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹25.0 LPA" in res_reject.rejection_reason


def test_salary_parsing_with_30lpa_floor():
    # Min >= 30 is eligible
    res_30 = parse_salary("30-45 LPA")
    assert res_30.eligibility == SalaryEligibility.ELIGIBLE
    assert res_30.min_lpa == 30.0

    # Higher ranges are eligible
    res_high = parse_salary("35-60 Lacs P.A.")
    assert res_high.eligibility == SalaryEligibility.ELIGIBLE
    assert res_high.min_lpa == 35.0

    # Range starting < 30 but exceeding 30 (max >= 30) is ACCEPTABLE per candidate requirement
    res_overlap_25 = parse_salary("25-40 Lacs P.A.")
    assert res_overlap_25.eligibility == SalaryEligibility.ELIGIBLE
    assert res_overlap_25.min_lpa == 25.0
    assert res_overlap_25.max_lpa == 40.0

    res_overlap_20 = parse_salary("20-35 LPA")
    assert res_overlap_20.eligibility == SalaryEligibility.ELIGIBLE
    assert res_overlap_20.min_lpa == 20.0
    assert res_overlap_20.max_lpa == 35.0

    res_overlap_32 = parse_salary("25-32.5 Lacs P.A.")
    assert res_overlap_32.eligibility == SalaryEligibility.ELIGIBLE
    assert res_overlap_32.min_lpa == 25.0
    assert res_overlap_32.max_lpa == 32.5

    # Range where max is strictly < 30 is REJECTED
    res_reject_25 = parse_salary("15-25 Lacs P.A.")
    assert res_reject_25.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹30.0 LPA" in res_reject_25.rejection_reason

    res_reject_28 = parse_salary("18-28 LPA")
    assert res_reject_28.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹30.0 LPA" in res_reject_28.rejection_reason

    res_reject_22 = parse_salary("15-22.5 Lacs P.A.")
    assert res_reject_22.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹30.0 LPA" in res_reject_22.rejection_reason

    # Single value < 30 is rejected
    res_single_reject = parse_salary("25 Lacs P.A.")
    assert res_single_reject.eligibility == SalaryEligibility.REJECTED

    # Single value >= 30 is eligible
    res_single_ok = parse_salary("35 Lacs P.A.")
    assert res_single_ok.eligibility == SalaryEligibility.ELIGIBLE

    # Undisclosed is still accepted
    res_undisclosed = parse_salary("Not Disclosed")
    assert res_undisclosed.eligibility == SalaryEligibility.UNDISCLOSED
