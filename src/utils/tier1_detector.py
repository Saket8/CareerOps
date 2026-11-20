"""Tier-1 GCC & Cloud Hyperscaler Priority Employer Detector.

Identifies top-tier Global Capability Centers (GCCs: JPMorgan, Goldman Sachs,
Wells Fargo, Walmart Global Tech, Target, Fidelity, Optum, Barclays, etc.)
and Cloud Hyperscalers / Product Tech firms (Oracle, AWS, Microsoft, Google,
Cisco, VMware, Snowflake, Salesforce, etc.) commanding ₹42-75 LPA+ compensation.
"""

import re
from typing import List, Optional, Tuple, Pattern

# Canonical Whitelist of Top GCCs and Hyperscalers / Product Tech Employers
TIER_1_GCC_HYPERSCALERS: List[str] = [
    # Cloud Hyperscalers & Enterprise Infra
    "Oracle",
    "Amazon",
    "AWS",
    "Microsoft",
    "Google",
    "Google Cloud",
    "Cisco",
    "VMware",
    "Broadcom",
    "Snowflake",
    "Salesforce",
    "ServiceNow",
    "Adobe",
    "NVIDIA",
    "Atlassian",
    "Intuit",
    "Uber",
    "Stripe",
    # Tier-1 Banking & Financial GCCs
    "JPMorgan",
    "JP Morgan",
    "Goldman Sachs",
    "Wells Fargo",
    "Morgan Stanley",
    "Barclays",
    "Citi",
    "Citibank",
    "BNY Mellon",
    "State Street",
    "Standard Chartered",
    "Fidelity",
    "Fidelity Investments",
    "American Express",
    "Amex",
    "Mastercard",
    "Visa",
    # Tier-1 Retail & Healthcare Tech GCCs
    "Walmart",
    "Walmart Global Tech",
    "Target",
    "Lowe's",
    "Lowes",
    "Optum",
    "UnitedHealth",
    "PayPal",
]

# Specialized regexes for abbreviations, variations, and punctuation
SPECIAL_PATTERNS = {
    "jpmorgan": r"\b(jpmorgan|jp\s*morgan|j\.p\.\s*morgan)\b",
    "jp morgan": r"\b(jpmorgan|jp\s*morgan|j\.p\.\s*morgan)\b",
    "citi": r"\b(citi|citibank|citigroup)\b",
    "citibank": r"\b(citi|citibank|citigroup)\b",
    "lowes": r"\b(lowe'?s)\b",
    "lowe's": r"\b(lowe'?s)\b",
    "unitedhealth": r"\b(unitedhealth|united\s*health)\b",
    "optum": r"\boptum\b",
    "bny mellon": r"\b(bny\s*mellon|new\s*york\s*mellon)\b",
    "servicenow": r"\b(service\s*now|servicenow)\b",
    "amex": r"\b(american\s*express|amex)\b",
    "american express": r"\b(american\s*express|amex)\b",
    "google": r"\b(google|google\s*cloud)\b",
    "google cloud": r"\b(google|google\s*cloud)\b",
    "amazon": r"\b(amazon|aws)\b",
    "aws": r"\b(amazon|aws)\b",
}


def _compile_patterns(companies: List[str]) -> List[Tuple[str, Pattern]]:
    compiled = []
    seen = set()
    for name in companies:
        n_low = name.lower().strip()
        if n_low in seen:
            continue
        seen.add(n_low)
        if n_low in SPECIAL_PATTERNS:
            pat = SPECIAL_PATTERNS[n_low]
            compiled.append((name, re.compile(pat, re.IGNORECASE)))
        else:
            words = [re.escape(w) for w in n_low.split()]
            pat = r"\b" + r"\s+".join(words) + r"\b"
            compiled.append((name, re.compile(pat, re.IGNORECASE)))
    return compiled


def _load_all_top_entities() -> List[str]:
    names = list(TIER_1_GCC_HYPERSCALERS)
    from pathlib import Path
    import yaml
    yaml_path = Path("data/gcc_hyperscalers_top100.yaml")
    if yaml_path.exists():
        try:
            with open(yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for ent in data.get("entities", []):
                ent_name = ent.get("name")
                if ent_name and ent_name not in names:
                    names.append(ent_name)
        except Exception:
            pass
    return names


# Precompiled default pattern list containing all Top 100 GCCs & Hyperscalers
_DEFAULT_COMPILED = _compile_patterns(_load_all_top_entities())


def is_tier_1_company(company: Optional[str], custom_list: Optional[List[str]] = None) -> bool:
    """Checks whether the given company name matches a Tier-1 GCC or Hyperscaler."""
    if not company or not company.strip():
        return False
    patterns = _compile_patterns(custom_list) if custom_list else _DEFAULT_COMPILED
    c_str = company.strip()
    for _, pat in patterns:
        if pat.search(c_str):
            return True
    return False


def get_tier_1_matched_name(company: Optional[str], custom_list: Optional[List[str]] = None) -> Optional[str]:
    """Returns the canonical matched Tier-1 company name if matched, else None."""
    if not company or not company.strip():
        return None
    patterns = _compile_patterns(custom_list) if custom_list else _DEFAULT_COMPILED
    c_str = company.strip()
    for canonical_name, pat in patterns:
        if pat.search(c_str):
            return canonical_name
    return None
