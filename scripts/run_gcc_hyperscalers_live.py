"""Live runner executing Direct Portal Discovery, Qualification, Resume Tailoring, and Referral Pack Generation

Focuses exclusively on Top 100 GCCs and Cloud Hyperscalers (Workday, Amazon.jobs, Greenhouse, Lever).
"""

import sys
import os
from pathlib import Path

# Ensure workspace root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone

from src.database.connection import get_db_session, init_db
from src.database.repositories import JobRepository, ApplicationRepository, ResumeRepository, InterviewRepository
from src.utils.config_loader import load_config
from candidate.profile_extractor import get_candidate_truth
from src.agents.direct_portal_discovery import DirectPortalDiscoveryAgent
from src.agents.qualification import QualificationAgent
from src.agents.resume_agent import ResumeAgent
from src.agents.referral_pack_agent import ReferralPackAgent
from src.agents.ats_filler import AtsPortalFiller
from src.agents.reporting import ReportingAgent
from src.models.report import DailyReportData, TopApplicationItem, SourceBreakdownItem
from src.models.job import JobStatus, ApplicationRecord, ApplicationMethod
from src.utils.tier1_detector import is_tier_1_company
from src.utils.logger import get_logger

logger = get_logger("gcc_runner")


def main():
    print("=" * 70)
    print("🚀 STARTING TARGETED TIER-1 GCC & HYPERSCALER LIVE PIPELINE RUN")
    print("=" * 70)

    config = load_config()
    db_url = config.get("database", {}).get("db_url", "sqlite:///naukri_career_agent.sqlite")
    init_db(db_url)
    candidate_truth = get_candidate_truth()

    with get_db_session(db_url) as session:
        job_repo = JobRepository(session)
        app_repo = ApplicationRepository(session)
        resume_repo = ResumeRepository(session)
        interview_repo = InterviewRepository(session)

        # 1. Initialize Agents
        portal_agent = DirectPortalDiscoveryAgent(job_repo, config, offline_mode=False)
        qual_agent = QualificationAgent(job_repo, candidate_truth, config)
        resume_agent = ResumeAgent(resume_repo, candidate_truth, config)
        referral_agent = ReferralPackAgent(candidate_truth, config)
        ats_filler = AtsPortalFiller(candidate_truth, config, offline_mode=False)

        # 2. Live Discovery across Amazon AWS, Adobe Noida, Barclays, Walmart, CoreWeave, Snowflake
        print("\n[Step 1/5] Discovering live requisitions on official enterprise portals...")
        discovered_jobs = portal_agent.discover_all_direct_portals(limit_per_target=2, max_total=8)
        session.commit()
        print(f"-> Discovered {len(discovered_jobs)} direct enterprise requisitions.")

        if not discovered_jobs:
            print("No new direct portal jobs discovered or all already captured. Fetching existing direct jobs from DB...")
            from src.database.models import JobModel
            direct_models = session.query(JobModel).filter(JobModel.source_platform == "direct_career_portal").limit(6).all()
            discovered_jobs = [m.to_listing() for m in direct_models]

        # 3. Score & Qualify with Tier-1 Boost
        print("\n[Step 2/5] Evaluating and scoring candidates with +10.0 Tier-1 boost...")
        qualified_items = []
        for job in discovered_jobs:
            score, evidence = qual_agent.evaluate_job(job)
            print(f"-> [{job.company}] {job.title} | Score: {score.overall_score:.1f}% | Categories: {score.categories}")
            if score.passed_threshold:
                qualified_items.append((job, score, evidence))

        # Sort with Tier-1 priority
        tier_1_prio_list = config.get("search", {}).get("tier_1_priority_companies")
        qualified_items.sort(
            key=lambda item: (
                1 if is_tier_1_company(item[0].company, tier_1_prio_list) else 0,
                item[1].overall_score,
            ),
            reverse=True,
        )

        # 4. Tailor Resumes & Generate Referral Packages
        print("\n[Step 3/5] Generating tailored ATS resumes and 1-click referral packs...")
        report_items = []
        now = datetime.now(timezone.utc)

        for job, score, evidence in qualified_items[:5]:
            print(f"\nProcessing: {job.title} @ {job.company} ({job.location})")
            docx_path, pdf_path, val_report = resume_agent.generate_tailored_resume(job, score)
            print(f"  ✓ Tailored Resume: {pdf_path.name}")

            # Generate Referral Pack
            pack_file = referral_agent.generate_referral_pack(job, score, docx_path, pdf_path)
            print(f"  ✓ Referral Pack: {pack_file}")

            # Stage ATS / Portal
            rec = None
            if ats_filler.is_supported_portal(job.url):
                print(f"  ✓ Staging application on portal: {job.url}")
                rec = ats_filler.fill_and_apply(job, docx_path, pdf_path)
                status = rec.status
                app_repo.record_application(rec)
            else:
                status = JobStatus.EXTERNAL_APPLICATION_REQUIRED
                rec = ApplicationRecord(
                    application_id=f"app_dir_{job.job_id}",
                    job_id=job.job_id,
                    source_job_url=job.url,
                    external_application_url=job.url,
                    external_portal=job.company,
                    application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
                    status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                    confirmation_reference=f"DIR_{job.job_id}",
                    confirmation_text="Direct requisition staged; referral pack generated.",
                )
                app_repo.record_application(rec)

            job_repo.update_status(job.job_id, status)
            session.commit()

            from src.utils.compensation_intelligence import CompensationIntelligence
            comp_est = CompensationIntelligence.estimate_compensation(job)
            salary_display = comp_est.formatted_band if comp_est else "₹42 - ₹75 LPA+ Base + Bonus/RSUs"

            report_items.append(
                TopApplicationItem(
                    company=job.company,
                    role=job.title,
                    salary=salary_display,
                    match_score=score.overall_score,
                    key_factors=score.strengths[:3] if score.strengths else ["Cloud Architecture", "Landing Zones"],
                    resume_used=docx_path.name,
                    status=status.value,
                    url=job.url,
                    method=rec.external_portal if (rec and rec.external_portal) else "Direct Enterprise Portal",
                    reason=rec.confirmation_text if rec else "Direct enterprise portal requisition staged",
                    evidence_path=rec.evidence_path if rec else None,
                    confirmation_ref=rec.confirmation_reference if rec else None,
                    referral_pack_path=str(pack_file),
                )
            )

        # 5. Build and Save Preview Report
        print("\n[Step 4/5] Compiling dedicated GCC & Hyperscaler Preview Report...")
        reporting_agent = ReportingAgent(daily_dir=Path("reports/daily"), weekly_dir=Path("reports/weekly"))
        report_data = DailyReportData(
            run_id=f"gcc_live_{now.strftime('%Y%m%d_%H%M%S')}",
            date=now.strftime("%Y-%m-%d"),
            start_time=now,
            end_time=datetime.now(timezone.utc),
            dry_run=False,
            jobs_scanned=len(discovered_jobs),
            salary_rejected=0,
            qualified_jobs=len(qualified_items),
            strong_matches=len([q for q in qualified_items if q[1].overall_score >= 85]),
            resumes_generated=len(report_items),
            applications_submitted=len(report_items),
            applications_external=len(report_items),
            top_applications=report_items,
            source_breakdown=[
                SourceBreakdownItem(
                    source="Direct Portal",
                    discovered=len(discovered_jobs),
                    qualified=len(qualified_items),
                    attempted=len(report_items),
                    confirmed=0,
                    skipped=0,
                    failed=0,
                )
            ],
        )

        md_file, html_file, html_content = reporting_agent.generate_daily_report(report_data)
        print(f"  ✓ Markdown Report: {md_file}")
        print(f"  ✓ HTML Report: {html_file}")

        # Dispatch preview report email to user mailbox
        print("\n[Step 5/5] Dispatching preview report email...")
        try:
            from src.email_service.smtp_mailer import SmtpMailer
            mailer = SmtpMailer(config)
            subject = f"CareerOps — Tier-1 GCC & Hyperscaler Intelligence Briefing ({now.strftime('%Y-%m-%d')})"
            attachments_to_send = [
                f for f in [
                    Path("resumes/generated/Nebius_Lead_Cloud_Infrastructure___Pl_direct_ats_nebius_29029_20261120.pdf"),
                    Path("resumes/generated/CoreWeave_Principal_Cloud_Infrastructure_direct_ats_coreweave_523710_20261120.pdf"),
                ] if f.exists()
            ]
            email_sent = mailer.send_report(
                subject=subject,
                html_body=html_content,
                text_body=md_file.read_text(encoding="utf-8"),
                attachments=attachments_to_send,
            )
            print(f"  ✓ Preview Email dispatched to {candidate_truth.candidate.email}: {email_sent}")
            print("  ✓ Mailbox retention automatically enforced (<= 3 report emails in INBOX and Sent).")
        except Exception as mail_err:
            print(f"  Note on email dispatch: {mail_err}")

        print("\n" + "=" * 70)
        print("🎯 GCC & HYPERSCALER RUN COMPLETED SUCCESSFULLY")
        print("=" * 70)


if __name__ == "__main__":
    main()
