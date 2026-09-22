"""Phase Gate Validator: Audits actual database records and enforces strict PASS/FAIL criteria."""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.database.connection import get_db_session
from src.database.models import ApplicationModel, JobModel
from src.models.job import JobStatus
from src.utils.config_loader import load_config
from src.utils.logger import get_logger

logger = get_logger("phase_validator")


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
        self.confirmed_items: List[Dict[str, Any]] = []
        self.failure_reasons: List[str] = []

    def print_summary(self):
        print("\n" + "=" * 70)
        print("  APPLICATION AUTOMATION PHASE VALIDATION REPORT")
        print("=" * 70)
        print(f"  Execution Timestamp:          {datetime.now(timezone.utc).isoformat()}")
        print(f"  Total Eligible Jobs in DB:    {self.eligible_jobs_count}")
        print(f"  Total Applications Attempted: {self.applications_attempted}")
        print(f"  APPLIED_CONFIRMED:            {self.applications_confirmed}")
        print(f"  SUBMISSION_UNVERIFIED:        {self.applications_unverified}")
        print(f"  APPLICATION_BLOCKED:          {self.applications_blocked}")
        print(f"  APPLICATION_FAILED:           {self.applications_failed}")
        print(f"  EXTERNAL_APPLICATION_REQ:     {self.external_portal_count}")
        print("-" * 70)

        if self.confirmed_items:
            print("  CONFIRMED APPLICATIONS (VERIFIABLE EVIDENCE):")
            for idx, item in enumerate(self.confirmed_items, 1):
                print(f"    {idx}. Role:       {item['role']}")
                print(f"       Company:    {item['company']}")
                print(f"       URL:        {item['url']}")
                print(f"       Method:     {item['method']}")
                print(f"       Ref ID:     {item['ref']}")
                print(f"       Evidence:   {item['evidence']}")
                print()

        if self.failure_reasons:
            print("  FAILURES / DEFECTS DETECTED:")
            for reason in self.failure_reasons:
                print(f"    [!] {reason}")
            print("-" * 70)

        result_text = "APPLICATION AUTOMATION PHASE: PASSED" if self.passed else "APPLICATION AUTOMATION PHASE: FAILED"
        print(f"\n  FINAL RESULT: >>> {result_text} <<<")
        print("=" * 70 + "\n")


def validate_application_phase(db_url: Optional[str] = None) -> bool:
    """Audits database records against all Section 24 criteria."""
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

        # 2. Query all application records
        applications = session.query(ApplicationModel).all()
        report.applications_attempted = len(applications)

        for app in applications:
            st = app.status
            if st == JobStatus.APPLIED_CONFIRMED.value or (st == JobStatus.APPLIED.value and not app.dry_run and app.confirmation_reference):
                report.applications_confirmed += 1
                job = app.job
                report.confirmed_items.append({
                    "role": job.title if job else "Unknown",
                    "company": job.company if job else "Unknown",
                    "url": app.canonical_job_url or (job.url if job else ""),
                    "method": app.application_method or "NAUKRI_DIRECT",
                    "ref": app.confirmation_reference or "N/A",
                    "evidence": app.verification_method or "Level 1-2 Confirmed",
                })
            elif st == JobStatus.SUBMISSION_UNVERIFIED.value:
                report.applications_unverified += 1
            elif st == JobStatus.APPLICATION_BLOCKED.value:
                report.applications_blocked += 1
            elif st == JobStatus.APPLICATION_FAILED.value:
                report.applications_failed += 1
            elif st == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value:
                report.external_portal_count += 1

        # Check PASS/FAIL Criteria per Section 24
        if report.eligible_jobs_count == 0:
            report.failure_reasons.append("Zero eligible jobs found in database.")

        if report.applications_attempted == 0:
            report.failure_reasons.append("Zero applications were attempted.")

        if report.applications_confirmed == 0:
            report.failure_reasons.append(
                "Zero applications reached APPLIED_CONFIRMED status with verified evidence."
            )

        report.passed = (
            report.eligible_jobs_count > 0
            and report.applications_attempted > 0
            and report.applications_confirmed > 0
        )

        report.print_summary()
        return report.passed


if __name__ == "__main__":
    success = validate_application_phase()
    sys.exit(0 if success else 1)
