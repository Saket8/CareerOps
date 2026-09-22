"""Phase Gate Validator: Audits actual database records and enforces strict PASS/FAIL criteria."""

import os
import sys
from pathlib import Path

# Ensure workspace root is in sys.path
workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from src.database.connection import get_db_session
from src.database.models import ApplicationModel, JobModel
from src.models.job import JobStatus
from src.utils.config_loader import load_config
from src.utils.logger import get_logger

logger = get_logger("phase_validator")


import argparse
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional


class PhaseValidationReport:
    def __init__(self):
        self.passed: bool = False
        self.eligible_jobs_count: int = 0
        self.applications_attempted: int = 0
        self.applications_confirmed: int = 0
        self.applications_unverified: int = 0
        self.applications_blocked: int = 0
        self.applications_failed: int = 0
        self.external_portal_count: int = 0
        self.evidence_files_verified: int = 0
        self.confirmed_items: List[Dict[str, Any]] = []
        self.failure_reasons: List[str] = []

    def print_summary(self):
        print("\n" + "=" * 70)
        print("  APPLICATION AUTOMATION PHASE VALIDATION REPORT (PROOF-BASED)")
        print("=" * 70)
        print(f"  Execution Timestamp:          {datetime.now(timezone.utc).isoformat()}")
        print(f"  Total Eligible Jobs in DB:    {self.eligible_jobs_count}")
        print(f"  Total Applications Audited:   {self.applications_attempted}")
        print(f"  APPLIED_CONFIRMED:            {self.applications_confirmed}")
        print(f"  Evidence Files Verified:      {self.evidence_files_verified}")
        print(f"  SUBMISSION_UNVERIFIED:        {self.applications_unverified}")
        print(f"  APPLICATION_BLOCKED:          {self.applications_blocked}")
        print(f"  APPLICATION_FAILED:           {self.applications_failed}")
        print(f"  EXTERNAL_APPLICATION_REQ:     {self.external_portal_count}")
        print("-" * 70)

        if self.confirmed_items:
            print("  CONFIRMED APPLICATIONS (VERIFIABLE PHYSICAL PROOF):")
            for idx, item in enumerate(self.confirmed_items, 1):
                print(f"    {idx}. Role:       {item['role']}")
                print(f"       Company:    {item['company']}")
                print(f"       URL:        {item['url']}")
                print(f"       Method:     {item['method']}")
                print(f"       Ref ID:     {item['ref']}")
                print(f"       Evidence:   {item['evidence']}")
                print(f"       File Proof: {item['file_proof']} ({item['file_size']} bytes)")
                print()

        if self.failure_reasons:
            print("  FAILURES / DEFECTS DETECTED:")
            for reason in self.failure_reasons:
                print(f"    [!] {reason}")
            print("-" * 70)

        result_text = "APPLICATION AUTOMATION PHASE: PASSED" if self.passed else "APPLICATION AUTOMATION PHASE: FAILED"
        print(f"\n  FINAL RESULT: >>> {result_text} <<<")
        print("=" * 70 + "\n")


