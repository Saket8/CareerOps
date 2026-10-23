"""Screening Knowledge Base for Autonomous Form Field & Screening Resolution.

Persists learned answers, location synonyms, and skill mappings across runs,
allowing both Naukri and LinkedIn adapters to continuously self-heal.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from src.utils.logger import get_logger

logger = get_logger("screening_knowledge")

DATA_DIR = Path("data")
LEARNED_SCREENING_FILE = DATA_DIR / "learned_screening_answers.json"
LEARNED_LOCATION_SYNONYMS_FILE = DATA_DIR / "learned_location_synonyms.json"

DEFAULT_SKILL_YEARS: Dict[str, int] = {
    "oci": 7,
    "oracle cloud": 7,
    "oracle cloud infrastructure": 7,
    "aws": 6,
    "amazon web services": 6,
    "azure": 6,
    "microsoft azure": 6,
    "gcp": 3,
    "google cloud": 3,
    "google cloud platform": 3,
    "cloud": 7,
    "cloud architecture": 12,
    "kubernetes": 5,
    "k8s": 5,
    "oke": 5,
    "docker": 5,
    "container": 5,
    "helm": 5,
    "terraform": 6,
    "iac": 6,
    "ansible": 5,
    "devops": 6,
    "ci/cd": 6,
    "linux": 12,
    "unix": 12,
    "rhel": 12,
    "bash": 12,
    "shell": 12,
    "python": 5,
    "database": 12,
    "sql": 12,
    "oracle db": 12,
    "exadata": 12,
    "rac": 12,
    "genai": 5,
    "generative ai": 5,
    "llm": 5,
    "rag": 5,
    "agentic": 5,
    "agentic ai": 5,
    "ai": 5,
    "security": 6,
    "iam": 6,
    "networking": 8,
    "total": 12,
    "overall": 12,
}

DEFAULT_PATTERNS: List[Dict[str, str]] = [
    {"pattern": r"notice\s+period", "answer": "90 Days"},
    {"pattern": r"serving\s+notice", "answer": "No"},
    {"pattern": r"last\s+working\s+day", "answer": "Not Serving"},
    {"pattern": r"comfortable\s+working\s+in\s+hybrid", "answer": "Yes"},
    {"pattern": r"willing\s+to\s+relocate", "answer": "Yes"},
    {"pattern": r"work\s+authorization", "answer": "Yes"},
    {"pattern": r"authorized\s+to\s+work", "answer": "Yes"},
    {"pattern": r"require.*sponsorship", "answer": "No"},
    {"pattern": r"visa\s+sponsorship", "answer": "No"},
    {"pattern": r"gross\s+(?:per\s+)?month", "answer": "7500"},
    {"pattern": r"salary\s+expectations?", "answer": "7500"},
    {"pattern": r"annual\s+salary", "answer": "95000"},
    {"pattern": r"hourly\s+rate", "answer": "80"},
    {"pattern": r"background\s+check", "answer": "Yes"},
    {"pattern": r"drug\s+test", "answer": "Yes"},
    {"pattern": r"night\s+shift", "answer": "Yes"},
    {"pattern": r"rotational\s+shift", "answer": "Yes"},
    {"pattern": r"us\s+shift", "answer": "Yes"},
    {"pattern": r"pf\s+(?:account|fund)", "answer": "Yes"},
]


class ScreeningKnowledgeBase:
    """Manages the autonomous knowledge base of screening answers, skill mappings, and location synonyms."""

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.skill_years: Dict[str, int] = dict(DEFAULT_SKILL_YEARS)
        self.exact_answers: Dict[str, str] = {}
        self.patterns: List[Dict[str, str]] = list(DEFAULT_PATTERNS)
        self.location_synonyms: Dict[str, List[str]] = {}
        self.load()

    def load(self) -> None:
        """Loads learned questions, answers, patterns, and synonyms from disk."""
        if LEARNED_SCREENING_FILE.exists():
            try:
                with open(LEARNED_SCREENING_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.exact_answers.update(data.get("exact_answers", {}))
                    self.skill_years.update(data.get("skill_years", {}))
                    custom_patterns = data.get("patterns", [])
                    for cp in custom_patterns:
                        if cp not in self.patterns:
                            self.patterns.append(cp)
                logger.debug(f"Loaded {len(self.exact_answers)} exact answers from {LEARNED_SCREENING_FILE}")
            except Exception as e:
                logger.warning(f"Failed to load {LEARNED_SCREENING_FILE}: {e}")

        if LEARNED_LOCATION_SYNONYMS_FILE.exists():
            try:
                with open(LEARNED_LOCATION_SYNONYMS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.location_synonyms.update(data.get("mappings", {}))
                logger.debug(f"Loaded {len(self.location_synonyms)} location synonym sets from {LEARNED_LOCATION_SYNONYMS_FILE}")
            except Exception as e:
                logger.warning(f"Failed to load {LEARNED_LOCATION_SYNONYMS_FILE}: {e}")

    def save(self) -> None:
        """Persists current screening knowledge base and location synonyms to disk."""
        try:
            payload = {
                "exact_answers": self.exact_answers,
                "skill_years": self.skill_years,
                "patterns": self.patterns,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(LEARNED_SCREENING_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.debug(f"Persisted screening knowledge base to {LEARNED_SCREENING_FILE}")
        except Exception as e:
            logger.error(f"Failed to save {LEARNED_SCREENING_FILE}: {e}")

        try:
            loc_payload = {
                "mappings": self.location_synonyms,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(LEARNED_LOCATION_SYNONYMS_FILE, "w", encoding="utf-8") as f:
                json.dump(loc_payload, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save {LEARNED_LOCATION_SYNONYMS_FILE}: {e}")

    def get_answer(self, question_text: str, field_type: str = "text") -> Optional[str]:
        """Resolves a question using exact match, skill mapping, or regex patterns."""
        q_clean = (question_text or "").strip().lower()
        if not q_clean:
            return None

        # 1. Exact or normalized string match
        if q_clean in self.exact_answers:
            return self.exact_answers[q_clean]

        for k, v in self.exact_answers.items():
            if k in q_clean or q_clean in k:
                return v

        # 2. Skill Years Match
        is_numeric = field_type in ("number", "numeric") or any(
            w in q_clean for w in ["how many years", "years of experience", "total years", "years do you have"]
        )
        if is_numeric:
            for skill, yrs in sorted(self.skill_years.items(), key=lambda x: len(x[0]), reverse=True):
                # Word boundary check for skill
                if re.search(r"\b" + re.escape(skill) + r"\b", q_clean):
                    return str(yrs)

        # 3. Regex Pattern Matches
        for item in self.patterns:
            pat = item.get("pattern", "")
            ans = item.get("answer", "")
            if pat and ans and re.search(pat, q_clean, re.IGNORECASE):
                return ans

        return None

    def learn_answer(self, question_text: str, answer: str, save_immediate: bool = True) -> None:
        """Records a verified or inferred answer for a screening question."""
        q_clean = (question_text or "").strip().lower()
        ans_clean = str(answer).strip()
        if not q_clean or not ans_clean:
            return

        self.exact_answers[q_clean] = ans_clean
        logger.info(f"Learned screening answer: '{q_clean}' -> '{ans_clean}'")
        if save_immediate:
            self.save()

    def learn_pattern(self, pattern: str, answer: str, save_immediate: bool = True) -> None:
        """Records a new regex pattern mapping."""
        pat_clean = pattern.strip()
        ans_clean = str(answer).strip()
        if not pat_clean or not ans_clean:
            return

        for p in self.patterns:
            if p.get("pattern") == pat_clean:
                p["answer"] = ans_clean
                if save_immediate:
                    self.save()
                return

        self.patterns.append({"pattern": pat_clean, "answer": ans_clean})
        logger.info(f"Learned screening pattern: '{pat_clean}' -> '{ans_clean}'")
        if save_immediate:
            self.save()

    def learn_location_synonym(self, canonical_city: str, synonym: str, save_immediate: bool = True) -> None:
        """Registers a location synonym under a canonical city key."""
        can_clean = canonical_city.strip().lower()
        syn_clean = synonym.strip().lower()
        if not can_clean or not syn_clean:
            return

        syn_list = self.location_synonyms.setdefault(can_clean, [])
        if syn_clean not in syn_list:
            syn_list.append(syn_clean)
            logger.info(f"Learned location synonym for '{can_clean}': '{syn_clean}'")
            if save_immediate:
                self.save()

    def get_compatible_location_terms(self, canonical_city: str = "noida") -> List[str]:
        """Returns all compatible terms for a location including learned synonyms."""
        base = ["delhi / ncr", "delhi ncr", "noida", "greater noida", "gurugram", "gurgaon", "faridabad", "ghaziabad"]
        can_clean = canonical_city.strip().lower()
        learned = self.location_synonyms.get(can_clean, [])
        combined = list(set(base + learned))
        return combined


# Global singleton instance
_GLOBAL_KNOWLEDGE_BASE: Optional[ScreeningKnowledgeBase] = None


def get_screening_knowledge_base() -> ScreeningKnowledgeBase:
    """Returns the process-wide ScreeningKnowledgeBase instance."""
    global _GLOBAL_KNOWLEDGE_BASE
    if _GLOBAL_KNOWLEDGE_BASE is None:
        _GLOBAL_KNOWLEDGE_BASE = ScreeningKnowledgeBase()
    return _GLOBAL_KNOWLEDGE_BASE
