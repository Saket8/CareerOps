"""Compensation Intelligence and Market Salary Estimation Engine.

Estimates realistic market compensation ranges for roles where salary is listed as
'Not Disclosed' or 'Competitive', based on title seniority, technical specialization
(OCI, GenAI, Cloud Architecture), and regional market benchmarks (Levels.fyi, AmbitionBox).
"""

import re
from typing import Dict, Any, Optional
from dataclasses import dataclass

from src.models.job import JobListing


@dataclass
class CompensationEstimate:
    min_amount: float
    max_amount: float
    currency: str
    formatted_band: str
    confidence: str
    source_benchmark: str


class CompensationIntelligence:
    """Provides market salary estimates for undisclosed executive and tech roles."""

    # Regional Base Bands for Principal / Lead Architects
    BENCHMARKS = {
        "india": {
            "currency": "INR",
            "unit": "LPA",
            "cloud_architect": (38.0, 55.0),
            "ai_architect": (45.0, 65.0),
            "principal_architect": (48.0, 72.0),
            "default": (35.0, 50.0),
        },
        "europe": {
            "currency": "EUR",
            "unit": "k/year",
            "cloud_architect": (95.0, 125.0),
            "ai_architect": (105.0, 145.0),
            "principal_architect": (115.0, 155.0),
            "default": (90.0, 120.0),
        },
        "nordics": {
            "currency": "EUR",
            "unit": "k/year",
            "cloud_architect": (95.0, 130.0),
            "ai_architect": (110.0, 150.0),
            "principal_architect": (120.0, 160.0),
            "default": (95.0, 125.0),
        },
        "australia": {
            "currency": "AUD",
            "unit": "k/year",
            "cloud_architect": (160.0, 210.0),
            "ai_architect": (180.0, 240.0),
            "principal_architect": (195.0, 260.0),
            "default": (150.0, 200.0),
        },
        "united states": {
            "currency": "USD",
            "unit": "k/year",
            "cloud_architect": (175.0, 235.0),
            "ai_architect": (200.0, 275.0),
            "principal_architect": (210.0, 290.0),
            "default": (165.0, 220.0),
        },
        "united kingdom": {
            "currency": "GBP",
            "unit": "k/year",
            "cloud_architect": (90.0, 125.0),
            "ai_architect": (105.0, 140.0),
            "principal_architect": (115.0, 150.0),
            "default": (85.0, 115.0),
        },
    }

    @classmethod
    def estimate_compensation(cls, job: JobListing) -> Optional[CompensationEstimate]:
        """Calculates realistic market compensation estimation based on role and location."""
        # If salary was already explicitly disclosed and parsed, format it
        if job.salary and job.salary.is_disclosed and job.salary.min_lpa and job.salary.max_lpa:
            return CompensationEstimate(
                min_amount=job.salary.min_lpa,
                max_amount=job.salary.max_lpa,
                currency="INR",
                formatted_band=f"₹{job.salary.min_lpa:.1f} – ₹{job.salary.max_lpa:.1f} LPA (Disclosed)",
                confidence="High (Disclosed by Employer)",
                source_benchmark="Employer Job Posting",
            )

        loc_lower = (job.location or "").lower()
        title_lower = (job.title or "").lower()

        # Identify Region
        target_region = "india"
        if any(r in loc_lower for r in ("nordic", "denmark", "sweden", "norway", "finland")):
            target_region = "nordics"
        elif any(r in loc_lower for r in ("europe", "germany", "netherlands", "ireland", "switzerland")):
            target_region = "europe"
        elif any(r in loc_lower for r in ("australia", "sydney", "melbourne")):
            target_region = "australia"
        elif any(r in loc_lower for r in ("united states", "us", "san francisco", "new york", "austin", "seattle")):
            target_region = "united states"
        elif any(r in loc_lower for r in ("uk", "united kingdom", "london")):
            target_region = "united kingdom"

        bench = cls.BENCHMARKS.get(target_region, cls.BENCHMARKS["india"])

        # Determine Tier by Title
        if any(kw in title_lower for kw in ("principal", "director", "head", "chief", "staff")):
            min_val, max_val = bench["principal_architect"]
            tier_name = "Principal / Leadership"
        elif any(kw in title_lower for kw in ("ai", "genai", "llm", "agentic", "machine learning")):
            min_val, max_val = bench["ai_architect"]
            tier_name = "AI / GenAI Architecture"
        elif any(kw in title_lower for kw in ("cloud", "oci", "solution", "enterprise")):
            min_val, max_val = bench["cloud_architect"]
            tier_name = "Cloud Architecture"
        else:
            min_val, max_val = bench["default"]
            tier_name = "Enterprise Senior Tech"

        curr = bench["currency"]
        unit = bench["unit"]

        if curr == "INR":
            formatted = f"~₹{min_val:.0f} – ₹{max_val:.0f} LPA (Est. Market Benchmark)"
        elif curr == "EUR":
            formatted = f"~€{min_val:.0f}k – €{max_val:.0f}k/yr (Est. Market Benchmark)"
        elif curr == "GBP":
            formatted = f"~£{min_val:.0f}k – £{max_val:.0f}k/yr (Est. Market Benchmark)"
        elif curr == "AUD":
            formatted = f"~A${min_val:.0f}k – A${max_val:.0f}k/yr (Est. Market Benchmark)"
        else:
            formatted = f"~${min_val:.0f}k – ${max_val:.0f}k/yr (Est. Market Benchmark)"

        return CompensationEstimate(
            min_amount=min_val,
            max_amount=max_val,
            currency=curr,
            formatted_band=formatted,
            confidence="Estimated (Levels.fyi / AmbitionBox Index)",
            source_benchmark=f"{target_region.capitalize()} {tier_name}",
        )
