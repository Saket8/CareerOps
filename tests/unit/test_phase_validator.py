"""Unit tests for Phase Gate Validator auditing Section 24 compliance."""

import pytest
from src.cli.phase_validator import validate_application_phase
from src.database.connection import init_db, get_db_session
from src.database.models import JobModel, ApplicationModel
from src.models.job import JobStatus


def test_phase_validator_execution(tmp_path):
    db_file = tmp_path / "test_phase.sqlite"
    db_url = f"sqlite:///{db_file}"
    init_db(db_url)

    # 1. Empty database must fail audit
    assert validate_application_phase(db_url) is False

    # 2. Seed a verified confirmed application with physical evidence on disk
    ev_file = tmp_path / "test_phase_evidence.png"
    ev_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # Valid non-empty PNG header

    with get_db_session(db_url) as session:
        job = JobModel(
            job_id="test_phase_job_1",
            title="Principal OCI Architect",
            company="Maveric",
            location="Pan India",
            url="https://www.naukri.com/job-listings-oci-architect",
            status=JobStatus.APPLIED_CONFIRMED.value,
        )
        session.add(job)
        session.flush()

        app = ApplicationModel(
            application_id="test_phase_app_1",
            job_id="test_phase_job_1",
            status=JobStatus.APPLIED_CONFIRMED.value,
            canonical_job_url="https://www.naukri.com/job-listings-oci-architect",
            application_method="NAUKRI_DIRECT",
            confirmation_reference="DIRECT_APPLY_VERIFIED",
            verification_method="LEVEL_3_BUTTON_ALREADY_APPLIED",
            evidence_path=str(ev_file),
        )
        session.add(app)
        session.commit()

    # 3. Validated state with physical proof must pass audit
    passed = validate_application_phase(db_url)
    assert passed is True

    # 4. Corrupt / 0-byte evidence must fail audit
    ev_file.write_bytes(b"")
    passed_corrupt = validate_application_phase(db_url)
    assert passed_corrupt is False


def test_phase_validator_passes_with_confirmed_and_non_fatal_failed_jobs(tmp_path):
    db_file = tmp_path / "test_phase_failures.sqlite"
    db_url = f"sqlite:///{db_file}"
    init_db(db_url)

    ev_file = tmp_path / "test_phase_evidence_2.png"
    ev_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    with get_db_session(db_url) as session:
        # Confirmed job 1
        job1 = JobModel(
            job_id="test_phase_job_ok",
            title="AI Automation Leader",
            company="Capgemini",
            location="Hyderabad",
            url="https://www.naukri.com/job-listings-ai-leader",
            status=JobStatus.APPLIED_CONFIRMED.value,
        )
        # Failed job 2
        job2 = JobModel(
            job_id="test_phase_job_fail",
            title="GenAI Architect",
            company="Nagarro",
            location="Bengaluru",
            url="https://www.naukri.com/job-listings-genai-architect",
            status=JobStatus.APPLICATION_FAILED.value,
        )
        session.add_all([job1, job2])
        session.flush()

        app1 = ApplicationModel(
            application_id="app_ok_1",
            job_id="test_phase_job_ok",
            status=JobStatus.APPLIED_CONFIRMED.value,
            canonical_job_url="https://www.naukri.com/job-listings-ai-leader",
            application_method="NAUKRI_DIRECT",
            confirmation_reference="ALREADY_APPLIED",
            verification_method="LEVEL_3_BUTTON_ALREADY_APPLIED",
            evidence_path=str(ev_file),
        )
        app2 = ApplicationModel(
            application_id="app_fail_1",
            job_id="test_phase_job_fail",
            status=JobStatus.APPLICATION_FAILED.value,
            canonical_job_url="https://www.naukri.com/job-listings-genai-architect",
            application_method="NAUKRI_DIRECT",
            failure_reason="Timeout 30000ms exceeded on click",
        )
        session.add_all([app1, app2])
        session.commit()

    # Must pass because confirmed application with physical proof exists, and per-job failure is non-fatal warning
    passed = validate_application_phase(db_url)
    assert passed is True

