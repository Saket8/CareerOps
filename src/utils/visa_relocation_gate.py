"""Visa Sponsorship and Relocation Assistance Gate for LinkedIn Applications.

Strictly verifies that international job postings affirmatively offer employer
visa sponsorship for candidates from India and provide relocation assistance,
while rejecting roles with negative exclusion language or domestic non-sponsorship.
"""

import re
from typing import Tuple, Dict, Any, List, Optional
from src.models.job import JobListing
from src.utils.logger import get_logger

logger = get_logger("visa_relocation_gate")

# Explicit negative indicators (instant disqualification)
NEGATIVE_SPONSORSHIP_PATTERNS = [
    re.compile(r"\b(no|not|cannot|can't|unable to|will not|won't|does not|doesn't|not able to)\s+(provide|offer|grant|support)?\s*(visa\s+)?sponsorship\b", re.I),
    re.compile(r"\bsponsorship\s+(is\s+)?(not|never)\s+(available|offered|provided|supported|considered)\b", re.I),
    re.compile(r"\b(not|never)\s+(eligible|considered)\s+for\s+(visa\s+)?sponsorship\b", re.I),
    re.compile(r"\bwithout\s+(the\s+)?(need\s+for\s+|need\s+of\s+|requiring\s+)?(employer\s+|company\s+)?(visa\s+)?sponsorship\b", re.I),
    re.compile(r"\bno\s+work\s+visa\s+sponsorship\b", re.I),
    re.compile(r"\b(authorized|authorised)\s+to\s+work\s+in\s+[^.\n]+without\s+(the\s+)?(need\s+for\s+|need\s+of\s+)?sponsorship\b", re.I),
    re.compile(r"\bmust\s+have\s+(the\s+)?(existing\s+|valid\s+|current\s+)?(legal\s+)?right\s+to\s+work\s+without\s+sponsorship\b", re.I),
    re.compile(r"\bno\s+third\s*party\s+or\s+visa\s+sponsorship\b", re.I),
    re.compile(r"\b(us\s+citizens|green\s+card|eu\s+citizens|uk\s+citizens|australian\s+citizens|pr\s+holders?)\s+only\b", re.I),
    re.compile(r"\b(not\s+open\s+to|cannot\s+accept)\s+international\s+applicants\b", re.I),
    re.compile(r"\bunable\s+to\s+sponsor\b", re.I),
    re.compile(r"\bcannot\s+sponsor\b", re.I),
    re.compile(r"\bno\s+sponsorship\b", re.I),
]

NEGATIVE_RELOCATION_PATTERNS = [
    re.compile(r"\b(no|not|cannot|unable to|will not)\s+(provide|offer)?\s*relocation(\s+assistance|\s+package|\s+support)?\b", re.I),
    re.compile(r"\brelocation\s+(is\s+)?(not|never)\s+(provided|offered|available|supported|covered|reimbursed)\b", re.I),
    re.compile(r"\brelocation\s*:\s*(no|none|n/a|not available|not offered)\b", re.I),
    re.compile(r"\bno\s+relocation\b", re.I),
    re.compile(r"\blocal\s+candidates\s+only\b", re.I),
    re.compile(r"\bno\s+relocation\s+(assistance|package|support|allowance|bonus|expenses)\b", re.I),
]

# Explicit positive indicators (mandatory requirement)
POSITIVE_SPONSORSHIP_PATTERNS = [
    re.compile(r"\bvisa\s+sponsorship\b", re.I),
    re.compile(r"\b(will|can|open to|able to|offer(s)?|provide(s)?|support(s)?)\s+(visa\s+)?sponsorship\b", re.I),
    re.compile(r"\bsponsorship\s+(is\s+)?(available|provided|offered|supported)\b", re.I),
    re.compile(r"\b(sponsor|sponsoring)\s+(work\s+)?(visas?|permits?|candidates?|applicants?|foreign\s+nationals?|international\s+talent)\b", re.I),
    re.compile(r"\bvisa\s+(support|assistance|processing|facilitation)\b", re.I),
    re.compile(r"\bwork\s+(permit|authorization)\s+sponsorship\b", re.I),
    re.compile(r"\b(international|global|overseas)\s+applicants?\s+(are\s+)?welcome\b", re.I),
    re.compile(r"\bsponsorship\s*:\s*(yes|available|provided|offered|true)\b", re.I),
    re.compile(r"\b(visa|sponsorship)\s*&\s*relocation\b", re.I),
    re.compile(r"\brelocation\s*&\s*(visa|sponsorship)\b", re.I),
    re.compile(r"\bvisa\s+and\s+relocation\b", re.I),
    re.compile(r"\brelocation\s+and\s+visa\b", re.I),
    re.compile(r"\bcandidates\s+requiring\s+sponsorship\s+(are\s+)?(welcome|considered|encouraged)\b", re.I),
    re.compile(r"\bwilling\s+to\s+sponsor\b", re.I),
]

