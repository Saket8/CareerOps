"""Unit tests for ResumeAgent, PDF generation, and ATS validation."""

import pytest
import hashlib
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories.resume_repo import ResumeRepository
from src.agents.resume_agent import ResumeAgent, ATSValidator
from candidate.profile_extractor import get_candidate_truth, MASTER_RESUME_PATH
from src.models.job import JobListing, JobSalary, SalaryEligibility
from src.models.score import JobScore


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def test_resume_generation_and_validation(db_session, tmp_path):
    resume_repo = ResumeRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    config = {
        "resume": {
            "output_dir": str(tmp_path / "generated_resumes"),
            "generate_pdf": True,
            "generate_docx": True,
        }
    }
    agent = ResumeAgent(resume_repo, candidate_truth, config)

    job = JobListing(
        job_id="job_oracle_genai_101",
        title="Principal Cloud Solutions Architect",
        company="Oracle",
        location="Bengaluru",
        url="https://naukri.com/job/101",
        jd_text="Focus on OCI, OKE, GenAI platform, Terraform automation, and air-gapped IAM security.",
    )

    score = JobScore(
        job_id="job_oracle_genai_101",
        overall_score=92.0,
        architecture_score=95.0,
        cloud_score=90.0,
        oci_score=95.0,
        ai_score=85.0,
        agentic_ai_score=80.0,
        kubernetes_score=90.0,
        security_score=85.0,
        multicloud_score=80.0,
        experience_alignment=95.0,
        skill_alignment=90.0,
        passed_threshold=True,
    )

    # Record master resume checksum before generation
    master_checksum_before = hashlib.sha256(open(MASTER_RESUME_PATH, "rb").read()).hexdigest()

    docx_path, pdf_path, val_report = agent.generate_tailored_resume(job, score)

    # 1. Assert files exist
    assert docx_path.exists(), "DOCX must be created"
    assert pdf_path.exists(), "PDF must be created"
    assert docx_path.stat().st_size > 1000, "DOCX file must not be empty"
    assert pdf_path.stat().st_size > 500, "PDF file must not be empty"

    # 2. Assert naming convention: Company_Role_YYYYMMDD.docx
    assert "Oracle" in docx_path.name
    assert "Principal" in docx_path.name
    assert docx_path.suffix == ".docx"
    assert pdf_path.suffix == ".pdf"

    # 3. Assert ATS Validation Passes
    assert val_report["passed"] is True
    assert val_report["ats_score"] >= 90.0
    assert val_report["checks"]["text_extractability"] is True
    assert val_report["checks"]["section_recognition"] is True
    assert val_report["checks"]["contact_name"] is True
    assert val_report["checks"]["contact_phone"] is True

    # 4. Assert Version tracked in Database
    version = resume_repo.get_by_job_id("job_oracle_genai_101")
    assert version is not None
    assert version.ats_score >= 90.0
    assert version.file_path_docx == str(docx_path)

    # 5. Assert Master Resume is 100% untouched
    master_checksum_after = hashlib.sha256(open(MASTER_RESUME_PATH, "rb").read()).hexdigest()
    assert master_checksum_before == master_checksum_after, "Master resume MUST remain completely unchanged!"
