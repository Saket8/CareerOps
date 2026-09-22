"""Playwright Browser Adapter implementing real-world job navigation, dynamic form answering, and confirmation verification."""

import os
import re
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.naukri.url_validator import UrlValidator, UrlValidationResult
from src.naukri.verifier import ApplicationVerifier, VerificationEvidence
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.models.job import JobListing, JobStatus, ApplicationRecord, ApplicationMethod
from src.models.candidate import CandidateTruth
from src.utils.salary_parser import parse_salary
from src.utils.logger import get_logger

logger = get_logger("playwright_adapter")

EVIDENCE_DIR = Path("artifacts/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class PlaywrightBrowserAdapter(BaseNaukriClient):
    """Production Playwright adapter executing verified end-to-end applications."""

    def __init__(self, offline_mode: bool = False, headless: bool = True):
        self.offline_mode = offline_mode or os.environ.get("NAUKRI_MOCK", "0") == "1"
        self.headless = headless
        self.url_validator = UrlValidator()
        self.verifier = ApplicationVerifier()

    def search_jobs(
        self,
        query: str,
        locations: Optional[List[str]] = None,
        experience_min: Optional[int] = None,
        experience_max: Optional[int] = None,
        limit: int = 25,
    ) -> List[JobListing]:
        """Discovers jobs via browser or fallback market intelligence."""
        # Use existing browser adapter search logic (with dynamic query-aligned market generator)
        from src.naukri.browser_adapter import NaukriBrowserAdapter
        adapter = NaukriBrowserAdapter(offline_mode=self.offline_mode)
        return adapter.search_jobs(query, locations, experience_min, experience_max, limit)

    def fetch_job_details(self, job_listing: JobListing) -> JobListing:
        """Fetches full job description text for an existing listing."""
        from src.naukri.browser_adapter import NaukriBrowserAdapter
        adapter = NaukriBrowserAdapter(offline_mode=self.offline_mode)
        return adapter.fetch_job_details(job_listing)

    def submit_application(
        self,
        job: JobListing,
        resume_docx_path: str,
        resume_pdf_path: str,
        candidate_truth: CandidateTruth,
        dry_run: bool = True,
    ) -> ApplicationRecord:
        """Executes full verified application workflow via Playwright or offline test verifier."""
        app_id = f"app_{job.job_id}_{int(datetime.now(timezone.utc).timestamp())}"
        started_at = datetime.now(timezone.utc)
        evidence_path = str(EVIDENCE_DIR / f"{job.job_id}_evidence.png")

        # 1. URL Pre-Flight Validation (Section 3 & 20)
        validation = self.url_validator.validate_job_url(
            url=job.url,
            expected_company=job.company,
            expected_title=job.title,
        )
        canonical_url = validation.canonical_url if validation.is_valid else job.url

        if not validation.is_valid and not self.offline_mode and not dry_run:
            logger.warning(f"URL Validation Failed for {job.url}: {validation.failure_reason}")
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                status=JobStatus.APPLICATION_FAILED,
                failure_reason=f"URL Validation Failed: {validation.failure_reason}",
                error_code="INVALID_JOB_URL",
                error_message=validation.failure_reason,
                dry_run=dry_run,
            )

        # 2. DRY RUN SIMULATION MODE
        if dry_run:
            logger.info(f"[DRY_RUN] Simulating application for {job.job_id} ({job.title} @ {job.company})")
            # Build simulated evidence for dry run
            mock_ref = f"MOCK_CONF_{uuid.uuid4().hex[:8].upper()}"
            resolver = CandidateAnswerResolver(candidate_truth)
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                submitted_at=datetime.now(timezone.utc),
                status=JobStatus.APPLIED,
                confirmation_detected=True,
                confirmation_text="Simulated dry run confirmation",
                confirmation_reference=mock_ref,
                final_url=canonical_url,
                verification_method="SIMULATED_DRY_RUN",
                questions_answered=resolver.verified_facts,
                dry_run=True,
            )

        # 3. OFFLINE VERIFICATION FIXTURE (for automated testing of real verifier)
        if self.offline_mode:
            logger.info(f"[OFFLINE_TEST] Executing offline verification fixture for {job.job_id}")
            mock_ref = f"CONF_{uuid.uuid4().hex[:8].upper()}"
            mock_confirmation_html = f"""
            <html>
                <body>
                    <h1>Application submitted successfully!</h1>
                    <p>Thank you for applying for {job.title} at {job.company}.</p>
                    <p>Application ID: {mock_ref}</p>
                </body>
            </html>
            """
            evidence = self.verifier.verify_submission(
                page_content=mock_confirmation_html,
                final_url=f"{canonical_url}/confirmation",
                page_title="Application Submitted Successfully",
                is_simulated_in_test=True,
            )

            resolver = CandidateAnswerResolver(candidate_truth)
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                submitted_at=datetime.now(timezone.utc),
                status=evidence.status,
                confirmation_detected=evidence.confirmed,
                confirmation_text=evidence.confirmation_text,
                confirmation_reference=evidence.confirmation_reference,
                final_url=evidence.final_url,
                verification_method=evidence.verification_level,
                evidence_path=evidence_path,
                questions_answered=resolver.verified_facts,
                dry_run=False,
            )

        # 4. REAL PLAYWRIGHT EXECUTION
        return self._execute_playwright_workflow(
            job=job,
            app_id=app_id,
            canonical_url=canonical_url,
            resume_docx_path=resume_docx_path,
            resume_pdf_path=resume_pdf_path,
            candidate_truth=candidate_truth,
            started_at=started_at,
            evidence_path=evidence_path,
        )

    def _execute_playwright_workflow(
        self,
        job: JobListing,
        app_id: str,
        canonical_url: str,
        resume_docx_path: str,
        resume_pdf_path: str,
        candidate_truth: CandidateTruth,
        started_at: datetime,
        evidence_path: str,
    ) -> ApplicationRecord:
        """Launches Playwright, navigates to the job, inspects form, submits, and verifies."""
        from playwright.sync_api import sync_playwright

        resolver = CandidateAnswerResolver(candidate_truth)
        questions_detected = []
        questions_answered = {}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()

                # Step 1: Open Job Page
                logger.info(f"Navigating to job URL: {canonical_url}")
                page.goto(canonical_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(2)

                # Step 2: Check for Anti-Automation Challenges
                page_text = page.content().lower()
                if "recaptcha" in page_text or "cf-turnstile" in page_text or "verify you are human" in page_text:
                    page.screenshot(path=evidence_path)
                    browser.close()
                    logger.warning(f"CAPTCHA / Bot detection challenged on {canonical_url}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        status=JobStatus.APPLICATION_BLOCKED,
                        failure_reason="Anti-automation challenge (CAPTCHA/Bot detection) encountered",
                        error_code="CAPTCHA_BLOCKED",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 3: Detect Application Type (Direct vs External ATS)
                external_button = page.locator("a:has-text('Apply on company website'), a:has-text('Apply on Employer Site'), button:has-text('Apply on company website')")
                if external_button.count() > 0:
                    external_url = external_button.first.get_attribute("href") or canonical_url
                    page.screenshot(path=evidence_path)
                    browser.close()
                    logger.info(f"External career portal application detected for {job.title} @ {job.company}: {external_url}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        external_application_url=external_url,
                        external_portal="External Career Portal",
                        started_at=started_at,
                        status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                        failure_reason="Application must be completed on external company career portal",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 4: Click Apply Button on Naukri
                apply_button = page.locator("button:has-text('Apply'), a:has-text('Apply'), .apply-button").first
                if not apply_button.is_visible():
                    # Check if already applied
                    if "already applied" in page_text or page.locator("button:has-text('Already Applied')").count() > 0:
                        page.screenshot(path=evidence_path)
                        browser.close()
                        logger.info(f"Job already applied previously: {job.title} @ {job.company}")
                        return ApplicationRecord(
                            application_id=app_id,
                            job_id=job.job_id,
                            application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                            source_job_url=job.url,
                            canonical_job_url=canonical_url,
                            started_at=started_at,
                            submitted_at=datetime.now(timezone.utc),
                            status=JobStatus.APPLIED_CONFIRMED,
                            confirmation_detected=True,
                            confirmation_text="Already Applied state confirmed on listing",
                            confirmation_reference="ALREADY_APPLIED",
                            final_url=page.url,
                            verification_method="LEVEL_3_BUTTON_ALREADY_APPLIED",
                            evidence_path=evidence_path,
                            dry_run=False,
                        )

                    page.screenshot(path=evidence_path)
                    browser.close()
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        status=JobStatus.APPLICATION_FAILED,
                        failure_reason="Apply button not found or listing not accept applications",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                apply_button.click()
                time.sleep(3)

                # Step 5: Check for Login Prompt Modal
                if page.locator("input[placeholder*='Email'], input[type='email'], .login-layer").count() > 0:
                    page.screenshot(path=evidence_path)
                    browser.close()
                    logger.warning(f"Login required to apply for {job.job_id} at {job.company}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        status=JobStatus.NEEDS_MANUAL_INTERVENTION,
                        failure_reason="Naukri user session not logged in; login wall displayed",
                        error_code="LOGIN_REQUIRED",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 6: Dynamic Form Inspection & Truthful Answering
                # Inspect visible inputs
                form_inputs = page.locator("input[type='text'], input[type='number'], textarea")
                input_count = form_inputs.count()

                for i in range(input_count):
                    inp = form_inputs.nth(i)
                    if not inp.is_visible():
                        continue
                    label = inp.get_attribute("placeholder") or inp.get_attribute("name") or inp.get_attribute("aria-label") or ""
                    questions_detected.append({"index": i, "label": label})

                    ans_result = resolver.resolve_question(label)
                    if not ans_result.can_answer:
                        page.screenshot(path=evidence_path)
                        browser.close()
                        logger.warning(f"Unverified form question '{label}'. Stopping submission to prevent hallucination.")
                        return ApplicationRecord(
                            application_id=app_id,
                            job_id=job.job_id,
                            application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                            source_job_url=job.url,
                            canonical_job_url=canonical_url,
                            started_at=started_at,
                            status=JobStatus.NEEDS_MANUAL_INTERVENTION,
                            failure_reason=f"Unverified candidate question: '{label}'",
                            questions_detected=questions_detected,
                            evidence_path=evidence_path,
                            dry_run=False,
                        )

                    inp.fill(str(ans_result.answer_value))
                    questions_answered[label] = ans_result.answer_value

                # Step 7: File / Resume Upload if file input exists
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0 and Path(resume_docx_path).exists():
                    file_input.first.set_input_files(resume_docx_path)
                    time.sleep(1)

                # Step 8: Click Final Submit Button
                submit_btn = page.locator("button:has-text('Submit'), button:has-text('Apply Now'), button:has-text('Send Application')").first
                if submit_btn.is_visible():
                    submit_btn.click()
                    time.sleep(4)

                # Step 9: Verify Confirmation Evidence
                evidence = self.verifier.verify_submission(
                    page_content=page.content(),
                    final_url=page.url,
                    page_title=page.title(),
                )

                page.screenshot(path=evidence_path)
                browser.close()

                return ApplicationRecord(
                    application_id=app_id,
                    job_id=job.job_id,
                    application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                    source_job_url=job.url,
                    canonical_job_url=canonical_url,
                    started_at=started_at,
                    submitted_at=datetime.now(timezone.utc) if evidence.confirmed else None,
                    status=evidence.status,
                    confirmation_detected=evidence.confirmed,
                    confirmation_text=evidence.confirmation_text,
                    confirmation_reference=evidence.confirmation_reference,
                    final_url=evidence.final_url,
                    verification_method=evidence.verification_level,
                    questions_detected=questions_detected,
                    questions_answered=questions_answered,
                    evidence_path=evidence_path,
                    dry_run=False,
                )

        except Exception as exc:
            logger.error(f"Playwright workflow exception for {job.job_id}: {exc}")
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                status=JobStatus.APPLICATION_FAILED,
                failure_reason=f"Browser automation error: {str(exc)}",
                error_code="PLAYWRIGHT_ERROR",
                error_message=str(exc),
                dry_run=False,
            )
