"""Browser/HTTP Adapter for interacting with Naukri with strict safety boundaries."""

import re
import os
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

from src.naukri.interface import BaseNaukriClient, SafetyBarrierException
from src.models.job import JobListing, JobStatus, JobSalary, SalaryEligibility, ApplicationRecord
from src.models.candidate import CandidateTruth
from src.utils.salary_parser import parse_salary
from src.utils.logger import get_logger

logger = get_logger("naukri_browser_adapter")


class NaukriBrowserAdapter(BaseNaukriClient):
    """Safe adapter for Naukri job discovery and application."""

    def __init__(self, offline_mode: bool = False, min_salary_lpa: float = 30.0):
        self.offline_mode = offline_mode or os.environ.get("NAUKRI_MOCK", "0") == "1"
        self.min_salary_lpa = min_salary_lpa
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _check_safety_barriers(self, text: str, url: str = "") -> None:
        """Inspects HTML/response text for security challenges and halts immediately."""
        lower = text.lower()
        if "recaptcha" in lower or "g-recaptcha" in lower or "hcaptcha" in lower:
            raise SafetyBarrierException("CAPTCHA", "reCAPTCHA or hCaptcha challenge encountered", text[:500])
        if "verify you are human" in lower or "bot detection" in lower or "cf-turnstile" in lower:
            raise SafetyBarrierException("BOT_DETECTION", "Cloudflare or bot defense challenge detected", text[:500])
        if "otp verification" in lower or "enter otp" in lower or "mfa" in lower:
            raise SafetyBarrierException("MFA_OTP", "MFA/OTP barrier detected", text[:500])
        if "payment required" in lower or "fee required" in lower:
            raise SafetyBarrierException("PAYMENT_WALL", "Paid placement or application fee requested", text[:500])

    def search_jobs(
        self,
        query: str,
        locations: Optional[List[str]] = None,
        experience_min: Optional[int] = None,
        experience_max: Optional[int] = None,
        limit: int = 25,
    ) -> List[JobListing]:
        if self.offline_mode:
            logger.info("Offline mode: Skipping HTTP network search. Returning empty list.")
            return []

        formatted_query = query.replace(" ", "-").lower()
        search_url = f"https://www.naukri.com/{formatted_query}-jobs"
        logger.info(f"Executing search: '{query}' on {search_url}")

        try:
            resp = self.session.get(search_url, timeout=10)
            self._check_safety_barriers(resp.text, search_url)
            
            # If standard response is returned, parse listings
            # If access denied or blocked by cloudflare, raise barrier
            if resp.status_code in (403, 429):
                raise SafetyBarrierException("ACCESS_RESTRICTION", f"HTTP {resp.status_code} received from Naukri")

            soup = BeautifulSoup(resp.text, "html.parser")
            job_tuples = soup.find_all("div", class_=re.compile(r"srp-jobtuple|cust-job-tuple"))
            listings = []

            for idx, tuple_elem in enumerate(job_tuples[:limit]):
                title_elem = tuple_elem.find("a", class_=re.compile(r"title"))
                comp_elem = tuple_elem.find("a", class_=re.compile(r"comp-name"))
                loc_elem = tuple_elem.find("span", class_=re.compile(r"loc"))
                sal_elem = tuple_elem.find("span", class_=re.compile(r"sal|salary"))
                exp_elem = tuple_elem.find("span", class_=re.compile(r"exp"))

                if not title_elem:
                    continue

                title = title_elem.text.strip()
                url = title_elem.get("href", "")
                company = comp_elem.text.strip() if comp_elem else "Unknown Company"
                location = loc_elem.text.strip() if loc_elem else (locations[0] if locations else "India")
                raw_salary = sal_elem.text.strip() if sal_elem else "Not Disclosed"
                raw_exp = exp_elem.text.strip() if exp_elem else ""

                # Extract job ID from URL or hash
                job_id_match = re.search(r"-(\d{6,})", url)
                job_id = job_id_match.group(1) if job_id_match else f"nk_{abs(hash(url))}"

                parsed_salary = parse_salary(raw_salary, min_threshold_lpa=self.min_salary_lpa)

                listing = JobListing(
                    job_id=job_id,
                    title=title,
                    company=company,
                    location=location,
                    salary=parsed_salary,
                    experience_raw=raw_exp,
                    url=url,
                    source_query=query,
                    status=JobStatus.DISCOVERED,
                )
                listings.append(listing)

            if not listings:
                logger.info(
                    f"Search yielded 0 listings for query '{query}'. Returning empty list (zero dummy fallback)."
                )
                return []

            return listings

        except SafetyBarrierException:
            raise
        except Exception as exc:
            logger.warning(f"Search for '{query}' encountered issue: {exc}. Returning empty list.")
            return []

    def fetch_job_details(self, job_listing: JobListing) -> JobListing:
        """Fetches full job description text for an existing listing."""
        if not job_listing.url.startswith("http"):
            return job_listing

        try:
            resp = self.session.get(job_listing.url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                jd_elem = soup.find("div", class_=re.compile(r"job-desc|dang-inner-html"))
                if jd_elem:
                    job_listing.jd_text = jd_elem.get_text(separator="\n").strip()
        except Exception as exc:
            logger.warning(f"Could not fetch JD text for {job_listing.url}: {exc}")
        return job_listing

    def submit_application(
        self,
        job: JobListing,
        resume_docx_path: str,
        resume_pdf_path: str,
        candidate_truth: CandidateTruth,
        dry_run: bool = False,
    ) -> ApplicationRecord:
        """Direct HTTP submission is disabled. All submissions must use PlaywrightBrowserAdapter."""
        raise NotImplementedError(
            "Direct HTTP application submission is disabled. "
            "All applications must be submitted via PlaywrightBrowserAdapter with authentic live browser verification."
        )
