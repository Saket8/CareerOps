"""Guaranteed Daily Report Dispatcher.

Ensures that an application report email is dispatched to the candidate (sauravskt8@gmail.com)
every single day, even if main.py or post_run_healer encountered an unexpected exit or timeout.
"""

import sys
import os
import json
import argparse
from pathlib import Path

sys.path.insert(0, "/u01/CareerOps")

from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

from src.utils.config_loader import load_config
from src.database.connection import get_db_session
from src.database.models import ApplicationModel, JobModel
from src.email_service.smtp_mailer import SmtpMailer
from src.models.report import DailyReportData, TopApplicationItem, SourceBreakdownItem
from src.models.job import JobStatus
from src.agents.reporting import ReportingAgent
from src.utils.logger import get_logger
from sqlalchemy import func

logger = get_logger("guaranteed_email_dispatch")


def dispatch_guaranteed_report(target_date: str = None, force: bool = False) -> bool:
    config = load_config()
    tz_name = config.get("schedule", {}).get("timezone", "Asia/Kolkata")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc

    today_str = target_date or datetime.now(tz).strftime("%Y-%m-%d")
    logger.info(f"Checking guaranteed email delivery for {today_str} (force={force})...")

    dispatch_history_path = Path("artifacts/dispatched_emails.json")
    dispatched_records = []
    if dispatch_history_path.exists():
        try:
            dispatched_records = json.loads(dispatch_history_path.read_text(encoding="utf-8"))
            if not isinstance(dispatched_records, list):
                dispatched_records = []
        except Exception as e:
            logger.warning(f"Error reading dispatch history: {e}")

    # Check if already delivered today
    if not force:
        already_dispatched = any(
            rec.get("date") == today_str and rec.get("success", True)
            for rec in dispatched_records
        )
        if already_dispatched:
            logger.info(f"Daily report email already dispatched for {today_str}. Skipping to prevent duplicates.")
            return True

    with get_db_session() as session:
        # Fetch all applications submitted or attempted today
        apps_today = session.query(ApplicationModel, JobModel).join(
            JobModel, ApplicationModel.job_id == JobModel.job_id
        ).filter(
            (func.date(ApplicationModel.submitted_at) == today_str) |
            (func.date(ApplicationModel.started_at) == today_str)
        ).all()

        logger.info(f"Found {len(apps_today)} application records for {today_str} in database.")

        confirmed_apps = []
        other_apps = []

        source_counts = {
            "Naukri": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
            "LinkedIn": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
            "ATS Portal": {"discovered": 0, "qualified": 0, "attempted": 0, "confirmed": 0, "skipped": 0, "failed": 0},
        }

        top_items = []
        current_job_urls = []

        for app, job in apps_today:
            # Exclude historical already applied
            if app.confirmation_reference == "ALREADY_APPLIED" and (not app.submitted_at or str(app.submitted_at)[:10] != today_str):
                continue

            src = "LinkedIn" if ("linkedin" in (job.source_platform or "").lower() or app.application_method == "LINKEDIN_EASY_APPLY") else "Naukri"
            source_counts[src]["attempted"] += 1

            is_confirmed = (app.status == JobStatus.APPLIED_CONFIRMED.value and app.confirmation_reference != "ALREADY_APPLIED")
            if is_confirmed:
                source_counts[src]["confirmed"] += 1
                confirmed_apps.append((app, job))
            else:
                source_counts[src]["failed"] += 1
                other_apps.append((app, job))

            if job.url:
                current_job_urls.append(job.url)

            top_items.append(
                TopApplicationItem(
                    company=job.company or "Unknown",
                    role=job.title or "Unknown",
                    salary="Market Competitive",
                    match_score=85.0,
                    key_factors=["Cloud Architecture", "OCI", "AI/ML"],
                    resume_used=app.resume_version or "Master CV",
                    status=app.status,
                    url=job.url or "",
                    method=app.application_method or src,
                    reason=app.failure_reason,
                    confirmation_ref=app.confirmation_reference,
                )
            )

        rep_cfg = config.get("reporting", {})
        daily_dir = Path(rep_cfg.get("daily_dir", "reports/daily"))
        weekly_dir = Path(rep_cfg.get("weekly_dir", "reports/weekly"))
        reporting_agent = ReportingAgent(daily_dir=daily_dir, weekly_dir=weekly_dir)

        source_breakdown = [
            SourceBreakdownItem(
                source=s,
                discovered=counts["discovered"],
                qualified=counts["qualified"],
                attempted=counts["attempted"],
                confirmed=counts["confirmed"],
                skipped=counts["skipped"],
                failed=counts["failed"],
            )
            for s, counts in source_counts.items()
        ]

        now_utc = datetime.now(timezone.utc)
        daily_data = DailyReportData(
            run_id=f"guaranteed_{today_str}_{int(now_utc.timestamp())}",
            date=today_str,
            start_time=now_utc,
            end_time=now_utc,
            dry_run=False,
            jobs_scanned=len(apps_today),
            salary_rejected=0,
            qualified_jobs=len(apps_today),
            strong_matches=len(confirmed_apps),
            resumes_generated=len(apps_today),
            applications_submitted=len(apps_today),
            applications_confirmed=len(confirmed_apps),
            applications_unverified=0,
            applications_external=0,
            applications_manual_intervention=0,
            blocked_applications=0,
            failed_applications=len(other_apps),
            interview_packs_generated=len(confirmed_apps),
            profile_refresh_status="ACTIVE",
            top_applications=top_items,
            source_breakdown=source_breakdown,
        )

        d_md, d_html, d_html_content = reporting_agent.generate_daily_report(daily_data)

        # Dispatch email
        subject = f"CareerOps — Daily Application Report — {today_str}"
        smtp_mailer = SmtpMailer(config)
        sent = smtp_mailer.send_report(
            subject=subject,
            html_body=d_html_content,
            attachments=[],
        )

        if sent:
            recipient = config.get("email", {}).get("default_recipient", "sauravskt8@gmail.com")
            logger.info(f"Successfully sent guaranteed daily report email for {today_str} to {recipient}!")
            dispatched_records.append({
                "run_id": daily_data.run_id,
                "date": today_str,
                "timestamp": now_utc.isoformat(),
                "job_urls": current_job_urls,
                "applications_count": len(top_items),
                "confirmed_count": len(confirmed_apps),
                "subject": subject,
                "success": True,
            })
            dispatch_history_path.write_text(json.dumps(dispatched_records, indent=2), encoding="utf-8")
            return True
        else:
            logger.error(f"Failed to deliver guaranteed daily report email for {today_str}.")
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Guaranteed Daily Report Dispatcher")
    parser.add_argument("--date", type=str, default=None, help="Target date YYYY-MM-DD")
    parser.add_argument("--force", action="store_true", help="Force email dispatch even if recorded")
    args = parser.parse_args()

    success = dispatch_guaranteed_report(target_date=args.date, force=args.force)
    sys.exit(0 if success else 1)
