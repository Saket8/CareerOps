"""Unit tests for Interview Intelligence Agent and 7-document pack generation."""

import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.database.repositories.interview_repo import InterviewRepository
from src.agents.interview_agent import InterviewAgent
from candidate.profile_extractor import get_candidate_truth
from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility
from src.models.score import JobScore, JobEvidence


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


def test_interview_pack_generation(db_session, tmp_path):
    interview_repo = InterviewRepository(db_session)
    candidate_truth = get_candidate_truth(refresh=True)
    agent = InterviewAgent(interview_repo, candidate_truth, base_dir=tmp_path / "interviews")

    job = JobListing(
        job_id="job_oracle_genai_202",
        title="Principal Cloud Architect",
        company="Oracle Financial",
        location="Bengaluru",
        url="https://naukri.com/job/202",
        salary=JobSalary(min_lpa=35.0, is_disclosed=True, eligibility=SalaryEligibility.ELIGIBLE),
        jd_text="Deep OCI, OKE, GenAI, and air-gapped security architecture.",
    )

    score = JobScore(
        job_id="job_oracle_genai_202",
        overall_score=94.0,
        architecture_score=95.0,
        cloud_score=95.0,
        oci_score=95.0,
        ai_score=90.0,
        agentic_ai_score=85.0,
        kubernetes_score=90.0,
        security_score=90.0,
        multicloud_score=85.0,
        experience_alignment=95.0,
        skill_alignment=92.0,
        passed_threshold=True,
        strengths=["OCI Specialization", "Private OKE Clusters", "GenAI CloudOps Dashboard"],
        gaps=[],
    )

    evidence = JobEvidence(
        job_id="job_oracle_genai_202",
        observed_facts=["Explicit mention of OCI and OKE", "Disclosed salary >= 35 LPA"],
        inferred_signals=["High-affinity architecture leadership role"],
        generated_actions=["Prepare Level 3 trade-off questions"],
    )

    pack_dir = agent.generate_interview_pack(job, score, evidence)

    # 1. Assert pack directory was created
    assert pack_dir.exists()
    assert pack_dir.is_dir()

    # 2. Assert exact 7 files are generated
    expected_files = [
        "JD.md",
        "match-analysis.md",
        "likely-questions.md",
        "model-answers.md",
        "architecture-exercises.md",
        "candidate-gaps.md",
        "7-day-preparation-plan.md",
    ]
    for filename in expected_files:
        file_path = pack_dir / filename
        assert file_path.exists(), f"File {filename} was not generated"
        assert file_path.stat().st_size > 100, f"File {filename} is too small"

    # 3. Verify content of likely-questions.md includes 3 levels
    q_text = (pack_dir / "likely-questions.md").read_text(encoding="utf-8")
    assert "LEVEL 1" in q_text
    assert "LEVEL 2" in q_text
    assert "LEVEL 3" in q_text
    assert "Follow-up" in q_text  # cross-questioning

    # 4. Verify model-answers.md references real candidate experience
    a_text = (pack_dir / "model-answers.md").read_text(encoding="utf-8")
    assert "KPN" in a_text
    assert "Model Context Protocol" in a_text or "MCP" in a_text

    # 5. Verify database persistence
    db_pack = interview_repo.get_by_job_id("job_oracle_genai_202")
    assert db_pack is not None
    assert db_pack.company == "Oracle Financial"
    assert db_pack.question_count > 0
