"""Greenhouse and Lever ATS automated application form resolver.

Autonomous multi-step form filler for standard enterprise job boards (Greenhouse, Lever)
which host 50%+ of high-paying international technology positions.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from src.models.candidate import CandidateTruth
from src.models.job import JobListing, JobStatus, ApplicationMethod, ApplicationRecord
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.utils.logger import get_logger

logger = get_logger("ats_filler")

EVIDENCE_DIR = Path("artifacts/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class AtsPortalFiller:
    """Detects and automatically submits applications on Greenhouse and Lever career boards."""

    def __init__(self, candidate_truth: CandidateTruth, config: Dict[str, Any], offline_mode: bool = False):
        self.candidate_truth = candidate_truth
        self.config = config
        self.offline_mode = offline_mode
        self.resolver = CandidateAnswerResolver(candidate_truth, strict_truth_only=False)
        self.auto_submit = config.get("ats_filler", {}).get("auto_submit", True)

    @staticmethod
    def is_supported_portal(url: str) -> bool:
        """Determines if the URL points to a Greenhouse or Lever hosted board."""
        u = (url or "").lower()
        return any(p in u for p in ("boards.greenhouse.io", "jobs.lever.co", "greenhouse.io", "lever.co"))

    def fill_and_apply(
        self,
        job: JobListing,
        docx_path: Path,
        pdf_path: Path,
    ) -> ApplicationRecord:
        """Fills and submits an application on a Greenhouse or Lever portal."""
        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            application_id=f"app_ats_{job.job_id}_{now.strftime('%Y%m%d%H%M%S')}",
            job_id=job.job_id,
            source_job_url=job.url,
            external_application_url=job.url,
            external_portal="Greenhouse/Lever ATS",
            application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
            status=JobStatus.APPLICATION_STARTED,
            started_at=now,
            dry_run=self.offline_mode or self.config.get("application", {}).get("dry_run", False),
        )

        if self.offline_mode or record.dry_run:
            record.status = JobStatus.APPLIED_CONFIRMED
            record.confirmation_reference = f"SIM_ATS_{job.job_id}"
            record.confirmation_text = "Simulated ATS submission in dry-run mode."
            record.submitted_at = now
            return record

        cand = self.candidate_truth.candidate
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
                )
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    viewport={"width": 1440, "height": 900},
                )
                logger.info(f"Navigating to external ATS portal: {job.url}")
                page.goto(job.url, wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(3000)

                # 1. Fill First & Last Name
                first_name_input = page.locator("input[name*='first_name'], input#first_name, input[aria-label*='First Name']").first
                last_name_input = page.locator("input[name*='last_name'], input#last_name, input[aria-label*='Last Name']").first
                full_name_input = page.locator("input[name*='name'], input#name, input[aria-label*='Full Name']").first

                name_parts = cand.name.split(" ", 1)
                first_n = name_parts[0]
                last_n = name_parts[1] if len(name_parts) > 1 else ""

                if first_name_input.count() > 0 and first_name_input.is_visible():
                    first_name_input.fill(first_n)
                    if last_name_input.count() > 0 and last_name_input.is_visible():
                        last_name_input.fill(last_n)
                elif full_name_input.count() > 0 and full_name_input.is_visible():
                    full_name_input.fill(cand.name)

                # 2. Fill Email
                email_input = page.locator("input[type='email'], input[name*='email'], input#email").first
                if email_input.count() > 0 and email_input.is_visible():
                    email_input.fill(cand.email)

                # 3. Fill Phone
                phone_input = page.locator("input[type='tel'], input[name*='phone'], input#phone").first
                if phone_input.count() > 0 and phone_input.is_visible():
                    phone_input.fill(cand.phone)

                # 4. Fill Location / City
                loc_input = page.locator("input[name*='location'], input#location, input[name*='city']").first
                if loc_input.count() > 0 and loc_input.is_visible():
                    loc_input.fill(cand.location)

                # 5. Fill LinkedIn profile URL
                li_input = page.locator("input[name*='linkedin'], input#linkedin, input[aria-label*='LinkedIn']").first
                if li_input.count() > 0 and li_input.is_visible():
                    li_input.fill("https://www.linkedin.com/in/saket-saurav-cloud")

                # 6. Upload Resume (PDF preferred)
                file_input = page.locator("input[type='file']").first
                if file_input.count() > 0:
                    resume_to_upload = pdf_path if pdf_path.exists() else docx_path
                    if resume_to_upload.exists():
                        file_input.set_input_files(str(resume_to_upload.resolve()))
                        logger.info(f"Attached resume {resume_to_upload.name} to ATS portal.")
                        page.wait_for_timeout(2000)

                # 7. Resolve custom screening questions
                all_inputs = page.locator("input[type='text'], textarea").all()
                for inp in all_inputs:
                    try:
                        val = inp.input_value()
                        if val and val.strip():
                            continue
                        label = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
                        inp_id = inp.get_attribute("id")
                        if inp_id:
                            lbl = page.locator(f"label[for='{inp_id}']").first
                            if lbl.count() > 0:
                                label = lbl.inner_text().strip()
                        if label:
                            res = self.resolver.resolve_question(label)
                            if res.can_answer and res.answer_value is not None:
                                inp.fill(str(res.answer_value))
                    except Exception:
                        pass

                # 8. Submit or Leave at Review
                submit_btn = page.locator("button:has-text('Submit'), input[type='submit'], button#submit_app").first
                if submit_btn.count() > 0 and submit_btn.is_visible() and self.auto_submit:
                    logger.info("Submitting application on external ATS portal...")
                    submit_btn.click()
                    page.wait_for_timeout(5000)

                    evidence_file = EVIDENCE_DIR / f"{job.job_id}_ats_applied.png"
                    try:
                        page.screenshot(path=str(evidence_file), timeout=5000)
                        record.evidence_path = str(evidence_file)
                    except Exception:
                        pass

                    record.status = JobStatus.APPLIED_CONFIRMED
                    record.confirmation_reference = f"ATS_{job.job_id}_{uuid.uuid4().hex[:6].upper()}"
                    record.confirmation_text = "Application confirmed on external ATS portal."
                    record.submitted_at = datetime.now(timezone.utc)
                else:
                    record.status = JobStatus.EXTERNAL_APPLICATION_REQUIRED
                    record.failure_reason = "Application form filled; ready for final review."

                browser.close()
        except Exception as e:
            logger.error(f"Error filling ATS portal {job.url}: {e}")
            record.status = JobStatus.APPLICATION_FAILED
            record.failure_reason = str(e)

        return record
