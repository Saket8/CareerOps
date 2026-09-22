"""Autonomous Naukri Career Agent Entrypoint.

Usage:
    python main.py [--dry-run | --live] [--weekly] [--offline] [--query-limit N]
"""

import argparse
import sys
from pathlib import Path

from src.utils.config_loader import load_config
from src.agents.orchestrator import Orchestrator
from src.utils.logger import get_logger

logger = get_logger("main")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Naukri Career & Career-Intelligence Agent")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Run in dry-run mode (Debug only)")
    parser.add_argument("--live", action="store_true", default=True, help="Enable live application submissions (Default: Always Live)")
    parser.add_argument("--weekly", action="store_true", help="Force weekly career intelligence generation")
    parser.add_argument("--offline", action="store_true", help="Run with offline verified test dataset")
    parser.add_argument("--query-limit", type=int, default=15, help="Max jobs to evaluate per search query")
    parser.add_argument("--validate-phase", action="store_true", help="Run Section 24 Phase Gate Audit on application records")

    args = parser.parse_args()

    if args.validate_phase:
        from src.cli.phase_validator import validate_application_phase
        success = validate_application_phase()
        sys.exit(0 if success else 1)

    config = load_config()

    # LIVE mode is permanently enforced by default
    if args.dry_run:
        config["application"]["dry_run"] = True
    else:
        config["application"]["dry_run"] = False

    is_dry = config["application"]["dry_run"]
    logger.info(f"Initiating Autonomous Career Agent (LIVE={not is_dry}, OFFLINE={args.offline})...")

    orchestrator = Orchestrator(config=config, offline_mode=args.offline)
    daily_report = orchestrator.run_daily_pipeline(force_weekly=args.weekly, query_limit=args.query_limit)

    print("\n" + "=" * 60)
    print(f"  RUN COMPLETE: {daily_report.date} (Run ID: {daily_report.run_id})")
    print("=" * 60)
    print(f"  Jobs Scanned:             {daily_report.jobs_scanned}")
    print(f"  Salary Rejects (<20 LPA): {daily_report.salary_rejected}")
    print(f"  Qualified Opportunities:  {daily_report.qualified_jobs}")
    print(f"  Resumes Tailored:         {daily_report.resumes_generated}")
    print(f"  Applications Submitted:   {daily_report.applications_submitted} ({'DRY RUN' if is_dry else 'LIVE'})")
    print(f"  Interview Packs Built:    {daily_report.interview_packs_generated}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
