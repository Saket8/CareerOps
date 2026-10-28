"""Unit tests for configuration loading and environment variable overrides."""

import os
from src.utils.config_loader import load_config


def test_load_default_config():
    config = load_config()
    assert config["application"]["match_threshold"] == 70.0
    assert config["application"]["max_applications_per_day"] == 35
    assert config["application"]["min_salary_lpa"] == 30.0
    assert isinstance(config["application"]["dry_run"], bool)
    assert config["linkedin"]["max_applications_per_day"] == 15
    assert config["linkedin"]["require_visa_sponsorship"] is False
    assert config["linkedin"]["require_relocation"] is False
    assert config["resume"]["reupload_daily"] is True
    assert config["resume"]["reupload_weekends"] is True
    assert config["schedule"]["cron_expression"] == "23 3 * * *"
    assert "queries" in config["search"]
    assert "oracle_cloud" in config["search"]["queries"]
    assert len(config["search"]["queries"]["oracle_cloud"]) > 0


def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("MATCH_THRESHOLD", "80")
    monkeypatch.setenv("MIN_SALARY_LPA", "35")
    
    config = load_config()
    assert config["application"]["dry_run"] is False
    assert config["application"]["match_threshold"] == 80.0
    assert config["application"]["min_salary_lpa"] == 35.0


def test_weekend_schedule_gate_logic():
    """Verify that on weekend days (Saturday/Sunday), reupload_weekends triggers resume refresh only."""
    config = load_config()
    reupload_weekends = config.get("resume", {}).get("reupload_weekends", False)
    allowed_days = [d.lower().strip() for d in config.get("schedule", {}).get("days", [])]

    # Saturday and Sunday should NOT be in weekday operations allowed_days
    assert "saturday" not in allowed_days
    assert "sunday" not in allowed_days

    # But reupload_weekends should be enabled
    assert reupload_weekends is True
