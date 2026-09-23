"""Experience parsing utility."""

import re
from typing import Tuple, Optional


def parse_experience(raw_exp: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Parses raw experience text (e.g. '0-0 Yrs', '10-15 Yrs', '8-12 Yrs', '10+ Yrs') into (min_exp, max_exp).

    Returns:
        (min_years, max_years) as floats, or (None, None) if cannot be parsed.
    """
    if not raw_exp:
        return None, None

    raw_exp = str(raw_exp).strip()

    # Match ranges like "0-0 Yrs", "10-15 Yrs", "8-12 years", "12 - 16 Yrs", "0 to 1 Yrs"
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)", raw_exp, re.IGNORECASE)
    if range_match:
        try:
            return float(range_match.group(1)), float(range_match.group(2))
        except ValueError:
            pass

    # Match single numbers like "10+ Yrs", "12 years", "8 Yrs"
    single_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:yrs|years|yr)", raw_exp, re.IGNORECASE)
    if single_match:
        try:
            val = float(single_match.group(1))
            return val, val + 5.0
        except ValueError:
            pass

    return None, None
