"""Autonomous Naukri Career Agent Entrypoint.

Usage:
    python main.py [--dry-run | --live] [--weekly] [--offline] [--query-limit N]
"""

import argparse
import os
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
    parser.add_argument("--cleanup", "--apply-retention", dest="cleanup", action="store_true", help="Execute retention policy to purge stale data and reclaim storage")
    parser.add_argument("--interview-briefing", "--force-interview", dest="force_interview", action="store_true", help="Force generation and email dispatch of consolidated daily interview briefing")

    args = parser.parse_args()

    if args.validate_phase:
        from src.cli.phase_validator import validate_application_phase
        success = validate_application_phase()
        sys.exit(0 if success else 1)

    config = load_config()

    if args.cleanup:
        from src.maintenance.retention_manager import RetentionManager
        mgr = RetentionManager(config)
        report = mgr.apply_retention_policy(dry_run=args.dry_run)
        db = report.get("database", {})
        storage = report.get("storage", {})
        print("\n" + "=" * 65)
        print("  RETENTION & STORAGE CLEANUP REPORT")
        print("=" * 65)
        print(f"  Status:                   {report.get('status')}")
        print(f"  Mode:                     {'DRY RUN' if args.dry_run else 'LIVE PURGE'}")
        print(f"  Stale Jobs Purged:        {db.get('jobs_purged', 0)}")
        print(f"  Historical Runs Purged:   {db.get('runs_purged', 0)}")
        print(f"  Market Signals Purged:    {db.get('signals_purged', 0)}")
        print(f"  Draft Resumes Purged:     {db.get('resume_versions_purged', 0)}")
        print(f"  SQLite VACUUM:            {'EXECUTED' if db.get('vacuum_executed') else 'SKIPPED'}")
        print("-" * 65)
        print(f"  Log Files Deleted:        {storage.get('logs_deleted', 0)}")
        print(f"  Scratch Files Deleted:    {storage.get('scratch_files_deleted', 0)}")
        print(f"  Orphan Resumes Deleted:   {storage.get('draft_resumes_deleted', 0)}")
        print(f"  Scratch Evidence Deleted: {storage.get('evidence_files_deleted', 0)}")
        print(f"  Storage Reclaimed:        {storage.get('bytes_reclaimed', 0):,} bytes")
        print("=" * 65 + "\n")
        sys.exit(0)

    # LIVE mode is enforced by default unless --dry-run or DRY_RUN=true is specified
    env_dry = os.environ.get("DRY_RUN", "").strip().lower() in ("true", "1", "yes")
    if args.dry_run or env_dry:
        config["application"]["dry_run"] = True
    else:
        config["application"]["dry_run"] = False

    is_dry = config["application"]["dry_run"]
    logger.info(f"Initiating Autonomous Career Agent (LIVE={not is_dry}, OFFLINE={args.offline})...")

    orchestrator = Orchestrator(config=config, offline_mode=args.offline)
    daily_report = orchestrator.run_daily_pipeline(
        force_weekly=args.weekly,
        force_interview=args.force_interview,
        query_limit=args.query_limit,
    )

    print("\n" + "=" * 60)
    print(f"  RUN COMPLETE: {daily_report.date} (Run ID: {daily_report.run_id})")
    print("=" * 60)
    print(f"  Jobs Scanned:             {daily_report.jobs_scanned}")
    print(f"  Salary Rejects (<30 LPA): {daily_report.salary_rejected}")
    print(f"  Qualified Opportunities:  {daily_report.qualified_jobs}")
    print(f"  Resumes Tailored:         {daily_report.resumes_generated}")
    print(f"  Applications Submitted:   {daily_report.applications_submitted} ({'DRY RUN' if is_dry else 'LIVE'})")
    print(f"  Interview Packs Built:    {daily_report.interview_packs_generated}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
