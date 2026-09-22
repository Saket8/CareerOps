"""Candidate profile extractor and truth validator.

Extracts candidate details from the master DOCX resume and validates
against the immutable candidate_facts.yaml truth layer.
"""

import os
from pathlib import Path
from typing import Optional
import yaml
import docx

from src.models.candidate import CandidateTruth


FACTS_PATH = Path(__file__).resolve().parent / "candidate_facts.yaml"
MASTER_RESUME_PATH = Path(__file__).resolve().parent.parent / "resumes" / "master" / "Saket_Saurav_OCI.docx"

_CACHED_TRUTH: Optional[CandidateTruth] = None


def extract_text_from_docx(file_path: Path) -> str:
    """Extract full plaintext from a DOCX resume."""
    if not file_path.exists():
        raise FileNotFoundError(f"Master resume not found at {file_path}")
    doc = docx.Document(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    table_text = []
    for table in doc.tables:
        for row in table.rows:
            row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
            if row_vals:
                table_text.append(" | ".join(row_vals))
    return "\n".join(paragraphs + table_text)


def load_candidate_facts(facts_path: Path = FACTS_PATH) -> CandidateTruth:
    """Load and validate candidate truth facts against Pydantic schema."""
    if not facts_path.exists():
        raise FileNotFoundError(f"Candidate facts file not found at {facts_path}")
    
    with open(facts_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    return CandidateTruth(**data)


def get_candidate_truth(refresh: bool = False) -> CandidateTruth:
    """Singleton getter for candidate truth layer."""
    global _CACHED_TRUTH
    if _CACHED_TRUTH is None or refresh:
        _CACHED_TRUTH = load_candidate_facts()
    return _CACHED_TRUTH


def verify_facts_against_resume(facts: CandidateTruth, resume_path: Path = MASTER_RESUME_PATH) -> bool:
    """Strict check ensuring candidate facts do not fabricate claims absent in resume."""
    resume_text = extract_text_from_docx(resume_path).lower()
    
    # Check candidate name and phone/email
    assert facts.candidate.name.lower() in resume_text, "Candidate name missing from resume text"
    assert "7028481800" in resume_text, "Candidate phone missing from resume text"
    
    # Check key companies
    for emp in facts.employment_history:
        assert emp.company.lower() in resume_text, f"Company {emp.company} missing from resume text"
    
    # Check certifications
    for cert in facts.certifications:
        # Check core part of certification name
        cert_core = cert.name.lower().replace("certified ", "").strip()
        assert cert_core in resume_text or cert.name.lower() in resume_text, f"Certification {cert.name} missing from resume"
        
    return True


if __name__ == "__main__":
    facts = get_candidate_truth()
    print(f"Loaded facts for: {facts.candidate.name} - {facts.candidate.title}")
    print(f"Certifications: {len(facts.certifications)}")
    print(f"Companies: {[e.company for e in facts.employment_history]}")
    verified = verify_facts_against_resume(facts)
    print(f"Verified against master resume: {verified}")