POSITIVE_RELOCATION_PATTERNS = [
    re.compile(r"\brelocation\s+(assistance|package|support|bonus|allowance|stipend|expenses|coverage|budget|benefit)\b", re.I),
    re.compile(r"\brelocation\s+(is\s+)?(provided|offered|available|covered|included|supported|reimbursed)\b", re.I),
    re.compile(r"\b(offer(s)?|provide(s)?|support(s)?|assist(s)?\s+with)\s+relocation\b", re.I),
    re.compile(r"\b(reimburse(s)?|cover(s)?)\s+relocation\b", re.I),
    re.compile(r"\brelocation\s*:\s*(yes|available|provided|offered|true|included)\b", re.I),
    re.compile(r"\binternational\s+relocation\b", re.I),
    re.compile(r"\brelocation\s+to\s+[a-zA-Z\s]+\s+(provided|offered|supported|available)\b", re.I),
    re.compile(r"\bhelp\s+(you\s+)?relocate\b", re.I),
    re.compile(r"\bcomprehensive\s+relocation\b", re.I),
    re.compile(r"\bfull\s+relocation\b", re.I),
    re.compile(r"\brelocation\s+budget\b", re.I),
    re.compile(r"\brelocation\s+flight\b", re.I),
]

DOMESTIC_INDIA_INDICATORS = [
    "india", "noida", "gurgaon", "gurugram", "delhi", "bengaluru", "bangalore",
    "pune", "hyderabad", "mumbai", "chennai", "kolkata", "ahmedabad", "pan india",
]


class VisaRelocationGate:
    """Evaluates whether a LinkedIn job listing satisfies visa sponsorship and relocation prerequisites."""

    @classmethod
    def evaluate(
        cls,
        job: JobListing,
        li_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Evaluates a job listing against visa sponsorship and relocation criteria.

        Returns:
            Tuple[bool, str]: (passed, reason_message)
        """
        config = li_config or {}
        req_sponsorship = bool(config.get("require_visa_sponsorship", True))
        req_relocation = bool(config.get("require_relocation", True))

        # Check if domestic India role
        loc = (job.location or "").lower()
        is_domestic = any(d in loc for d in DOMESTIC_INDIA_INDICATORS)
        
        # If the job is located inside India, it cannot provide visa sponsorship from India or international relocation
        if is_domestic:
            return (
                False,
                f"DOMESTIC_INDIA_ROLE: Job location '{job.location}' is within India. "
                "LinkedIn applications are reserved strictly for international opportunities offering visa sponsorship from India and relocation assistance.",
            )

        # Combine all descriptive text
        text_parts = [
            getattr(job, "title", "") or "",
            getattr(job, "jd_text", "") or "",
            getattr(job, "description_raw", "") or "",
            getattr(job, "description_cleaned", "") or "",
            getattr(job, "source_query", "") or "",
            getattr(job, "discovered_via_query", "") or "",
        ]
        combined_text = "\n".join(text_parts).lower()

        # 1. Negative Exclusion Checks (Immediate Rejection)
        for pat in NEGATIVE_SPONSORSHIP_PATTERNS:
            match = pat.search(combined_text)
            if match:
                matched_phrase = match.group(0).strip()
                return (
                    False,
                    f"VISA_SPONSORSHIP_EXCLUDED: Posting explicitly excludes visa sponsorship ('{matched_phrase}').",
                )

        for pat in NEGATIVE_RELOCATION_PATTERNS:
            match = pat.search(combined_text)
            if match:
                matched_phrase = match.group(0).strip()
                return (
                    False,
                    f"RELOCATION_EXCLUDED: Posting explicitly excludes relocation assistance ('{matched_phrase}').",
                )

        # 2. Positive Verification: Visa Sponsorship
        has_sponsorship = any(pat.search(combined_text) for pat in POSITIVE_SPONSORSHIP_PATTERNS)
        if req_sponsorship and not has_sponsorship:
            return (
                False,
                "MISSING_VISA_SPONSORSHIP: Job posting does not affirmatively confirm employer visa sponsorship for candidates from India.",
            )

        # 3. Positive Verification: Relocation Assistance
        has_relocation = any(pat.search(combined_text) for pat in POSITIVE_RELOCATION_PATTERNS)
        if req_relocation and not has_relocation:
            return (
                False,
                "MISSING_RELOCATION: Job posting does not affirmatively confirm relocation assistance package.",
            )

        return True, "PASSED: Verified affirmative visa sponsorship and relocation assistance offered."
