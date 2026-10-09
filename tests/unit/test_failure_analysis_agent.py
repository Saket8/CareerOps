"""Unit tests for FailureAnalysisAgent, FailureAnalysisRepository, and Immediate Improvements."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, JobModel, ApplicationModel, ApplicationFailureAnalysisModel
from src.database.repositories.failure_analysis_repo import FailureAnalysisRepository
from src.agents.failure_analysis_agent import FailureAnalysisAgent, FailureDiagnostic
from src.agents.discovery import DiscoveryAgent
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.models.job import JobStatus
from candidate.profile_extractor import get_candidate_truth


@pytest.fixture
def db_session():
    """In-memory SQLite database session for unit testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_discovery_agent_program_gate():
    """Verifies that gender-specific and returnship programs are blocked in discovery."""
    assert DiscoveryAgent.is_restricted_program("Infosys Evolve | AI Architect | Women Returnship Program") is True
    assert DiscoveryAgent.is_restricted_program("Return to Work for Women - Cloud Architect") is True
    assert DiscoveryAgent.is_restricted_program("Her Second Innings - Solution Architect") is True
    assert DiscoveryAgent.is_restricted_program("Principal Cloud Architect - OCI") is False
    assert DiscoveryAgent.is_restricted_program("Lead AI Engineer") is False


def test_candidate_answer_resolver_location_options():
    """Verifies NCR location normalization and compatible options matching."""
    truth = get_candidate_truth(refresh=False)
    resolver = CandidateAnswerResolver(truth)

    options = ["Gurugram, Haryana", "Pune, Maharashtra", "Delhi / NCR", "Skip this question"]
    matches = resolver.get_compatible_location_options(options)

    assert "Delhi / NCR" in matches
    assert "Gurugram, Haryana" in matches
    assert "Skip this question" not in matches


def test_failure_analysis_diagnose_diversity(db_session):
    """Verifies diagnosis and self-healing for women returnship program."""
    truth = get_candidate_truth(refresh=False)
    agent = FailureAnalysisAgent(db_session, truth)

    job = JobModel(
        job_id="test_returnship_01",
        title="Infosys Evolve | GenAI Architect | Women Returnship Program",
        company="Infosys",
        location="Bengaluru",
        url="https://test.naukri.com/job/returnship",
        status="APPLICATION_FAILED",
    )
    db_session.add(job)
    app = ApplicationModel(
        application_id="app_ret_01",
        job_id="test_returnship_01",
        status="APPLICATION_FAILED",
        failure_reason="Submission could not be confirmed on reload.",
        questions_answered={"Are you a woman professional looking to restart career?": "No"},
    )
    db_session.add(app)
    db_session.commit()

    diag = agent.diagnose_job(job=job, app=app)
    assert diag.root_cause_category == "DIVERSITY_PROGRAM_RESTRICTION"
    assert diag.self_healing_action == "DISQUALIFIED_DIVERSITY_PROGRAM"
    assert diag.healing_status == "DISQUALIFIED_PERMANENT"
    assert diag.retry_eligible is False

    agent.self_heal(diag)

    # Verify database persistence
    saved = db_session.query(ApplicationFailureAnalysisModel).filter_by(job_id="test_returnship_01").first()
    assert saved is not None
    assert saved.root_cause_category == "DIVERSITY_PROGRAM_RESTRICTION"
    assert saved.healing_status == "DISQUALIFIED_PERMANENT"


def test_failure_analysis_diagnose_location_mismatch(db_session):
    """Verifies diagnosis and self-healing for location checkbox mismatch."""
    truth = get_candidate_truth(refresh=False)
    agent = FailureAnalysisAgent(db_session, truth)

    job = JobModel(
        job_id="test_iris_01",
        title="SDLC + Architect",
        company="Iris Software",
        location="Gurugram, Pune, Delhi / NCR",
        url="https://test.naukri.com/job/iris",
        status="NEEDS_MANUAL_INTERVENTION",
    )
    db_session.add(job)
    app = ApplicationModel(
        application_id="app_iris_01",
        job_id="test_iris_01",
        status="NEEDS_MANUAL_INTERVENTION",
        failure_reason="Recruiter screening could not be answered because no matching option or input was available.",
        questions_detected=[{"turn": 3, "question": "Please select the city you are currently residing or willing to relocate to"}],
        questions_answered={"SDLC experience": "12", "Architectural Design": "0"},
    )
    db_session.add(app)
    db_session.commit()

    diag = agent.diagnose_job(job=job, app=app)
    assert diag.root_cause_category == "LOCATION_SYNONYM_MISMATCH"
    assert diag.self_healing_action == "LOCATION_SYNONYM_LEARNED"
    assert diag.healing_status == "HEALED"
    assert diag.retry_eligible is True

    agent.self_heal(diag)

    # Verify state updated in job table
    updated_job = db_session.query(JobModel).filter_by(job_id="test_iris_01").first()
    assert updated_job.status == JobStatus.READY_FOR_RETRY.value

    # Verify recorded in failure analysis table
    analysis = db_session.query(ApplicationFailureAnalysisModel).filter_by(job_id="test_iris_01").first()
    assert analysis is not None
    assert analysis.healing_status == "HEALED"
    assert analysis.retry_eligible is True


def test_failure_analysis_diagnose_experience_threshold(db_session):
    """Verifies diagnosis and permanent close for truth-layer experience disqualification."""
    truth = get_candidate_truth(refresh=False)
    agent = FailureAnalysisAgent(db_session, truth)

    job = JobModel(
        job_id="test_connect_01",
        title="GenAI Architect | Generative AI | LLM",
        company="Connect iO",
        location="Noida",
        url="https://test.naukri.com/job/connectio",
        status="APPLICATION_FAILED",
    )
    db_session.add(job)
    app = ApplicationModel(
        application_id="app_conn_01",
        job_id="test_connect_01",
        status="APPLICATION_FAILED",
        failure_reason="Submission could not be confirmed on reload.",
        questions_answered={
            "How many years of hands-on experience do you have in GenAI/LLM?": "2",
            "Do you have hands-on experience designing RAG?": "Yes",
        },
    )
    db_session.add(app)
    db_session.commit()

    diag = agent.diagnose_job(job=job, app=app)
    assert diag.root_cause_category == "EXPERIENCE_THRESHOLD_RESTRICTION"
    assert diag.self_healing_action == "DISQUALIFIED_EXPERIENCE_THRESHOLD"
    assert diag.healing_status == "DISQUALIFIED_PERMANENT"
    assert diag.retry_eligible is False

    agent.self_heal(diag)

    # Verify status in job table
    updated_job = db_session.query(JobModel).filter_by(job_id="test_connect_01").first()
    assert updated_job.status == JobStatus.DISQUALIFIED_SCREENING.value
