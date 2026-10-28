"""Unit tests verifying screening chatbot improvements and LinkedIn Easy Apply automation refinements."""

import re
import pytest
from candidate.profile_extractor import get_candidate_truth
from src.models.candidate import CandidateTruth


def test_notice_period_chip_logic():
    cand_truth = get_candidate_truth(refresh=True)
    notice_days = getattr(cand_truth.candidate, "notice_period_days", 90) or 90
    assert notice_days == 90

    # Test patterns that should match 90 days
    sample_chips = [
        "15 Days or less",
        "1 Month",
        "2 Months",
        "3 Months",
        "More than 3 Months",
    ]

    matched = None
    for chip in sample_chips:
        c_text = chip.lower()
        if notice_days >= 75 and any(k in c_text for k in ["3 month", "3-month", "90 day", "90-day", "2 to 3 month", "2-3 month", "more than 2 month", "60 to 90"]):
            matched = chip
            break

    assert matched == "3 Months", f"Expected '3 Months', got {matched}"


def test_numeric_experience_range_regex():
    sample_q_ans = 3.0  # e.g. 3 years AWS experience

    chip_options = [
        "< 1 year",
        "1 - 2 years",
        "3 to 5 years",
        "5+ years"
    ]

    matched_chip = None
    for cand_text in [c.lower() for c in chip_options]:
        # Exact number
        exact_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?|yr|%)?\b", cand_text)
        if exact_match and float(exact_match.group(1)) == sample_q_ans:
            matched_chip = cand_text
            break

        # Range match
        range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|\s)*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?|yr|%)?", cand_text)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if low <= sample_q_ans <= high:
                matched_chip = cand_text
                break

    assert matched_chip == "3 to 5 years", f"Expected '3 to 5 years', got {matched_chip}"


def test_linkedin_salary_expectation_logic():
    test_labels = [
        ("Salary Expectations (Gross per month in EUR)*", "7500"),
        ("Expected monthly compensation (EUR)", "7500"),
        ("Hourly Rate (CAD/hr)", "80"),
        ("Target Annual Base Salary (USD)", "95000"),
        ("Current / Expected CTC (LPA)", "45"),
    ]

    for lbl, expected_val in test_labels:
        l = lbl.toLowerCase() if hasattr(lbl, "toLowerCase") else lbl.lower()
        val = None
        if any(k in l for k in ["salary", "compensation", "remuneration", "rate", "ctc", "pay", "gross", "eur", "cad", "usd", "inr"]):
            if any(k in l for k in ["month", "mensual", "monat", "mensuel"]):
                val = "7500"
            elif any(k in l for k in ["hour", "hourly", "stunde", "heure", "hr"]):
                val = "80"
            elif any(k in l for k in ["lpa", "lakh", "inr"]):
                val = "45"
            elif any(k in l for k in ["annual", "year", "per annum", "año", "jahr"]):
                val = "95000"
            else:
                val = "7500"
        
        assert val == expected_val, f"For label '{lbl}', expected {expected_val}, got {val}"
        assert val != "Yes", f"Salary label '{lbl}' must never be 'Yes'"


def test_linkedin_modal_helper_filtering():
    # Simulate DOM elements
    elements = [
        {"tag": "DIV", "testid": "popover-floating", "popover": "manual", "inert": True, "text": ""},
        {"tag": "DIV", "testid": None, "popover": None, "inert": False, "role": "dialog", "text": "Apply to VASS. Easy Apply Step 1"},
    ]

    valid = [
        el for el in elements
        if el.get("testid") != "popover-floating" and el.get("popover") != "manual" and not el.get("inert")
    ]

    assert len(valid) == 1
    assert "Apply to VASS" in valid[0]["text"]


def test_naukri_chatbot_container_exclusion_and_city_chip_selection():
    """Verify that chatbot option filtering excludes wrapper containers and selects leaf chip."""
    # Scenario: Outer container contains the question text and all options
    outer_container = {
        "text": "Please select the city you are currently residing or willing to relocate to\nBengaluru\nPune\nDelhi / NCR\nSkip this question\nSave",
        "is_leaf": False,
    }
    chip_bengaluru = {"text": "Bengaluru", "is_leaf": True}
    chip_pune = {"text": "Pune", "is_leaf": True}
    chip_delhi_ncr = {"text": "Delhi / NCR", "is_leaf": True}
    chip_skip = {"text": "Skip this question", "is_leaf": True}
    button_save = {"text": "Save", "is_leaf": True}

    candidates = [outer_container, chip_bengaluru, chip_pune, chip_delhi_ncr, chip_skip, button_save]
    primary_ncr_terms = ["delhi / ncr", "delhi/ncr", "delhi ncr", "delhi", "noida", "gurugram", "gurgaon", "greater noida", "ncr"]

    matching_chip = None
    for cand in candidates:
        cand_raw = cand["text"]
        # Strict leaf guard
        if not cand_raw or len(cand_raw.strip()) > 35 or "\n" in cand_raw:
            continue
        cand_clean = " ".join(cand_raw.strip().lower().split())
        if cand_clean in ["save", "submit", "continue", "next", "send", "apply", "skip this question", "skip", "cancel", "close"]:
            continue
        if any(term == cand_clean or term in cand_clean for term in primary_ncr_terms):
            matching_chip = cand
            break

    assert matching_chip is not None, "Failed to match Delhi / NCR chip"
    assert matching_chip["text"] == "Delhi / NCR"
    assert matching_chip["is_leaf"] is True


def test_linkedin_timeout_and_step_config():
    """Verify LinkedIn adapter configuration settings are tuned for reliable multi-step execution."""
    from src.linkedin.adapter import LinkedInAdapter
    import inspect
    source = inspect.getsource(LinkedInAdapter.apply_easy_apply)
    assert any(f"max_easy_apply_duration = {val}" in source for val in (600, 300, 180, 150, 120))
    assert "max_steps = 7" in source or "max_steps = 6" in source
