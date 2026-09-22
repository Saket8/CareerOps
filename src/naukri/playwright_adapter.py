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
AUTH_STATE_FILE = Path("artifacts/naukri_auth.json")


class PlaywrightBrowserAdapter(BaseNaukriClient):
    """Production Playwright adapter executing verified end-to-end applications."""

    def __init__(self, offline_mode: bool = False, headless: bool = False, min_salary_lpa: float = 30.0):
        self.offline_mode = offline_mode or os.environ.get("NAUKRI_MOCK", "0") == "1"
        self.headless = headless
        self.min_salary_lpa = min_salary_lpa
        self.url_validator = UrlValidator()
        self.verifier = ApplicationVerifier()

    def _launch_browser(self, p):
        """Launches Chromium or native Chrome with persistent state."""
        import sys

        channel = "chrome" if (sys.platform == "win32" and not self.offline_mode) else None

        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel

        browser = p.chromium.launch(**launch_kwargs)

        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "viewport": {"width": 1280, "height": 800},
        }
        if AUTH_STATE_FILE.exists():
            context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

        context = browser.new_context(**context_kwargs)
        return browser, context

    def _ensure_authenticated(self, page, context) -> bool:
        """Ensures the browser session is authenticated on Naukri using user credentials."""
        try:
            if page.locator(".nI-gNb-drawer, .view-profile-wrapper").count() > 0:
                return True

            username = os.environ.get("NAUKRI_USERNAME", "sauravskt8@gmail.com")
            password = os.environ.get("NAUKRI_PASSWORD", "SS@19081992")

            logger.info(f"Ensuring authenticated Naukri session for {username}...")
            page.goto("https://www.naukri.com/nlogin/login", timeout=35000, wait_until="domcontentloaded")
            time.sleep(2)

            if "mnjuser" in page.url or page.locator(".nI-gNb-drawer, .view-profile-wrapper").count() > 0:
                context.storage_state(path=str(AUTH_STATE_FILE))
                return True

            user_field = page.locator("#usernameField")
            pass_field = page.locator("#passwordField")
            if user_field.count() > 0 and pass_field.count() > 0:
                user_field.fill(username)
                pass_field.fill(password)
                login_btn = page.locator("button:has-text('Login'), button.blue-btn").first
                login_btn.click()
                time.sleep(5)

                if "mnjuser" in page.url or page.locator(".nI-gNb-drawer, .view-profile-wrapper").count() > 0:
                    context.storage_state(path=str(AUTH_STATE_FILE))
                    logger.info("Authentication successful; session saved to storage.")
                    return True

            return False
        except Exception as exc:
            logger.warning(f"Session authentication check encountered exception: {exc}")
            return False

    def search_jobs(
        self,
        query: str,
        locations: Optional[List[str]] = None,
        experience_min: Optional[int] = None,
        experience_max: Optional[int] = None,
        limit: int = 25,
    ) -> List[JobListing]:
        """Discovers jobs via live browser session or fallback market intelligence."""
        if self.offline_mode:
            from src.naukri.browser_adapter import NaukriBrowserAdapter
            adapter = NaukriBrowserAdapter(offline_mode=True)
            return adapter.search_jobs(query, locations, experience_min, experience_max, limit)

        from playwright.sync_api import sync_playwright
        formatted_query = query.replace(" ", "-").lower()
        search_url = f"https://www.naukri.com/{formatted_query}-jobs"
        logger.info(f"Executing live search for '{query}' on {search_url}")

        try:
            with sync_playwright() as p:
                browser, context = self._launch_browser(p)
                page = context.new_page()
                page.goto(search_url, timeout=35000, wait_until="domcontentloaded")
                time.sleep(3)

                tuples = page.locator("div.cust-job-tuple, div.srp-jobtuple").all()
                listings = []
                for t in tuples[:limit]:
                    title_el = t.locator("a.title").first
                    comp_el = t.locator("a.comp-name").first
                    loc_el = t.locator("span.loc-wrap, span.loc").first
                    sal_el = t.locator("span.sal-wrap, span.sal").first
                    exp_el = t.locator("span.exp-wrap, span.exp").first

                    if title_el.count() == 0:
                        continue

                    title = title_el.text_content().strip()
                    url = title_el.get_attribute("href") or ""
                    if not url or url == "None":
                        continue

                    company = comp_el.text_content().strip() if comp_el.count() > 0 else "Unknown Company"
                    location = loc_el.text_content().strip() if loc_el.count() > 0 else (locations[0] if locations else "India")
                    raw_sal = sal_el.text_content().strip() if sal_el.count() > 0 else "Not Disclosed"
                    raw_exp = exp_el.text_content().strip() if exp_el.count() > 0 else ""

                    job_id_match = re.search(r"-(\d{6,})", url)
                    job_id = job_id_match.group(1) if job_id_match else f"nk_{abs(hash(url))}"

                    parsed_salary = parse_salary(raw_sal, min_threshold_lpa=self.min_salary_lpa)

                    # Extract tags, description snippet, and full card text
                    tags_el = t.locator("ul.tags-gt li, ul.tags li, .tag-li, .dot-gt, [class*='tag']").all()
                    skills_found = [el.text_content().strip() for el in tags_el if el.text_content().strip()]

                    desc_el = t.locator("span.job-desc, div.job-desc, span.ni-job-tuple-icon-srp-description, div.row4, span.desc").first
                    desc_snippet = desc_el.text_content().strip() if desc_el.count() > 0 else ""
                    full_card_text = t.text_content().strip()

                    listing = JobListing(
                        job_id=job_id,
                        title=title,
                        company=company,
                        location=location,
                        salary=parsed_salary,
                        experience_required=raw_exp,
                        skills_found=skills_found,
                        description_raw=full_card_text,
                        description_cleaned=desc_snippet or full_card_text,
                        url=url,
                        posted_date="Recent",
                        discovered_via_query=query,
                    )
                    listings.append(listing)

                browser.close()
                if listings:
                    logger.info(f"Live search found {len(listings)} listings on {search_url}")
                    return listings
        except Exception as exc:
            logger.warning(f"Live search encountered error on {search_url}: {exc}")
            return []

        return []

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
        dry_run: bool = False,
    ) -> ApplicationRecord:
        """Executes full verified application workflow via Playwright or offline test verifier."""
        app_id = f"app_{job.job_id}_{int(datetime.now(timezone.utc).timestamp())}"
        started_at = datetime.now(timezone.utc)
        evidence_path = str(EVIDENCE_DIR / f"{job.job_id}_already_applied.png")

        # 1. URL Pre-Flight Validation
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

        # 2. DRY RUN MODE (Zero dummy apply policy enforced)
        if dry_run:
            logger.info(
                f"[DRY_RUN] Application prepared for {job.job_id} ({job.title} @ {job.company}), "
                f"but live submission skipped per zero-dummy-apply policy."
            )
            resolver = CandidateAnswerResolver(candidate_truth)
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                submitted_at=None,
                status=JobStatus.APPLICATION_READY,
                confirmation_detected=False,
                confirmation_text=None,
                confirmation_reference=None,
                final_url=canonical_url,
                verification_method="DRY_RUN_PREPARED",
                questions_answered=resolver.verified_facts,
                dry_run=True,
                failure_reason="Dry run mode active: Live submission skipped. Zero dummy apply policy enforced.",
            )

        # 3. OFFLINE MODE (No network access, live browser submission unavailable)
        if self.offline_mode:
            logger.info(
                f"[OFFLINE_MODE] Offline mode active for {job.job_id}: "
                f"Live browser submission unavailable. Zero dummy apply policy enforced."
            )
            resolver = CandidateAnswerResolver(candidate_truth)
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                source_job_url=job.url,
                canonical_job_url=canonical_url,
                started_at=started_at,
                submitted_at=None,
                status=JobStatus.APPLICATION_READY,
                confirmation_detected=False,
                confirmation_text=None,
                confirmation_reference=None,
                final_url=canonical_url,
                verification_method="OFFLINE_MODE_SKIPPED",
                questions_answered=resolver.verified_facts,
                dry_run=False,
                failure_reason="Offline mode active: Live browser submission unavailable. Zero dummy apply policy enforced.",
            )

        # 4. REAL LIVE PLAYWRIGHT EXECUTION
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
        """Launches Playwright, authenticates session, navigates, answers forms, submits, and verifies 'Already Applied' badge."""
        from playwright.sync_api import sync_playwright

        resolver = CandidateAnswerResolver(candidate_truth)
        questions_detected = []
        questions_answered = {}

        try:
            with sync_playwright() as p:
                browser, context = self._launch_browser(p)
                page = context.new_page()

                # Step 1: Open Job Page
                logger.info(f"Navigating to job URL: {canonical_url}")
                page.goto(canonical_url, timeout=35000, wait_until="domcontentloaded")
                time.sleep(2)

                # Ensure session is authenticated (Fail-Closed Gate)
                if not self.offline_mode:
                    is_auth = self._ensure_authenticated(page, context)
                    if not is_auth:
                        page.screenshot(path=evidence_path)
                        browser.close()
                        logger.error(f"Authentication failed for {canonical_url}: Unable to establish valid logged-in Naukri session.")
                        return ApplicationRecord(
                            application_id=app_id,
                            job_id=job.job_id,
                            application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                            source_job_url=job.url,
                            canonical_job_url=canonical_url,
                            started_at=started_at,
                            status=JobStatus.APPLICATION_BLOCKED,
                            failure_reason="Authentication failed: valid Naukri session could not be established (Fail-Closed Safety Gate)",
                            error_code="AUTH_REQUIRED",
                            evidence_path=evidence_path,
                            dry_run=False,
                        )
                    if canonical_url not in page.url:
                        page.goto(canonical_url, timeout=35000, wait_until="domcontentloaded")
                        time.sleep(2)

                # Step 2: Check for Anti-Automation Challenges & Safety Barriers (Fail-Closed)
                page_text = page.content().lower()
                if any(x in page_text for x in ["recaptcha", "cf-turnstile", "verify you are human", "hcaptcha", "g-recaptcha"]):
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

                if any(x in page_text for x in ["otp verification", "enter otp", "enter the otp", "two-factor authentication", "mfa"]):
                    page.screenshot(path=evidence_path)
                    browser.close()
                    logger.warning(f"MFA/OTP barrier detected on {canonical_url}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        status=JobStatus.NEEDS_MANUAL_INTERVENTION,
                        failure_reason="MFA/OTP challenge detected; manual candidate verification required",
                        error_code="MFA_REQUIRED",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                if any(x in page_text for x in ["payment required", "application fee", "membership required", "upgrade to apply"]):
                    page.screenshot(path=evidence_path)
                    browser.close()
                    logger.warning(f"Payment barrier detected on {canonical_url}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        status=JobStatus.APPLICATION_BLOCKED,
                        failure_reason="Payment wall encountered; free application invariant enforced",
                        error_code="PAYMENT_REQUIRED",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 3: Check if already applied (Green badge .already-applied)
                applied_badge = page.locator(".already-applied, span.already-applied, span[class*='already-applied']")
                is_already_applied = False
                if applied_badge.count() > 0:
                    badge_text = applied_badge.first.inner_text().strip().lower()
                    if badge_text in ["applied", "already applied"]:
                        is_already_applied = True

                if is_already_applied:
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
                        confirmation_text="Applied state confirmed on listing with badge",
                        confirmation_reference="ALREADY_APPLIED",
                        final_url=page.url,
                        verification_method="LEVEL_3_BUTTON_ALREADY_APPLIED",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 4: Detect Application Type (Direct vs External ATS)
                external_button = page.locator(
                    "a:has-text('Apply on company site'), a:has-text('Apply on company website'), "
                    "a:has-text('Apply on Employer Site'), button:has-text('Apply on company site')"
                )
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

                # Step 5: Click Apply Button on Naukri
                apply_button = page.locator("button:has-text('Apply'), a.apply-button").first
                if not apply_button.is_visible():
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
                        failure_reason="Apply button not found or listing does not accept applications",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                apply_button.click()
                time.sleep(3)

                # Step 6: Handle Chatbot Recruiter Drawer if present
                drawer = page.locator(".chatbot_Drawer")
                if drawer.is_visible():
                    logger.info("Chatbot recruiter drawer detected. Answering screening questions...")
                    chat_turns = 0
                    while chat_turns < 10:
                        chat_turns += 1
                        if not drawer.is_visible():
                            break

                        drawer_text = drawer.inner_text().lower()
                        if any(c in drawer_text for c in ["applied to", "successfully applied", "application sent"]):
                            logger.info("Confirmation text observed in chatbot drawer.")
                            break

                        bot_msgs = page.locator(".botItem .botMsg span, .botMsg span").all()
                        if not bot_msgs:
                            time.sleep(2)
                            continue

                        latest_q = bot_msgs[-1].text_content().strip()
                        questions_detected.append({"turn": chat_turns, "question": latest_q})

                        if any(c in latest_q.lower() for c in ["successfully applied", "application sent", "applied to"]):
                            break

                        # Resolve question strictly against candidate truth layer (Finding 4)
                        ans_res = resolver.resolve_question(latest_q)
                        if not ans_res.can_answer:
                            page.screenshot(path=evidence_path)
                            browser.close()
                            logger.warning(f"Unverified candidate question in chat: '{latest_q}'. Stopping to prevent hallucination.")
                            return ApplicationRecord(
                                application_id=app_id,
                                job_id=job.job_id,
                                application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                                source_job_url=job.url,
                                canonical_job_url=canonical_url,
                                started_at=started_at,
                                status=JobStatus.NEEDS_MANUAL_INTERVENTION,
                                failure_reason=f"Unverified candidate question in screening chat: '{latest_q}'",
                                questions_detected=questions_detected,
                                evidence_path=evidence_path,
                                dry_run=False,
                            )

                        ans_val_str = str(ans_res.answer_value).strip()
                        ans_val_lower = ans_val_str.lower()
                        text_area = page.locator(".textArea[contenteditable='true']").first

                        # Check if a chip / radio option matching the resolved answer is available
                        matching_chip = None
                        if ans_val_lower in ["yes", "true"]:
                            chip = drawer.locator("xpath=.//*[normalize-space(translate(text(), 'yes', 'YES'))='YES']").first
                            if chip.is_visible():
                                matching_chip = chip
                        elif ans_val_lower in ["no", "false"]:
                            chip = drawer.locator("xpath=.//*[normalize-space(translate(text(), 'no', 'NO'))='NO']").first
                            if chip.is_visible():
                                matching_chip = chip
                        else:
                            chip = drawer.locator(f"xpath=.//*[normalize-space(text())='{ans_val_str}']").first
                            if chip.is_visible():
                                matching_chip = chip

                        if matching_chip:
                            matching_chip.click()
                            time.sleep(1)
                            save_btn = drawer.locator("xpath=.//*[normalize-space(text())='Save']").all()
                            for sb in save_btn:
                                if sb.is_visible():
                                    sb.click()
                                    break
                            questions_answered[latest_q] = ans_val_str
                            time.sleep(4)
                            continue

                        if not text_area.is_visible():
                            time.sleep(2)
                            continue

                        text_area.click()
                        time.sleep(0.5)
                        text_area.fill(ans_val_str)
                        time.sleep(0.5)
                        questions_answered[latest_q] = ans_val_str

                        send_btn = page.locator(".sendMsg, div[id*='sendMsg']").first
                        if send_btn.is_visible():
                            send_btn.click()
                        else:
                            text_area.press("Enter")
                        time.sleep(4)

                # Step 7: Handle dynamic form inputs if standard modal is displayed
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

                # Upload tailored PDF (configured and validated format per Finding 8)
                upload_file = resume_pdf_path if (resume_pdf_path and Path(resume_pdf_path).exists()) else resume_docx_path
                file_input = page.locator("input[type='file']")
                if file_input.count() > 0 and upload_file and Path(upload_file).exists():
                    file_input.first.set_input_files(str(upload_file))
                    logger.info(f"Uploaded tailored resume ({Path(upload_file).suffix.upper()}) to application form: {upload_file}")
                    time.sleep(2)

                submit_btn = page.locator("button:has-text('Submit'), button:has-text('Apply Now'), button:has-text('Send Application')").first
                if submit_btn.is_visible():
                    submit_btn.click()
                    time.sleep(4)

                # Step 8: Verify Confirmation Evidence via Mandatory Canonical Reload (Finding 1)
                time.sleep(2)
                initial_page_content = page.content()
                initial_url = page.url
                intermediate_evidence = self.verifier.verify_submission(
                    page_content=initial_page_content,
                    final_url=initial_url,
                    page_title=page.title(),
                )

                # Mandatory post-submit reload of canonical listing to assert live green badge
                logger.info(f"Reloading canonical job listing to assert green applied badge: {canonical_url}")
                page.goto(canonical_url, timeout=35000, wait_until="networkidle")
                time.sleep(2)

                applied_badge = page.locator(".already-applied, span.already-applied, span[class*='already-applied']")
                badge_confirmed = False
                if applied_badge.count() > 0:
                    badge_text = applied_badge.first.inner_text().strip().lower()
                    if badge_text in ["applied", "already applied"]:
                        badge_confirmed = True

                if badge_confirmed:
                    evidence = VerificationEvidence(
                        confirmed=True,
                        status=JobStatus.APPLIED_CONFIRMED,
                        verification_level="LEVEL_3_BUTTON_ALREADY_APPLIED",
                        confirmation_text="Applied badge confirmed on listing",
                        confirmation_reference="ALREADY_APPLIED",
                        final_url=page.url,
                        evidence_summary="Mandatory reload confirms official green '.already-applied' badge.",
                    )
                elif intermediate_evidence.confirmed or "saveapply" in initial_url.lower() or "applied to" in initial_page_content.lower():
                    # Weaker transient signal without reloaded badge -> SUBMISSION_UNVERIFIED
                    logger.warning(f"Submission had transient confirmation cues but green badge was not asserted on reload for {job.job_id}")
                    evidence = VerificationEvidence(
                        confirmed=False,
                        status=JobStatus.SUBMISSION_UNVERIFIED,
                        verification_level="SUBMISSION_UNVERIFIED",
                        confirmation_text="Transient confirmation detected without reloaded badge assertion",
                        confirmation_reference=intermediate_evidence.confirmation_reference or "TRANSIENT_CONFIRMATION",
                        final_url=page.url,
                        evidence_summary="Transient apply cues detected, but green badge was absent on post-submit reload.",
                    )
                else:
                    evidence = VerificationEvidence(
                        confirmed=False,
                        status=JobStatus.APPLICATION_FAILED,
                        verification_level="UNVERIFIED",
                        confirmation_text=None,
                        confirmation_reference=None,
                        final_url=page.url,
                        evidence_summary="Submission could not be confirmed on reload.",
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
