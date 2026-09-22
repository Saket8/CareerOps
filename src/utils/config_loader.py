"""Configuration loader supporting YAML configs with environment variable overrides."""

import os
from pathlib import Path
from typing import Any, Dict
import yaml

from src.utils.logger import get_logger

logger = get_logger("config_loader")

CONFIG_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "config.yaml"


def load_config(config_path: Path = CONFIG_FILE) -> Dict[str, Any]:
    """Loads configuration and applies environment variable overrides."""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Environment variable overrides (e.g., from GitHub Actions Secrets/Variables)
    if "DRY_RUN" in os.environ:
        config["application"]["dry_run"] = os.environ["DRY_RUN"].strip().lower() in ("true", "1", "yes")

    if "MATCH_THRESHOLD" in os.environ:
        try:
            config["application"]["match_threshold"] = float(os.environ["MATCH_THRESHOLD"])
        except ValueError:
            logger.warning("Invalid MATCH_THRESHOLD in env, using config value")

    if "MIN_SALARY_LPA" in os.environ:
        try:
            config["application"]["min_salary_lpa"] = float(os.environ["MIN_SALARY_LPA"])
        except ValueError:
            logger.warning("Invalid MIN_SALARY_LPA in env, using config value")

    if "MAX_APPLICATIONS_PER_DAY" in os.environ:
        try:
            config["application"]["max_applications_per_day"] = int(os.environ["MAX_APPLICATIONS_PER_DAY"])
        except ValueError:
            logger.warning("Invalid MAX_APPLICATIONS_PER_DAY in env, using config value")

    if "TIMEZONE" in os.environ:
        config["app"]["timezone"] = os.environ["TIMEZONE"]

    if "SEARCH_ENABLED" in os.environ:
        config["search"]["enabled"] = os.environ["SEARCH_ENABLED"].strip().lower() in ("true", "1", "yes")

    if "EMAIL_ENABLED" in os.environ:
        config["email"]["enabled"] = os.environ["EMAIL_ENABLED"].strip().lower() in ("true", "1", "yes")

    if "EMAIL_RECIPIENT" in os.environ:
        config["email"]["default_recipient"] = os.environ["EMAIL_RECIPIENT"].strip()

    if "DATABASE_URL" in os.environ:
        config["database"]["db_url"] = os.environ["DATABASE_URL"].strip()

    return config
