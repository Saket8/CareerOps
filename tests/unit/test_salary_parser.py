"""Unit tests for salary parser strictly enforcing ₹20 LPA eligibility rules."""

import pytest
from src.utils.salary_parser import parse_salary
from src.models.job import SalaryEligibility


@pytest.mark.parametrize(
    "raw_salary, expected_eligibility, expected_min, expected_disclosed",
    [
        # Accepted Disclosed Ranges (min >= 20)
        ("20-30 Lacs P.A.", SalaryEligibility.ELIGIBLE, 20.0, True),
        ("25-40 LPA", SalaryEligibility.ELIGIBLE, 25.0, True),
        ("30 Lacs+ P.A.", SalaryEligibility.ELIGIBLE, 30.0, True),
        ("₹ 22,00,000 - 35,00,000 P.A.", SalaryEligibility.ELIGIBLE, 22.0, True),
        ("20 - 25 Lacs", SalaryEligibility.ELIGIBLE, 20.0, True),
        
        # Rejected Disclosed Ranges (min < 20, even if upper bound is high)
        ("15-25 Lacs P.A.", SalaryEligibility.REJECTED, 15.0, True),
        ("18-30 LPA", SalaryEligibility.REJECTED, 18.0, True),
        ("10-20 LPA", SalaryEligibility.REJECTED, 10.0, True),
        ("12-18 Lacs P.A.", SalaryEligibility.REJECTED, 12.0, True),
        ("19.5 - 28 Lacs", SalaryEligibility.REJECTED, 19.5, True),
        ("15,00,000 - 45,00,000 PA", SalaryEligibility.REJECTED, 15.0, True),

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
    result = parse_salary("16-25 Lacs P.A.", min_threshold_lpa=20.0)
    assert result.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹20.0 LPA" in result.rejection_reason


def test_salary_parsing_with_25lpa_floor():
    # Min >= 25 is eligible
    res_25 = parse_salary("25-40 LPA", min_threshold_lpa=25.0)
    assert res_25.eligibility == SalaryEligibility.ELIGIBLE
    assert res_25.min_lpa == 25.0

    # No upper ceiling: 30-50 LPA or 50+ LPA is accepted
    res_high = parse_salary("30-60 Lacs P.A.", min_threshold_lpa=25.0)
    assert res_high.eligibility == SalaryEligibility.ELIGIBLE
    assert res_high.min_lpa == 30.0

    # Min < 25 is rejected (even if upper bound is high)
    res_reject = parse_salary("20-35 Lacs P.A.", min_threshold_lpa=25.0)
    assert res_reject.eligibility == SalaryEligibility.REJECTED
    assert "below required floor of ₹25.0 LPA" in res_reject.rejection_reason

    # Undisclosed is still accepted for analysis
    res_undisclosed = parse_salary("Not Disclosed", min_threshold_lpa=25.0)
    assert res_undisclosed.eligibility == SalaryEligibility.UNDISCLOSED