def validate_application_phase(
    db_url: Optional[str] = None,
    date_scope: Optional[str] = None,
    require_confirmed: bool = True,
) -> bool:
    """Audits database records strictly against proof-based criteria.
    
    Args:
        db_url: Optional SQLite database URL override.
        date_scope: 'today', a 'YYYY-MM-DD' date string, or None for all-time.
        require_confirmed: If True, at least one verified confirmed application or
                           external opportunity is strictly required for PASS.
    """
    config = load_config()
    target_db = db_url or config.get("database", {}).get("db_url", "sqlite:///naukri_career_agent.sqlite")

    report = PhaseValidationReport()

    with get_db_session(target_db) as session:
        # 1. Count eligible jobs
        all_jobs = session.query(JobModel).all()
        report.eligible_jobs_count = len([j for j in all_jobs if j.status in (
            JobStatus.QUALIFIED.value,
            JobStatus.HIGH_MATCH.value,
            JobStatus.APPLIED.value,
            JobStatus.APPLIED_CONFIRMED.value,
            JobStatus.APPLICATION_READY.value,
        )])

        # 2. Query application records with optional date filtering
        query = session.query(ApplicationModel)
        if date_scope:
            if date_scope.lower() == "today":
                target_date = datetime.now(timezone.utc).date()
            else:
                target_date = datetime.strptime(date_scope, "%Y-%m-%d").date()
            start_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
            end_dt = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc)
            query = query.filter(
                (ApplicationModel.submitted_at >= start_dt) & (ApplicationModel.submitted_at <= end_dt)
                | (ApplicationModel.created_at >= start_dt) & (ApplicationModel.created_at <= end_dt)
            )

        applications = query.all()
        report.applications_attempted = len(applications)

        for app in applications:
            st = app.status
            if st == JobStatus.APPLIED_CONFIRMED.value or (st == JobStatus.APPLIED.value and not app.dry_run and app.confirmation_reference):
                # Physical Evidence Verification Invariant
                ev_path = app.evidence_path
                file_verified = False
                file_size = 0
                if ev_path:
                    # Resolve relative to workspace root if needed
                    resolved_path = Path(ev_path) if os.path.isabs(ev_path) else (Path.cwd() / ev_path)
                    if resolved_path.exists() and resolved_path.is_file():
                        file_size = resolved_path.stat().st_size
                        if file_size > 0:
                            file_verified = True
                            report.evidence_files_verified += 1
                        else:
                            report.failure_reasons.append(
                                f"Corrupt visual evidence file (0 bytes) for job {app.job_id}: {ev_path}"
                            )
                    else:
                        report.failure_reasons.append(
                            f"Missing visual evidence file on disk for confirmed job {app.job_id}: {ev_path}"
                        )
                else:
                    report.failure_reasons.append(
                        f"Missing evidence_path in database record for confirmed job {app.job_id}"
                    )

                # Verification method verification: must be reload badge, modal ref, or direct confirmed
                method = app.verification_method or ""
                allowed_methods = (
                    "LEVEL_3_BUTTON_ALREADY_APPLIED",
                    "RELOAD_BADGE_CONFIRMED",
                    "LEVEL_1_DIRECT_MODAL",
                    "DIRECT_MODAL_CONFIRMED",
                    "Level 1-2 Confirmed",
                )
                if not any(m in method for m in allowed_methods):
                    report.failure_reasons.append(
                        f"Unverified confirmation method '{method}' for job {app.job_id}; must be reload badge or modal reference."
                    )

                report.applications_confirmed += 1
                job = app.job
                report.confirmed_items.append({
                    "role": job.title if job else "Unknown",
                    "company": job.company if job else "Unknown",
                    "url": app.canonical_job_url or (job.url if job else ""),
                    "method": app.application_method or "NAUKRI_DIRECT",
                    "ref": app.confirmation_reference or "N/A",
                    "evidence": app.verification_method or "N/A",
                    "file_proof": ev_path or "MISSING",
                    "file_size": file_size,
                })
            elif st == JobStatus.SUBMISSION_UNVERIFIED.value:
                report.applications_unverified += 1
            elif st == JobStatus.APPLICATION_BLOCKED.value:
                report.applications_blocked += 1
            elif st == JobStatus.APPLICATION_FAILED.value:
                report.applications_failed += 1
                report.failure_reasons.append(f"Recorded application failure for job {app.job_id}: {app.failure_reason}")
            elif st == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value:
                report.external_portal_count += 1

        # Check Strict PASS/FAIL Criteria
        if report.eligible_jobs_count == 0:
            report.failure_reasons.append("Zero eligible jobs found in database.")

        if require_confirmed and (report.applications_confirmed == 0 and report.external_portal_count == 0):
            report.failure_reasons.append("Zero confirmed applications or external portal opportunities in scope.")

        # PASS strictly requires confirmed opportunities, zero fatal defects, and verified physical evidence
        report.passed = (
            report.eligible_jobs_count > 0
            and (report.applications_confirmed > 0 or report.external_portal_count > 0)
            and len(report.failure_reasons) == 0
        )

        report.print_summary()
        return report.passed


def main():
    parser = argparse.ArgumentParser(description="Proof-Based Phase Gate Validator")
    parser.add_argument("--db", type=str, help="SQLite database URL override")
    parser.add_argument("--today", action="store_true", help="Scope validation strictly to today's applications")
    parser.add_argument("--run-date", type=str, help="Scope validation to a specific date (YYYY-MM-DD)")
    args = parser.parse_args()

    date_scope = "today" if args.today else args.run_date
    success = validate_application_phase(db_url=args.db, date_scope=date_scope)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
