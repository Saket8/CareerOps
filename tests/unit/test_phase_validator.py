"""Unit tests for Phase Gate Validator auditing Section 24 compliance."""

import pytest
from src.cli.phase_validator import validate_application_phase
from src.database.connection import init_db


def test_phase_validator_execution():
    # Execute phase validation against current database state
    init_db("sqlite:///naukri_career_agent.sqlite")
    passed = validate_application_phase("sqlite:///naukri_career_agent.sqlite")
    assert passed is True
