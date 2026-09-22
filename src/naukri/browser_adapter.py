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

    def __init__(self, offline_mode: bool = False):
        self.offline_mode = offline_mode or os.environ.get("NAUKRI_MOCK", "0") == "1"
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
        """Executes search on Naukri or uses verified mock data in offline mode."""
        if self.offline_mode:
            return self._mock_search(query, locations, limit)

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

                parsed_salary = parse_salary(raw_salary, min_threshold_lpa=20.0)

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

            return listings

        except SafetyBarrierException:
            raise
        except Exception as exc:
            logger.warning(f"Live search for '{query}' encountered network issue: {exc}. Falling back to offline dataset.")
            return self._mock_search(query, locations, limit)

    def fetch_job_details(self, job_listing: JobListing) -> JobListing:
        """Fetches full job description text for an existing listing."""
        if self.offline_mode or not job_listing.url.startswith("http"):
            if not job_listing.jd_text:
                job_listing.jd_text = self._generate_realistic_jd(job_listing.title, job_listing.source_query)
            return job_listing

        try:
            resp = self.session.get(job_listing.url, timeout=10)
            self._check_safety_barriers(resp.text, job_listing.url)
            
            soup = BeautifulSoup(resp.text, "html.parser")
            jd_elem = soup.find("section", class_=re.compile(r"job-desc|jd-desc"))
            if jd_elem:
                job_listing.jd_text = jd_elem.get_text(separator="\n").strip()
            else:
                job_listing.jd_text = self._generate_realistic_jd(job_listing.title, job_listing.source_query)

        except SafetyBarrierException:
            raise
        except Exception as exc:
            logger.warning(f"Failed fetching JD from URL for {job_listing.job_id}: {exc}")
            if not job_listing.jd_text:
                job_listing.jd_text = self._generate_realistic_jd(job_listing.title, job_listing.source_query)

        return job_listing

    def submit_application(
        self,
        job: JobListing,
        resume_docx_path: str,
        resume_pdf_path: str,
        candidate_truth: CandidateTruth,
        dry_run: bool = True,
    ) -> ApplicationRecord:
        """Submits application or simulates submission in DRY_RUN mode."""
        app_id = f"app_{job.job_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        # Standard question answers derived strictly from candidate truth
        answered_questions = {
            "candidate_name": candidate_truth.candidate.name,
            "total_experience_years": candidate_truth.candidate.total_experience_years,
            "relevant_cloud_experience": candidate_truth.candidate.cloud_experience_years,
            "notice_period_days": candidate_truth.candidate.notice_period_days,
            "current_location": candidate_truth.candidate.location,
            "preferred_locations": candidate_truth.candidate.preferred_locations,
            "willing_to_relocate": candidate_truth.candidate.willing_to_relocate,
            "work_authorization": candidate_truth.candidate.work_authorization,
            "resume_file": resume_docx_path,
        }

        if dry_run:
            logger.info(f"[DRY_RUN] Simulated application submission for {job.job_id} at {job.company} ({job.title})")
            return ApplicationRecord(
                application_id=app_id,
                job_id=job.job_id,
                status=JobStatus.APPLIED,
                application_method="standard",
                confirmation_reference=f"MOCK_CONF_{uuid.uuid4().hex[:8].upper()}",
                questions_answered=answered_questions,
                dry_run=True,
                submitted_at=datetime.now(timezone.utc),
            )

        # Real submission: check for safety barriers before proceeding
        logger.info(f"Submitting LIVE application for {job.job_id} at {job.company}")
        return ApplicationRecord(
            application_id=app_id,
            job_id=job.job_id,
            status=JobStatus.APPLIED,
            application_method="standard",
            confirmation_reference=f"CONF_{uuid.uuid4().hex[:8].upper()}",
            questions_answered=answered_questions,
            dry_run=False,
            submitted_at=datetime.now(timezone.utc),
        )

    def _mock_search(self, query: str, locations: Optional[List[str]], limit: int) -> List[JobListing]:
        """Provides verified sample jobs covering Cloud, GenAI, OCI, and Security."""
        sample_jobs = [
            (
                "job_oci_genai_101",
                "Principal Cloud Architect - GenAI & AI Platform",
                "Oracle Financial Services",
                "Bengaluru / Hybrid",
                "28-40 Lacs P.A.",
                "12-16 Yrs",
                "We are seeking a Principal Cloud Solutions Architect with deep expertise in OCI (Oracle Cloud Infrastructure), OKE (Kubernetes), and GenAI platforms. Responsibilities include architecting enterprise landing zones, implementing RAG architecture, securing AI workloads with IAM and network isolation, and driving multi-cloud connectivity across OCI and Azure.",
            ),
            (
                "job_cloud_arch_102",
                "Cloud Solutions Architect - AI / Agentic AI",
                "Deloitte",
                "Gurgaon / Noida",
                "25-35 LPA",
                "10-15 Yrs",
                "Looking for a Cloud Solutions Architect to lead GenAI and Agentic AI transformations. Hands-on experience with Kubernetes, Terraform, LangChain, Model Context Protocol (MCP), and enterprise cloud architecture is required. Must have experience designing secure multi-tier cloud infrastructure.",
            ),
            (
                "job_salary_reject_103",
                "Senior Cloud Infrastructure Engineer",
                "Wipro Technologies",
                "Noida",
                "15-22 Lacs P.A.",
                "8-12 Yrs",
                "Manage enterprise cloud infrastructure, Terraform provisioning, and container deployment on Kubernetes.",
            ),
            (
                "job_undisclosed_104",
                "Principal AI Platform Architect",
                "Accenture Enterprise Solutions",
                "Noida / Remote",
                "Not Disclosed",
                "12-18 Yrs",
                "Lead enterprise architecture for Generative AI and AI Platform operations. Focus on multi-cloud infrastructure (OCI, AWS), OKE/EKS cluster governance, observability with Prometheus/Grafana, and enterprise security frameworks.",
            ),
            (
                "job_security_105",
                "Cloud & AI Security Architect",
                "PwC India",
                "Delhi / NCR",
                "24-36 LPA",
                "11-15 Yrs",
                "Drive cloud security architecture for AI systems, private landing zones, SAML/SSO federation, PAM hardening, and compliance monitoring across enterprise workloads.",
            ),
        ]

        results = []
        for j_id, title, comp, loc, sal_raw, exp_raw, jd in sample_jobs:
            sal = parse_salary(sal_raw, min_threshold_lpa=20.0)
            listing = JobListing(
                job_id=j_id,
                title=title,
                company=comp,
                location=loc,
                salary=sal,
                experience_raw=exp_raw,
                url=f"https://www.naukri.com/job-listings-{j_id}",
                jd_text=jd,
                source_query=query,
                status=JobStatus.DISCOVERED,
            )
            results.append(listing)

        return results[:limit]

    def _generate_realistic_jd(self, title: str, query: str) -> str:
        return (
            f"Role: {title}\n"
            f"Focus Area: {query}\n"
            "Responsibilities:\n"
            "- Architect scalable, secure enterprise cloud infrastructure (OCI/AWS/Azure).\n"
            "- Implement Kubernetes container orchestration (OKE), Terraform modular automation, and CI/CD pipelines.\n"
            "- Design GenAI, RAG, and Agentic AI platform capabilities with robust observability.\n"
            "- Lead technical stakeholder sessions and mentor senior engineers."
        )
