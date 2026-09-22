"""Unit tests for configuration loading and environment variable overrides."""

import os
from src.utils.config_loader import load_config


def test_load_default_config():
    config = load_config()
    assert config["application"]["match_threshold"] == 75.0
    assert config["application"]["min_salary_lpa"] == 20.0
    assert isinstance(config["application"]["dry_run"], bool)
    assert "queries" in config["search"]
    assert len(config["search"]["queries"]["primary"]) > 0


def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("MATCH_THRESHOLD", "80")
    monkeypatch.setenv("MIN_SALARY_LPA", "25")
    
    config = load_config()
    assert config["application"]["dry_run"] is False
    assert config["application"]["match_threshold"] == 80.0
    assert config["application"]["min_salary_lpa"] == 25.0
