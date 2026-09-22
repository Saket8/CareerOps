"""Salary parsing and eligibility evaluation engine.

Strictly enforces:
- Disclosed minimum salary >= 20.0 LPA -> ELIGIBLE
- Undisclosed salary -> ELIGIBLE
- Disclosed minimum salary < 20.0 LPA -> REJECTED (regardless of upper bound)
"""

import re
from typing import Optional, Tuple
from src.models.job import JobSalary, SalaryEligibility
from src.utils.logger import get_logger

logger = get_logger("salary_parser")


UNDISCLOSED_PATTERNS = [
    r"not\s+disclosed",
    r"undisclosed",
    r"best\s+in\s+industry",
    r"as\s+per\s+industry\s+standards",
    r"competitive",
    r"confidential",
    r"to\s+be\s+discussed",
    r"negotiable",
    r"na",
    r"none",
    r"^$",
]


def parse_salary(raw_text: Optional[str], min_threshold_lpa: float = 20.0) -> JobSalary:
    """Parses raw salary string from job posting and evaluates eligibility."""
    if not raw_text or not raw_text.strip():
        return JobSalary(
            min_lpa=None,
            max_lpa=None,
            currency="INR",
            period="per_annum",
            is_disclosed=False,
            eligibility=SalaryEligibility.UNDISCLOSED,
            raw_text="",
            rejection_reason=None,
        )

    cleaned = raw_text.strip().replace(",", "")
    lower = cleaned.lower()

    # Check undisclosed patterns
    for pattern in UNDISCLOSED_PATTERNS:
        if re.search(pattern, lower):
            return JobSalary(
                min_lpa=None,
                max_lpa=None,
                currency="INR",
                period="per_annum",
                is_disclosed=False,
                eligibility=SalaryEligibility.UNDISCLOSED,
                raw_text=raw_text,
                rejection_reason=None,
            )

    # Detect currency (default INR)
    currency = "INR"
    if "$" in cleaned or "usd" in lower:
        currency = "USD"
    elif "€" in cleaned or "eur" in lower:
        currency = "EUR"
    elif "£" in cleaned or "gbp" in lower:
        currency = "GBP"

    # Pattern 1: Range in Lacs/LPA (e.g. "20-30 Lacs P.A.", "20 - 35 LPA", "25.5-40 Lacs")
    range_lacs_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lacs?|lpa|lac|lakhs?)?", lower)
    if range_lacs_match:
        val1 = float(range_lacs_match.group(1))
        val2 = float(range_lacs_match.group(2))
        
        # If numbers are large like 2000000 - 3000000
        if val1 >= 100000:
            val1 = val1 / 100000.0
        if val2 >= 100000:
            val2 = val2 / 100000.0

        min_val = min(val1, val2)
        max_val = max(val1, val2)

        # Monthly check: e.g. "1.5 - 2 Lacs per month" or "per month"
        if "month" in lower or "/m" in lower:
            min_val = min_val * 12.0
            max_val = max_val * 12.0

        is_eligible = min_val >= min_threshold_lpa
        rejection_reason = None if is_eligible else f"Minimum salary ₹{min_val:.1f} LPA is below required floor of ₹{min_threshold_lpa:.1f} LPA"

        return JobSalary(
            min_lpa=round(min_val, 2),
            max_lpa=round(max_val, 2),
            currency=currency,
            period="per_annum",
            is_disclosed=True,
            eligibility=SalaryEligibility.ELIGIBLE if is_eligible else SalaryEligibility.REJECTED,
            raw_text=raw_text,
            rejection_reason=rejection_reason,
        )

    # Pattern 2: Single value with plus or minimum (e.g. "25 Lacs+ P.A.", "30+ LPA", "min 20 Lacs")
    single_lacs_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:\+|plus)?\s*(?:lacs?|lpa|lac|lakhs?)", lower)
    if single_lacs_match:
        val = float(single_lacs_match.group(1))
        if val >= 100000:
            val = val / 100000.0

        if "month" in lower or "/m" in lower:
            val = val * 12.0

        is_eligible = val >= min_threshold_lpa
        rejection_reason = None if is_eligible else f"Minimum salary ₹{val:.1f} LPA is below required floor of ₹{min_threshold_lpa:.1f} LPA"

        return JobSalary(
            min_lpa=round(val, 2),
            max_lpa=None,
            currency=currency,
            period="per_annum",
            is_disclosed=True,
            eligibility=SalaryEligibility.ELIGIBLE if is_eligible else SalaryEligibility.REJECTED,
            raw_text=raw_text,
            rejection_reason=rejection_reason,
        )

    # Pattern 3: Absolute numbers without explicitly writing Lacs (e.g. "2000000 - 3500000 P.A.")
    abs_range_match = re.search(r"(\d{6,8})\s*(?:-|to)\s*(\d{6,8})", cleaned)
    if abs_range_match:
        min_val = float(abs_range_match.group(1)) / 100000.0
        max_val = float(abs_range_match.group(2)) / 100000.0
        if "month" in lower:
            min_val *= 12.0
            max_val *= 12.0

        is_eligible = min_val >= min_threshold_lpa
        rejection_reason = None if is_eligible else f"Minimum salary ₹{min_val:.1f} LPA is below required floor of ₹{min_threshold_lpa:.1f} LPA"

        return JobSalary(
            min_lpa=round(min_val, 2),
            max_lpa=round(max_val, 2),
            currency=currency,
            period="per_annum",
            is_disclosed=True,
            eligibility=SalaryEligibility.ELIGIBLE if is_eligible else SalaryEligibility.REJECTED,
            raw_text=raw_text,
            rejection_reason=rejection_reason,
        )

    # If format is unrecognized, treat as undisclosed rather than fabricating a value
    logger.info(f"Unrecognized salary format: '{raw_text}', treating as undisclosed")
    return JobSalary(
        min_lpa=None,
        max_lpa=None,
        currency=currency,
        period="per_annum",
        is_disclosed=False,
        eligibility=SalaryEligibility.UNDISCLOSED,
        raw_text=raw_text,
        rejection_reason=None,
    )
