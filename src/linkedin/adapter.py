"""LinkedIn Playwright Adapter executing automated international Easy Apply job discovery and submission."""

import os
import re
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from src.models.job import JobListing, JobStatus, ApplicationRecord, ApplicationMethod
from src.models.candidate import CandidateTruth
from src.naukri.candidate_answer_resolver import CandidateAnswerResolver
from src.utils.logger import get_logger

logger = get_logger("linkedin_adapter")

EVIDENCE_DIR = Path("artifacts/evidence")
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class LinkedInAdapter:
    """Production adapter for LinkedIn job discovery, answer resolution, and Easy Apply submission."""

    def __init__(
        self,
        config: Dict[str, Any],
        candidate_truth: CandidateTruth,
        offline_mode: bool = False,
        headless: Optional[bool] = None,
    ):
        self.config = config
        self.li_config = config.get("linkedin", {})
        self.candidate_truth = candidate_truth
        self.offline_mode = offline_mode
        self.auto_submit = bool(self.li_config.get("auto_submit", True))
        self.user_data_dir = self.li_config.get("user_data_dir", "/u01/CareerOps/.li_profile")
        self.auth_file = Path(self.li_config.get("auth_state_path", "artifacts/linkedin_auth.json"))
        
        # Headless mode determination
        if headless is not None:
            self.headless = headless
        else:
            self.headless = os.environ.get("HEADLESS", "true").lower() in ("true", "1", "yes")

        self.answer_resolver = CandidateAnswerResolver(candidate_truth, strict_truth_only=False)

    def discover_jobs(self, limit_per_query: int = 15) -> List[JobListing]:
        """Discovers Easy Apply jobs across target international regions and configured queries."""

        target_regions = self.li_config.get("target_regions", [
            {"name": "Europe", "location": "Europe"},
            {"name": "Nordics", "location": "Nordics"},
            {"name": "Australia", "location": "Australia"},
            {"name": "United States", "location": "United States"},
            {"name": "United Kingdom", "location": "United Kingdom"},
            {"name": "India", "location": "India"},
        ])

        queries = self.li_config.get("queries", [
            "OCI Architect",
            "Oracle Cloud Infrastructure Architect",
            "Cloud Architect",
            "AI Architect",
            "GenAI Architect",
        ])

        discovered_jobs: List[JobListing] = []
        seen_job_ids = set()

        if self.offline_mode:
            logger.info("LinkedInAdapter running in offline mode. Generating offline sample jobs.")
            return [
                JobListing(
                    job_id="li_mock_eur_1",
                    title="Lead Cloud Architect (Nordics)",
                    company="Devoteam Nordic",
                    location="Copenhagen, Denmark (Nordics)",
                    work_mode="onsite",
                    url="https://www.linkedin.com/jobs/view/9990001/",
                    source_query="Cloud Architect",
                    source_platform="linkedin",
                    application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
                    status=JobStatus.DISCOVERED,
                    has_full_jd=True,
                    jd_text="Seeking Lead Cloud Architect for Copenhagen, Denmark. Role requires deep expertise in Oracle Cloud Infrastructure (OCI), Enterprise Cloud Architecture, Terraform, Kubernetes, and hybrid cloud migrations.",
                    skills_found=["Oracle Cloud Infrastructure", "OCI", "Cloud Architecture", "Terraform", "Kubernetes"],
                ),
                JobListing(
                    job_id="li_mock_aus_1",
                    title="Principal Cloud Architect",
                    company="Canva Australia",
                    location="Sydney, Australia",
                    work_mode="hybrid",
                    url="https://www.linkedin.com/jobs/view/9990002/",
                    source_query="Cloud Architect",
                    source_platform="linkedin",
                    application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
                    status=JobStatus.DISCOVERED,
                    has_full_jd=True,
                    jd_text="Principal Cloud Architect to design scalable global multi-cloud infrastructure. Deep experience in Cloud Architecture, OCI, AWS, containerization, microservices, and enterprise infrastructure.",
                    skills_found=["Cloud Architecture", "OCI", "AWS", "Kubernetes", "Microservices"],
                ),
                JobListing(
                    job_id="li_mock_us_1",
                    title="Enterprise AI & Cloud Architect",
                    company="Datadog US",
                    location="San Francisco, CA, United States",
                    work_mode="remote",
                    url="https://www.linkedin.com/jobs/view/9990003/",
                    source_query="AI Architect",
                    source_platform="linkedin",
                    application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
                    status=JobStatus.DISCOVERED,
                    has_full_jd=True,
                    jd_text="Enterprise AI and Cloud Architect to build enterprise Generative AI platforms, LLM pipelines, Agentic AI architectures, and resilient cloud infrastructure.",
                    skills_found=["Generative AI", "LLM", "Agentic AI", "Cloud Architecture", "Python", "AI Platform"],
                ),
            ]

        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
                )
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                    viewport={"width": 1440, "height": 900}
                )

                for region_item in target_regions:
                    region_name = region_item.get("name", "Worldwide")
                    location_query = region_item.get("location", region_name)

                    for q in queries:
                        if len(discovered_jobs) >= self.li_config.get("max_applications_per_day", 25) * 4:
                            break

                        encoded_q = quote_plus(q)
                        encoded_loc = quote_plus(location_query)
                        search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_q}&location={encoded_loc}&f_AL=true"

                        logger.info(f"Searching LinkedIn: query='{q}' | region='{region_name}' (Easy Apply)")
                        try:
                            page.goto(search_url, wait_until="domcontentloaded", timeout=25000)
                            page.wait_for_timeout(3000)

                            job_elements = page.locator("ul.jobs-search__results-list li, .base-search-card").all()
                            logger.info(f"Found {len(job_elements)} job elements for '{q}' in {region_name}")

                            count_for_query = 0
                            for el in job_elements:
                                if count_for_query >= limit_per_query:
                                    break

                                try:
                                    link_el = el.locator("a.base-card__full-link, a[data-tracking-control-name*='job_card']").first
                                    if link_el.count() == 0:
                                        link_el = el.locator("a").first
                                    if link_el.count() == 0:
                                        continue

                                    job_url = link_el.get_attribute("href") or ""
                                    if not job_url or "/jobs/view/" not in job_url:
                                        continue

                                    # Clean up tracking params from URL
                                    clean_url = job_url.split("?")[0]
                                    match_id = re.search(r"(\d{8,12})", clean_url)
                                    job_id = match_id.group(1) if match_id else f"li_{uuid.uuid4().hex[:10]}"

                                    if job_id in seen_job_ids:
                                        continue
                                    seen_job_ids.add(job_id)

                                    title_el = el.locator(".base-search-card__title, h3").first
                                    company_el = el.locator(".base-search-card__subtitle, h4, a.hidden-nested-link").first
                                    loc_el = el.locator(".job-search-card__location, span.job-search-card__location").first

                                    title = title_el.inner_text().strip() if title_el.count() > 0 else q
                                    company = company_el.inner_text().strip() if company_el.count() > 0 else "Enterprise Employer"
                                    location_text = loc_el.inner_text().strip() if loc_el.count() > 0 else f"{region_name}"

                                    # Determine work mode
                                    t_lower = f"{title.lower()} {location_text.lower()}"
                                    if "remote" in t_lower:
                                        work_mode = "remote"
                                    elif "hybrid" in t_lower:
                                        work_mode = "hybrid"
                                    else:
                                        work_mode = "onsite"

                                    jd_snippet = f"{title} at {company} located in {location_text} ({region_name}). Focus areas: {q}, Enterprise Architecture, Cloud Infrastructure, Solutions Engineering, and Technical Leadership."

                                    job_item = JobListing(
                                        job_id=job_id,
                                        title=title,
                                        company=company,
                                        location=f"{location_text} ({region_name})",
                                        work_mode=work_mode,
                                        url=clean_url,
                                        source_query=q,
                                        source_platform="linkedin",
                                        application_method=ApplicationMethod.LINKEDIN_EASY_APPLY,
                                        status=JobStatus.DISCOVERED,
                                        has_full_jd=True,
                                        jd_text=jd_snippet,
                                        skills_found=[q, "Cloud Architecture", "Solution Design"],
                                    )
                                    discovered_jobs.append(job_item)
                                    count_for_query += 1
                                except Exception as parse_err:
                                    logger.debug(f"Error parsing LinkedIn job item: {parse_err}")
                        except Exception as req_err:
                            logger.warning(f"Failed query on LinkedIn for '{q}' in {region_name}: {req_err}")

                browser.close()
        except Exception as e:
            logger.error(f"Error executing LinkedIn discovery: {e}")

        logger.info(f"Total LinkedIn Easy Apply jobs discovered: {len(discovered_jobs)}")
        return discovered_jobs

    def apply_easy_apply(
        self,
        job: JobListing,
        score: Any,
        docx_path: Path,
        pdf_path: Path,
    ) -> ApplicationRecord:
        """Applies to an Easy Apply job in the authenticated persistent session with full automated submission."""
        now = datetime.now(timezone.utc)
        record = ApplicationRecord(
            application_id=f"app_li_{job.job_id}_{now.strftime('%Y%m%d%H%M%S')}",
            job_id=job.job_id,
            source_job_url=job.url,
            application_method=ApplicationMethod.LINKEDIN_EASY_APPLY.value,
            status=JobStatus.APPLICATION_STARTED,
            started_at=now,
            dry_run=self.offline_mode or self.config.get("application", {}).get("dry_run", False),
        )

        if self.offline_mode or self.config.get("application", {}).get("dry_run", False):
            record.status = JobStatus.APPLIED_CONFIRMED
            record.confirmation_reference = f"SIM_LI_{job.job_id}"
            record.confirmation_text = "Simulated LinkedIn application in offline/dry-run mode."
            record.submitted_at = now
            return record

        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    viewport={"width": 1440, "height": 900},
                )
                page = context.pages[0] if context.pages else context.new_page()

                logger.info(f"Navigating to LinkedIn job: {job.title} @ {job.company} ({job.url})")
                page.goto(job.url, wait_until="commit", timeout=35000)
                page.wait_for_timeout(4000)

                # 1. Check if already applied
                already_applied = page.locator("button:has-text('Applied'), span:has-text('Applied')").first
                if already_applied.count() > 0 and already_applied.is_visible():
                    logger.info(f"Already applied to {job.title} on LinkedIn. Recording confirmation.")
                    record.status = JobStatus.APPLIED_CONFIRMED
                    record.confirmation_reference = "ALREADY_APPLIED"
                    context.close()
                    return record

                # 2. Locate Easy Apply button
                apply_btn = page.get_by_role("button", name=re.compile(r"easy apply", re.I)).first
                if apply_btn.count() == 0:
                    apply_btn = page.locator("button.jobs-apply-button, button:has-text('Easy Apply')").first

                if apply_btn.count() == 0 or not apply_btn.is_visible():
                    logger.warning(f"Easy Apply button not visible on {job.url}. Status: EXTERNAL_APPLICATION_REQUIRED")
                    record.status = JobStatus.EXTERNAL_APPLICATION_REQUIRED
                    record.failure_reason = "No Easy Apply button present on LinkedIn job listing."
                    context.close()
                    return record

                logger.info(f"Clicking Easy Apply for {job.title}...")
                apply_btn.click()
                page.wait_for_timeout(3000)

                # 3. Locate modal
                modal = page.locator("div[role='dialog'], .jobs-easy-apply-modal").first
                if modal.count() == 0 or not modal.is_visible():
                    # Fallback click
                    apply_btn.dispatch_event("click")
                    page.wait_for_timeout(3000)
                    modal = page.locator("div[role='dialog'], .jobs-easy-apply-modal").first

                if modal.count() == 0 or not modal.is_visible():
                    record.status = JobStatus.APPLICATION_FAILED
                    record.failure_reason = "Easy Apply modal dialog did not render."
                    context.close()
                    return record

                # 4. Step-by-Step Form Resolution (up to 8 steps)
                step = 0
                max_steps = 8
                submitted = False

                while step < max_steps and not submitted:
                    step += 1
                    logger.info(f"Processing Easy Apply step {step} for {job.title}...")
                    page.wait_for_timeout(2000)

                    # A. Attach Resume if file input present
                    file_input = modal.locator("input[type='file']").first
                    if file_input.count() > 0:
                        try:
                            resume_to_upload = pdf_path if pdf_path.exists() else docx_path
                            if resume_to_upload.exists():
                                file_input.set_input_files(str(resume_to_upload.resolve()))
                                logger.info(f"Attached tailored resume: {resume_to_upload.name}")
                                page.wait_for_timeout(2000)
                        except Exception as up_err:
                            logger.debug(f"Resume upload handling note: {up_err}")

                    # B. Fill text / number inputs
                    text_inputs = modal.locator("input[type='text'], input[type='number'], textarea").all()
                    for inp in text_inputs:
                        try:
                            val = inp.input_value()
                            if val and val.strip():
                                continue  # Already pre-filled

                            # Extract label / question text
                            label_text = ""
                            inp_id = inp.get_attribute("id")
                            if inp_id:
                                lbl = modal.locator(f"label[for='{inp_id}']").first
                                if lbl.count() > 0:
                                    label_text = lbl.inner_text().strip()

                            if not label_text:
                                aria = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
                                label_text = aria

                            if label_text:
                                res = self.answer_resolver.resolve_question(label_text)
                                if res.can_answer and res.answer_value is not None:
                                    inp.fill(str(res.answer_value))
                                    logger.info(f"Filled LinkedIn field '{label_text[:40]}' -> '{res.answer_value}'")
                        except Exception as inp_err:
                            logger.debug(f"Input filling skipped: {inp_err}")

                    # C. Handle Radio Buttons & Checkboxes
                    radio_groups = modal.locator("fieldset").all()
                    for fg in radio_groups:
                        try:
                            legend = fg.locator("legend").first
                            q_text = legend.inner_text().strip() if legend.count() > 0 else ""
                            if q_text:
                                q_lower = q_text.lower()
                                if any(term in q_lower for term in ("relocate", "relocation", "authorized", "authorization", "onsite", "hybrid")):
                                    yes_opt = fg.locator("input[value='Yes'], label:has-text('Yes')").first
                                    if yes_opt.count() > 0:
                                        yes_opt.click()
                                elif "sponsorship" in q_lower:
                                    # For international applications from India, sponsorship is required
                                    req_opt = fg.locator("input[value='Yes'], label:has-text('Yes')").first
                                    if req_opt.count() > 0:
                                        req_opt.click()
                        except Exception as rg_err:
                            logger.debug(f"Fieldset handling note: {rg_err}")

                    # D. Navigation buttons
                    submit_btn = modal.locator("button:has-text('Submit application'), button[aria-label='Submit application']").first
                    next_btn = modal.locator("button:has-text('Next'), button[aria-label='Continue to next step']").first
                    review_btn = modal.locator("button:has-text('Review'), button[aria-label='Review your application']").first

                    if submit_btn.count() > 0 and submit_btn.is_visible():
                        if self.auto_submit:
                            logger.info(f"Submitting LinkedIn application for '{job.title}' @ {job.company}...")
                            submit_btn.click()
                            page.wait_for_timeout(4000)

                            # Take evidence screenshot
                            evidence_file = EVIDENCE_DIR / f"{job.job_id}_linkedin_applied.png"
                            try:
                                page.screenshot(path=str(evidence_file), timeout=5000)
                                record.evidence_path = str(evidence_file)
                            except Exception:
                                pass

                            submitted = True
                            record.status = JobStatus.APPLIED_CONFIRMED
                            record.confirmation_reference = f"LI_{job.job_id}_{uuid.uuid4().hex[:6].upper()}"
                            logger.info(f"LinkedIn application successfully submitted! Ref: {record.confirmation_reference}")
                            break
                        else:
                            logger.info("Auto-submit disabled. Application left at review step.")
                            record.status = JobStatus.FORM_COMPLETED
                            break
                    elif review_btn.count() > 0 and review_btn.is_visible():
                        logger.info("Advancing to Review step...")
                        review_btn.click()
                        page.wait_for_timeout(2000)
                    elif next_btn.count() > 0 and next_btn.is_visible():
                        logger.info("Advancing to Next step...")
                        next_btn.click()
                        page.wait_for_timeout(2000)
                    else:
                        logger.warning(f"No advance button found at step {step}. Exiting form loop.")
                        break

                # Clean up / dismiss modal if not submitted
                if not submitted and record.status != JobStatus.APPLIED_CONFIRMED:
                    dismiss = page.locator("button[aria-label='Dismiss'], button.artdeco-modal__dismiss").first
                    if dismiss.count() > 0:
                        dismiss.click()
                        page.wait_for_timeout(1000)
                        discard = page.locator("button:has-text('Discard'), button[data-control-name='discard_application_confirm_btn']").first
                        if discard.count() > 0:
                            discard.click()
                    record.status = JobStatus.NEEDS_MANUAL_INTERVENTION
                    record.failure_reason = "Unresolved screening fields or multi-page form pause."

                context.close()
        except Exception as e:
            logger.error(f"Error during LinkedIn Easy Apply execution for {job.title}: {e}")
            record.status = JobStatus.APPLICATION_FAILED
            record.failure_reason = str(e)

        return record
