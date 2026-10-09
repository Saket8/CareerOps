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
    parser.add_argument("--today", action="store_true", help="Scope phase validation strictly to today's applications")
    parser.add_argument("--cleanup", "--apply-retention", dest="cleanup", action="store_true", help="Execute retention policy to purge stale data and reclaim storage")
    parser.add_argument("--interview-briefing", "--force-interview", dest="force_interview", action="store_true", help="Force generation and email dispatch of consolidated daily interview briefing")
    parser.add_argument("--refresh-profile", "--upload-cv", dest="refresh_profile", action="store_true", help="Re-upload master CV to Naukri profile to refresh Resdex rank")
    parser.add_argument("--optimize-linkedin", "--optimize-profile", dest="optimize_linkedin", action="store_true", help="Optimize LinkedIn Profile headline, about section, and SEO keywords")
    parser.add_argument("--force-run", action="store_true", help="Bypass day-of-week schedule check")

    args = parser.parse_args()

    config = load_config()

    if args.optimize_linkedin:
        from src.linkedin.adapter import LinkedInAdapter
        from candidate.profile_extractor import get_candidate_truth
        print("\n[INFO] Executing LinkedIn Profile SEO Optimization (Headline, About, Keywords)...")
        cand_truth = get_candidate_truth()
        li_adapter = LinkedInAdapter(config=config, candidate_truth=cand_truth, offline_mode=args.offline)
        res = li_adapter.optimize_profile_keywords(dry_run=args.dry_run)
        print(f"[RESULT] {res}\n")
        sys.exit(0 if res.get("success") else 1)

    if args.refresh_profile:
        from src.naukri.playwright_adapter import PlaywrightBrowserAdapter
        cv_path = config.get("resume", {}).get("source_path", "resumes/master/Saket_Saurav_OCI.docx")
        print(f"\n[INFO] Re-uploading master CV to Naukri profile: {cv_path}")
        client = PlaywrightBrowserAdapter(offline_mode=args.offline)
        res = client.refresh_profile_resume(cv_path)
        print(f"[RESULT] {res}\n")
        sys.exit(0 if res.get("success") else 1)

    if args.validate_phase:
        from src.cli.phase_validator import validate_application_phase
        date_scope = "today" if args.today else None
        success = validate_application_phase(date_scope=date_scope)
        sys.exit(0 if success else 1)

    # Schedule Gate: Check if today is an active operations day per schedule configuration
    if not args.force_run and not args.validate_phase and not args.cleanup:
        import datetime
        try:
            import zoneinfo
            tz_name = config.get("schedule", {}).get("timezone", "Asia/Kolkata")
            tz = zoneinfo.ZoneInfo(tz_name)
        except Exception:
            tz = datetime.timezone.utc
        current_day_name = datetime.datetime.now(tz).strftime("%A").lower()
        allowed_days = [d.lower().strip() for d in config.get("schedule", {}).get("days", ["monday", "tuesday", "wednesday", "thursday", "friday"])]
        if current_day_name not in allowed_days:
            logger.info(
                f"SCHEDULE GATE: Today is {current_day_name.capitalize()}, which is excluded from operations "
                f"per schedule policy ({allowed_days}). Halting execution (no job discovery, applications, or alerts)."
            )
            print(f"\n[INFO] Today is {current_day_name.capitalize()} (Weekend/Excluded Day). No operations scheduled per config.yaml. Exiting cleanly.\n")
            sys.exit(0)

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
