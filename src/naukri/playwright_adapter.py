"""Playwright Browser Adapter implementing real-world job navigation, dynamic form answering, and confirmation verification."""

import os
import re
import uuid
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urlparse

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.naukri.url_validator import UrlValidator, UrlValidationResult
from src.naukri.verifier import ApplicationVerifier, VerificationEvidence
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.models.job import JobListing, JobStatus, ApplicationRecord, ApplicationMethod
from src.models.candidate import CandidateTruth
from src.utils.salary_parser import parse_salary
from src.utils.experience_parser import parse_experience
from src.utils.logger import get_logger

logger = get_logger("playwright_adapter")

EVIDENCE_DIR = Path("artifacts/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
AUTH_STATE_FILE = Path("artifacts/naukri_auth.json")


class PlaywrightBrowserAdapter(BaseNaukriClient):
    """Production Playwright adapter executing verified end-to-end applications."""

    def __init__(self, offline_mode: bool = False, headless: Optional[bool] = None, min_salary_lpa: float = 30.0):
        import sys
        self.offline_mode = offline_mode or os.environ.get("NAUKRI_MOCK", "0") == "1"
        if headless is not None:
            self.headless = headless
        else:
            # If a display server is present (e.g. DISPLAY=:99 via Xvfb or local GUI), run headed (headless=False)
            # because Akamai Bot Manager blocks headless Chromium with 403 Access Denied.
            has_display = "DISPLAY" in os.environ and bool(os.environ["DISPLAY"].strip())
            env_headless = os.environ.get("HEADLESS", "").lower() in ("true", "1", "yes")
            if has_display and not env_headless:
                self.headless = False
            else:
                is_linux_headless = (sys.platform != "win32") and not has_display
                self.headless = is_linux_headless or env_headless
        self.min_salary_lpa = min_salary_lpa
        self.url_validator = UrlValidator()
        self.verifier = ApplicationVerifier()

    def _prune_stale_auth_cookies(self):
        """Removes expired or IP-bound Akamai cookies from storage state to avoid 403 blocks."""
        if not AUTH_STATE_FILE.exists():
            return
        try:
            import json
            with open(AUTH_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            # Strip Akamai bot cookies that bind to specific IPs/sessions and cause 403 on new networks
            pruned = [
                c for c in cookies
                if c.get("name") not in ("ak_bmsc", "bm_sv", "bm_sz", "_abck")
            ]
            if len(pruned) != len(cookies):
                data["cookies"] = pruned
                with open(AUTH_STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Pruned {len(cookies) - len(pruned)} stale Akamai cookies from auth state.")
        except Exception as exc:
            logger.warning(f"Failed to prune auth state cookies: {exc}")

    def _launch_browser(self, p):
        """Launches Chromium or native Chrome with persistent state."""
        import sys

        self._prune_stale_auth_cookies()

        channel = "chrome" if (sys.platform == "win32" and not self.offline_mode) else None

        launch_kwargs = {
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider",
            ],
        }
        if channel:
            launch_kwargs["channel"] = channel

        browser = p.chromium.launch(**launch_kwargs)

        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            if sys.platform != "win32"
            else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )

        context_kwargs = {
            "user_agent": user_agent,
            "viewport": {"width": 1920, "height": 1080},
        }
        if AUTH_STATE_FILE.exists():
            context_kwargs["storage_state"] = str(AUTH_STATE_FILE)

        context = browser.new_context(**context_kwargs)

        # Inject anti-detection stealth script to mask webdriver
        stealth_script = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
        """
        context.add_init_script(stealth_script)

        return browser, context

    def _fetch_naukri_otp(self, start_time: float, timeout_sec: int = 60) -> Optional[str]:
        """Autonomously fetches 6-digit Naukri OTP from Gmail via IMAP if credentials are available."""
        import email
        import imaplib
        import re

        smtp_user = os.environ.get("SMTP_USERNAME")
        smtp_pass = os.environ.get("SMTP_PASSWORD")
        if not smtp_user or not smtp_pass:
            return None

        end_time = time.time() + timeout_sec
        while time.time() < end_time:
            try:
                mail = imaplib.IMAP4_SSL("imap.gmail.com")
                mail.login(smtp_user, smtp_pass)
                mail.select("inbox")
                status, messages = mail.search(None, '(FROM "naukri" SUBJECT "OTP")')
                msg_ids = messages[0].split()
                if msg_ids:
                    for mid in reversed(msg_ids[-5:]):
                        res, data = mail.fetch(mid, "(RFC822)")
                        for part in data:
                            if isinstance(part, tuple):
                                msg = email.message_from_bytes(part[1])
                                body = ""
                                for p in msg.walk():
                                    pl = p.get_payload(decode=True)
                                    if pl:
                                        body += " " + pl.decode(errors="ignore")
                                clean = " ".join(re.sub(r"<[^>]+>", " ", body).split())
                                m = re.search(r"enter below OTP.*?(\d{6})", clean, re.I)
                                if not m:
                                    m = re.search(r"valid for the next.*?(\d{6})", clean, re.I)
                                if not m:
                                    m = re.search(r"\b(\d{6})\b", clean)
                                if m:
                                    otp = m.group(1)
                                    mail.close()
                                    mail.logout()
                                    return otp
                mail.close()
                mail.logout()
            except Exception as e:
                logger.debug(f"IMAP poll error: {e}")
            time.sleep(3)
        return None

    def _ensure_authenticated(self, page, context) -> bool:
        """Ensures the browser session is authenticated on Naukri using user credentials or storage state."""
        try:
            # 1. Quick check: Already authenticated in current page DOM
            if page.locator(".nI-gNb-drawer, .view-profile-wrapper, .nI-gNb-header__wrapper").count() > 0:
                return True

            # 2. Check context cookies: if valid session token exists
            cookies = {c["name"]: c["value"] for c in context.cookies()}
            if "nauk_at" in cookies or (cookies.get("is_login") == "1" and "nauk_rt" in cookies):
                return True

            username = os.environ.get("NAUKRI_USERNAME", "sauravskt8@gmail.com")
            password = os.environ.get("NAUKRI_PASSWORD", "SS@19081992")

            logger.info(f"Ensuring authenticated Naukri session for {username}...")
            page.goto("https://www.naukri.com/nlogin/login", timeout=35000, wait_until="domcontentloaded")
            time.sleep(2)

            if "mnjuser" in page.url or page.locator(".nI-gNb-drawer, .view-profile-wrapper, .nI-gNb-header__wrapper").count() > 0:
                context.storage_state(path=str(AUTH_STATE_FILE))
                return True

            user_field = page.locator("#usernameField")
            pass_field = page.locator("#passwordField")
            if user_field.count() > 0 and pass_field.count() > 0:
                user_field.fill(username)
                pass_field.fill(password)
                time_before_click = time.time()
                login_btn = page.locator("button:has-text('Login'), button.blue-btn").first
                login_btn.click()
                time.sleep(4)

                # Check if OTP challenge is presented
                if page.locator("#Input_1").count() > 0 or page.locator("button.verify-button").count() > 0:
                    logger.info("Naukri OTP challenge detected. Retrieving verification code via IMAP...")
                    otp_code = self._fetch_naukri_otp(time_before_click, timeout_sec=60)
                    if otp_code:
                        logger.info("Retrieved OTP. Entering code into verification challenge...")
                        for i in range(1, 7):
                            digit = otp_code[i - 1]
                            inp = page.locator(f"#Input_{i}")
                            inp.click()
                            inp.fill(digit)
                            time.sleep(0.15)
                        time.sleep(1)
                        verify_btn = page.locator("button.verify-button, button:has-text('Verify')").first
                        if verify_btn.count() > 0:
                            verify_btn.click()
                            time.sleep(5)

                if "mnjuser" in page.url or page.locator(".nI-gNb-drawer, .view-profile-wrapper, .nI-gNb-header__wrapper").count() > 0:
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

                # Dismiss cookie consent banner if present
                try:
                    cookie_btn = page.locator("button:has-text('Got it')").first
                    if cookie_btn.is_visible(timeout=2000):
                        cookie_btn.click()
                except Exception:
                    pass

                # Wait for job tuples to attach to DOM
                try:
                    page.wait_for_selector("div.cust-job-tuple, div.srp-jobtuple, article", state="attached", timeout=12000)
                except Exception:
                    pass

                time.sleep(2)

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
                    exp_min, exp_max = parse_experience(raw_exp)

                    # Extract tags, description snippet, and full card text
                    tags_el = t.locator("ul.tags-gt li, ul.tags li, .tag-li, .dot-gt, [class*='tag']").all()
                    skills_found = [el.text_content().strip() for el in tags_el if el.text_content().strip()]

                    desc_el = t.locator("span.job-desc, div.job-desc, span.ni-job-tuple-icon-srp-description, div.row4, span.desc").first
                    desc_snippet = desc_el.text_content().strip() if desc_el.count() > 0 else ""
                    full_card_text = t.text_content().strip()

                    card_jd = f"{desc_snippet}\n{full_card_text}".strip() if (desc_snippet or full_card_text) else ""
                    has_full_jd = bool(len(card_jd) >= 50)

                    # Check if already applied directly on the search card tuple
                    is_card_applied = False
                    applied_badges = t.locator(".already-applied, .applied, span[class*='already-applied'], span[class*='applied'], span:has-text('Applied')").all()
                    for b in applied_badges:
                        b_txt = b.text_content().strip().lower()
                        if b_txt in ("applied", "already applied") or re.match(r"^applied\s+(\d+\s+days?\s+ago|today|yesterday|\d+\s+weeks?\s+ago)$", b_txt):
                            is_card_applied = True
                            break

                    listing = JobListing(
                        job_id=job_id,
                        title=title,
                        company=company,
                        location=location,
                        salary=parsed_salary,
                        experience_min=exp_min,
                        experience_max=exp_max,
                        experience_raw=raw_exp,
                        skills_found=skills_found,
                        jd_text=card_jd,
                        has_full_jd=has_full_jd,
                        url=url,
                        posted_date="Recent",
                        discovered_via_query=query,
                        source_query=query,
                        is_already_applied=is_card_applied,
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
        upload_file = resume_pdf_path if (resume_pdf_path and Path(resume_pdf_path).exists()) else resume_docx_path

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
                body_visible_text = page.locator("body").inner_text().lower() if page.locator("body").count() > 0 else ""

                # 2a. CAPTCHA / Bot Detection
                has_captcha = False
                if any(x in body_visible_text for x in ["verify you are human", "complete the security check to continue"]):
                    has_captcha = True
                elif page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], iframe[src*='turnstile'], .cf-turnstile").count() > 0:
                    has_captcha = True

                if has_captcha:
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

                # 2b. Visible OTP / MFA Challenge (Targeted phrases & inputs only; zero false-positive on scripts)
                otp_input = page.locator("input[name*='otp'], input[id*='otp'], input[placeholder*='otp'], .otp-container, .mfa-modal")
                mfa_phrases = ["enter otp", "enter the otp", "two-factor authentication", "2-factor authentication", "otp verification", "verify with otp"]
                has_mfa = False
                if otp_input.count() > 0 and otp_input.first.is_visible():
                    has_mfa = True
                elif any(phrase in body_visible_text for phrase in mfa_phrases) and "otp" in body_visible_text:
                    has_mfa = True

                if has_mfa:
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

                # 2c. Payment Walls
                if any(x in body_visible_text for x in ["payment required", "application fee", "membership required", "upgrade to apply"]):
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
                    logger.info(f"Job already applied previously: {job.title} @ {job.company}. Skipping re-apply.")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.NAUKRI_DIRECT.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        started_at=started_at,
                        submitted_at=started_at,
                        status=JobStatus.APPLIED,
                        confirmation_detected=False,
                        confirmation_text="Already applied in previous session",
                        confirmation_reference="ALREADY_APPLIED",
                        final_url=page.url,
                        verification_method="ALREADY_APPLIED_PREVIOUSLY",
                        evidence_path=evidence_path,
                        failure_reason="Already applied in previous session; skipped re-apply",
                        dry_run=False,
                    )

                # Step 4: Locate Primary Application Button on Naukri
                primary_apply = page.locator(
                    "button#apply-button, a#apply-button, "
                    "button.apply-button, a.apply-button, "
                    "[class*='styles_apply-button'], "
                    ".job-header button:has-text('Apply'), .job-header a:has-text('Apply'), "
                    ".apply-button-container button, .apply-button-container a, "
                    "button:has-text('Apply'), a.apply-button"
                ).first

                if not primary_apply.is_visible():
                    primary_apply = page.locator("button:has-text('Apply'), a:has-text('Apply')").first

                if not primary_apply.is_visible():
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

                # Check if the primary apply button is explicitly an external anchor pointing to non-Naukri domain
                primary_href = primary_apply.get_attribute("href")
                if primary_href and primary_href.startswith("http"):
                    parsed_href = urlparse(primary_href)
                    if parsed_href.netloc and not parsed_href.netloc.endswith("naukri.com"):
                        page.screenshot(path=evidence_path)
                        browser.close()
                        logger.info(f"Explicit external ATS link detected for {job.title} @ {job.company}: {primary_href}")
                        return ApplicationRecord(
                            application_id=app_id,
                            job_id=job.job_id,
                            application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
                            source_job_url=job.url,
                            canonical_job_url=canonical_url,
                            external_application_url=primary_href,
                            external_portal="External Career Portal",
                            started_at=started_at,
                            status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                            failure_reason="Application must be completed on external company career portal",
                            evidence_path=evidence_path,
                            dry_run=False,
                        )

                # Step 5: Click Apply Button on Naukri and monitor navigation
                new_page = None

                def _handle_popup(p):
                    nonlocal new_page
                    new_page = p

                page.on("popup", _handle_popup)

                try:
                    primary_apply.click(force=True, timeout=5000)
                except Exception:
                    try:
                        page.evaluate("(el) => el.click()", primary_apply.element_handle())
                    except Exception:
                        pass

                time.sleep(2)

                try:
                    page.remove_listener("popup", _handle_popup)
                except Exception:
                    pass

                # Check if navigation or popup led to an external ATS domain
                active_page = page
                if new_page:
                    active_page = new_page
                    try:
                        active_page.wait_for_load_state("domcontentloaded", timeout=10000)
                    except Exception:
                        pass

                current_nav_url = active_page.url
                parsed_nav = urlparse(current_nav_url)
                if parsed_nav.netloc and not parsed_nav.netloc.endswith("naukri.com"):
                    active_page.screenshot(path=evidence_path)
                    browser.close()
                    logger.info(f"Redirection to external ATS portal detected for {job.title} @ {job.company}: {current_nav_url}")
                    return ApplicationRecord(
                        application_id=app_id,
                        job_id=job.job_id,
                        application_method=ApplicationMethod.EXTERNAL_PORTAL.value,
                        source_job_url=job.url,
                        canonical_job_url=canonical_url,
                        external_application_url=current_nav_url,
                        external_portal="External Career Portal",
                        started_at=started_at,
                        status=JobStatus.EXTERNAL_APPLICATION_REQUIRED,
                        failure_reason="Application must be completed on external company career portal",
                        evidence_path=evidence_path,
                        dry_run=False,
                    )

                # Step 6: Handle Chatbot Recruiter Drawer if present
                drawer_selector = (
                    ".chatbot_Drawer, .chatbot_wrapper, [class*='chatbot_Drawer'], "
                    "[class*='chatbotWrapper'], .chat-drawer, div[class*='chatbot'], "
                    "[class*='chatbot-container'], .chat-container"
                )
                try:
                    page.wait_for_selector(drawer_selector, state="visible", timeout=3000)
                except Exception:
                    pass

                drawer = page.locator(drawer_selector).first
                chat_confirmed = False
                if drawer.is_visible():
                    logger.info("Chatbot recruiter drawer detected. Answering screening questions...")
                    chat_turns = 0
                    while chat_turns < 15:
                        chat_turns += 1
                        if not drawer.is_visible():
                            if questions_answered:
                                logger.info(f"Chatbot drawer closed after answering {len(questions_answered)} questions.")
                                chat_confirmed = True
                            break

                        drawer_text = drawer.inner_text().lower()
                        if any(c in drawer_text for c in [
                            "you have successfully applied",
                            "successfully applied",
                            "application has been sent",
                            "application sent to recruiter",
                            "your application is submitted",
                            "application submitted",
                            "applied successfully",
                            "we have received your application",
                            "profile has been shared",
                            "application completed",
                            "thank you for applying",
                            "thanks for applying",
                        ]):
                            logger.info("Confirmation text observed in chatbot drawer.")
                            chat_confirmed = True
                            break

                        page_text_lower = page.content().lower()
                        if any(c in page_text_lower for c in [
                            "applied to",
                            "you have successfully applied",
                            "successfully applied",
                            "application has been sent",
                            "saveapply"
                        ]):
                            logger.info("Confirmation text/URL observed on page during chatbot flow.")
                            chat_confirmed = True
                            break

                        bot_locator = drawer.locator(
                            ".botItem .botMsg span, .botMsg span, .bot-msg-item .question-header, "
                            "[class*='botMsg'] span, [class*='question'], .botItem span"
                        )
                        raw_texts = []
                        try:
                            raw_texts = bot_locator.all_text_contents()
                        except Exception:
                            pass

                        if not raw_texts:
                            try:
                                raw_texts = page.locator(".botItem .botMsg span, .botMsg span").all_text_contents()
                            except Exception:
                                pass

                        valid_bot_msgs = [
                            t.strip() for t in raw_texts
                            if t and t.strip() and t.strip() not in ["...", "typing", "• • •", "•••"]
                        ]
                        if not valid_bot_msgs:
                            time.sleep(2)
                            continue

                        latest_q = valid_bot_msgs[-1]

                        # If only greeting is visible so far, wait for question to render
                        if len(valid_bot_msgs) == 1 and ("thank you for showing interest" in latest_q.lower() or latest_q.lower().startswith("hi ")):
                            time.sleep(2)
                            continue

                        questions_detected.append({"turn": chat_turns, "question": latest_q})

                        if any(c in latest_q.lower() for c in ["successfully applied", "application sent", "applied to"]):
                            chat_confirmed = True
                            break

                        # If this question was already answered on a previous turn, wait for bot response
                        if latest_q in questions_answered:
                            logger.info(f"Question '{latest_q}' was already answered. Waiting for bot reply...")
                            time.sleep(3)
                            continue

                        # Check if recruiter specifically asks for resume / CV / document upload
                        if any(w in latest_q.lower() for w in ["resume", "cv", "upload", "attach"]):
                            drawer_file_input = drawer.locator("input[type='file']")
                            if drawer_file_input.count() > 0 and upload_file and Path(upload_file).exists():
                                try:
                                    drawer_file_input.first.set_input_files(str(upload_file))
                                    logger.info(f"Uploaded resume in chatbot drawer: {upload_file}")
                                    time.sleep(2)
                                    questions_answered[latest_q] = Path(upload_file).name

                                    # Confirm file upload by clicking Save / Send / Submit / Continue
                                    for btn_sel in [
                                        "button:has-text('Save')", ".save-btn", "button[class*='save']",
                                        "button:has-text('Submit')",
                                        "button:has-text('Continue')",
                                        "button:has-text('Send')",
                                        ".sendMsg", "div[id*='sendMsg']"
                                    ]:
                                        btn = drawer.locator(btn_sel).first
                                        if not btn.is_visible():
                                            btn = page.locator(btn_sel).first
                                        if btn.is_visible():
                                            try:
                                                btn.click(force=True, timeout=5000)
                                            except Exception:
                                                try:
                                                    page.evaluate("(el) => el.click()", btn.element_handle())
                                                except Exception:
                                                    pass
                                            break
                                    time.sleep(4)
                                    continue
                                except Exception:
                                    pass

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
                        logger.info(f"Chatbot question [Turn {chat_turns}]: '{latest_q}' -> Resolved Answer: '{ans_val_str}'")

                        # Check if a chip / radio option matching the resolved answer is available
                        matching_chip = None
                        is_affirmative = ans_val_lower in ["yes", "true"]
                        is_negative = ans_val_lower in ["no", "false"]

                        if is_affirmative:
                            for sel in [
                                "xpath=.//*[translate(normalize-space(.), 'yes', 'YES')='YES']",
                                "xpath=.//*[translate(normalize-space(.), 'true', 'TRUE')='TRUE']",
                                ":text-is('Yes')", ":text-is('YES')",
                                "button:has-text('Yes')", "span:has-text('Yes')", "div:has-text('Yes')", "label:has-text('Yes')"
                            ]:
                                c = drawer.locator(sel).first
                                if c.is_visible():
                                    try:
                                        c_text = (c.text_content(timeout=1000) or "").strip()
                                        if c_text.lower() in ("yes", "true", "y"):
                                            matching_chip = c
                                            break
                                    except Exception:
                                        pass

                        if not matching_chip and is_negative:
                            for sel in [
                                "xpath=.//*[translate(normalize-space(.), 'no', 'NO')='NO']",
                                "xpath=.//*[translate(normalize-space(.), 'false', 'FALSE')='FALSE']",
                                ":text-is('No')", ":text-is('NO')",
                                "button:has-text('No')", "span:has-text('No')", "div:has-text('No')", "label:has-text('No')"
                            ]:
                                c = drawer.locator(sel).first
                                if c.is_visible():
                                    try:
                                        c_text = (c.text_content(timeout=1000) or "").strip()
                                        if c_text.lower() in ("no", "false", "n"):
                                            matching_chip = c
                                            break
                                    except Exception:
                                        pass

                        if not matching_chip:
                            for sel in [
                                f":text-is('{ans_val_str}')",
                                f":text-is('{ans_val_str}%')",
                                f":text-is('{ans_val_str} %')",
                                f"xpath=.//*[normalize-space(.)='{ans_val_str}']",
                                f"button:has-text('{ans_val_str}%')",
                                f"span:has-text('{ans_val_str}%')",
                                f"label:has-text('{ans_val_str}%')",
                                f"div:has-text('{ans_val_str}%')",
                                f"button:has-text('{ans_val_str}')",
                                f"span:has-text('{ans_val_str}')",
                                f"label:has-text('{ans_val_str}')"
                            ]:
                                c = drawer.locator(sel).first
                                if c.is_visible():
                                    try:
                                        c_text = (c.text_content(timeout=1000) or "").strip()
                                        if c_text in (ans_val_str, f"{ans_val_str}%", f"{ans_val_str} %"):
                                            matching_chip = c
                                            break
                                    except Exception:
                                        pass

                        # Percentage, Range, or Threshold Matching for numeric/percentage values
                        is_numeric_val = False
                        numeric_val = 0.0
                        try:
                            numeric_val = float(ans_val_str.replace('%', '').strip())
                            is_numeric_val = True
                        except ValueError:
                            pass

                        if not matching_chip and is_numeric_val:
                            try:
                                cand_locators = drawer.locator(
                                    "label, button, a, [role='button'], [role='radio'], "
                                    "[class*='chip'], [class*='option'], [class*='radio'], [class*='pill'], "
                                    "[class*='choice'], [class*='reply'], [class*='answer'], [class*='bubble'], "
                                    "[class*='item'], li, span, div"
                                ).all()
                                for cand in cand_locators:
                                    if not cand.is_visible():
                                        continue
                                    cand_text = (cand.text_content(timeout=500) or "").strip().lower()
                                    if not cand_text or cand_text in ["save", "submit", "continue", "next", "send", "apply"]:
                                        continue

                                    # Check for range: e.g. "60-70%", "70 - 80%", "10-15 years"
                                    range_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|\s)*(?:-|to)\s*(\d+(?:\.\d+)?)\s*%?", cand_text)
                                    if range_match:
                                        low = float(range_match.group(1))
                                        high = float(range_match.group(2))
                                        if low <= numeric_val <= high:
                                            matching_chip = cand
                                            break

                                    # Check for threshold: e.g. "60% & above", "70% and above", "above 60%", "60+%"
                                    thresh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|\s)*(?:\+|and above|& above|above|or more|more)", cand_text)
                                    if thresh_match:
                                        thresh = float(thresh_match.group(1))
                                        if numeric_val >= thresh:
                                            matching_chip = cand
                                            break
                            except Exception:
                                pass

                        if matching_chip:
                            chip_text = ""
                            try:
                                chip_text = (matching_chip.text_content(timeout=500) or "").strip()
                            except Exception:
                                pass
                            logger.info(f"Chatbot Turn {chat_turns}: Selecting matching chip '{chip_text}' for question '{latest_q}'")
                            try:
                                matching_chip.click(force=True, timeout=5000)
                            except Exception:
                                try:
                                    page.evaluate("(el) => el.click()", matching_chip.element_handle())
                                except Exception:
                                    pass
                            try:
                                radio_inp = matching_chip.locator("input[type='radio'], input[type='checkbox']").first
                                if radio_inp.count() > 0:
                                    radio_inp.check(force=True, timeout=2000)
                            except Exception:
                                pass
                            time.sleep(1)
                            # Confirm or submit choice if a button is presented
                            for btn_sel in [
                                "button:has-text('Save')", ".save-btn", "button[class*='save']",
                                "button:has-text('Submit')",
                                "button:has-text('Continue')",
                                "button:has-text('Next')",
                                "button:has-text('Send')",
                                ".sendMsg", "div[id*='sendMsg']"
                            ]:
                                cb = drawer.locator(btn_sel).first
                                if not cb.is_visible():
                                    cb = page.locator(btn_sel).first
                                if cb.is_visible():
                                    try:
                                        cb.click(force=True, timeout=5000)
                                    except Exception:
                                        try:
                                            page.evaluate("(el) => el.click()", cb.element_handle())
                                        except Exception:
                                            pass
                                    break
                            questions_answered[latest_q] = ans_val_str
                            time.sleep(4)
                            continue

                        # Text input inside chatbot drawer
                        chat_input = drawer.locator(
                            "input[placeholder*='Type message'], "
                            "input[placeholder*='message'], "
                            "input[type='text'], "
                            "input[type='number'], "
                            "textarea, "
                            ".textArea[contenteditable='true'], "
                            "[contenteditable='true'], "
                            "div[role='textbox'], "
                            "input:not([type='file']):not([type='radio']):not([type='checkbox'])"
                        ).first

                        if not chat_input.is_visible():
                            chat_input = page.locator(
                                "input[placeholder*='Type message'], "
                                "input[placeholder*='message'], "
                                "input[type='text'], "
                                "input[type='number'], "
                                "textarea, "
                                ".textArea[contenteditable='true'], "
                                "[contenteditable='true'], "
                                "div[role='textbox'], "
                                "input:not([type='file']):not([type='radio']):not([type='checkbox'])"
                            ).first

                        if not chat_input.is_visible():
                            if chat_turns % 3 == 0:
                                try:
                                    vis_opts = [c.text_content().strip() for c in drawer.locator("button, [class*='chip'], [class*='option'], label, li, span").all()[:8] if (c.text_content() or '').strip()]
                                    logger.warning(
                                        f"Chatbot question [Turn {chat_turns}]: '{latest_q}' has no matching option or visible input. "
                                        f"Resolved answer: '{ans_val_str}'. Visible options: {vis_opts}"
                                    )
                                except Exception:
                                    pass
                            time.sleep(2)
                            continue

                        try:
                            chat_input.click(force=True, timeout=5000)
                        except Exception:
                            try:
                                page.evaluate("(el) => el.click()", chat_input.element_handle())
                            except Exception:
                                pass
                        time.sleep(0.5)

                        try:
                            chat_input.fill(ans_val_str)
                        except Exception:
                            try:
                                chat_input.click()
                                page.keyboard.type(ans_val_str)
                            except Exception:
                                pass

                        try:
                            page.keyboard.press("Space")
                            page.keyboard.press("Backspace")
                        except Exception:
                            pass

                        time.sleep(0.5)
                        questions_answered[latest_q] = ans_val_str

                        save_or_send = drawer.locator(
                            "button:has-text('Save'), .save-btn, button[class*='save'], "
                            ".sendMsg, div[id*='sendMsg'], button:has-text('Send'), button:has-text('Submit'), button:has-text('Continue')"
                        ).first
                        if not save_or_send.is_visible():
                            save_or_send = page.locator("button:has-text('Save'), .save-btn, button[class*='save'], .sendMsg, button:has-text('Send')").first
                        if save_or_send.is_visible():
                            try:
                                save_or_send.click(force=True, timeout=5000)
                            except Exception:
                                try:
                                    page.evaluate("(el) => el.click()", save_or_send.element_handle())
                                except Exception:
                                    pass
                        else:
                            chat_input.press("Enter")
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

                submit_selectors = [
                    "button:has-text('Submit Application')", "button:has-text('Apply Now')",
                    "button:has-text('Send Application')", "button:has-text('Save & Apply')",
                    "button:has-text('Apply with Naukri profile')", "button:has-text('Apply')",
                    "button:has-text('Submit')", "button:has-text('Confirm')", "button:has-text('Continue')",
                    "button:has-text('Done')", "button:has-text('Finish')", "button:has-text('Proceed')",
                    ".save-btn", ".submit-btn", ".apply-btn", "button.blue-btn", "button[type='submit']"
                ]
                submit_btn = None
                if drawer.is_visible():
                    for sel in submit_selectors:
                        btn = drawer.locator(sel).first
                        if btn.is_visible():
                            submit_btn = btn
                            break

                if not submit_btn:
                    for sel in [
                        ".modal button:has-text('Submit')", "[class*='modal'] button:has-text('Apply')",
                        "button:has-text('Submit Application')", "button:has-text('Send Application')",
                        "button:has-text('Save & Apply')", "button:has-text('Apply with Naukri profile')",
                        "button:has-text('Apply')", "button:has-text('Confirm')",
                        "[class*='applyModal'] button", "[class*='apply-modal'] button",
                        "[class*='applyDrawer'] button", ".apply-message-container button",
                        "button.apply-button", "button.blue-btn", "button[type='submit']"
                    ]:
                        btn = page.locator(sel).first
                        if btn.is_visible():
                            submit_btn = btn
                            break

                if submit_btn and submit_btn.is_visible():
                    try:
                        btn_txt = (submit_btn.text_content() or "").strip()
                        logger.info(f"Clicking application submit button: '{btn_txt}'")
                        submit_btn.click(force=True, timeout=5000)
                    except Exception:
                        try:
                            page.evaluate("(el) => el.click()", submit_btn.element_handle())
                        except Exception:
                            pass
                    time.sleep(5)

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

                applied_badge = page.locator(
                    ".already-applied, span.already-applied, span[class*='already-applied'], "
                    "button.applied-btn, button[class*='already-applied'], "
                    "button:has-text('Already Applied'), button:has-text('Applied')"
                )
                badge_confirmed = False
                if applied_badge.count() > 0:
                    for ab in applied_badge.all():
                        if ab.is_visible():
                            badge_text = ab.inner_text().strip().lower()
                            if badge_text in ["applied", "already applied"] or "applied" in badge_text:
                                badge_confirmed = True
                                break

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
                elif chat_confirmed:
                    evidence = VerificationEvidence(
                        confirmed=True,
                        status=JobStatus.APPLIED_CONFIRMED,
                        verification_level="LEVEL_1_DIRECT_MODAL",
                        confirmation_text="Chatbot recruiter application completed successfully",
                        confirmation_reference="CHATBOT_CONFIRMED",
                        final_url=page.url,
                        evidence_summary="Recruiter chatbot drawer completed all questionnaire turns with confirmed submission.",
                    )
                elif intermediate_evidence.confirmed or "saveapply" in initial_url.lower() or any(c in initial_page_content.lower() for c in ["applied to", "application sent", "successfully applied"]):
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
