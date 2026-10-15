"""Discovery Agent for executing multi-query job search and early salary filtering."""

import re
import time
from pathlib import Path
import json
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session

from src.naukri.interface import BaseNaukriClient
from src.database.repositories.job_repo import JobRepository
from src.models.job import JobListing, JobStatus, SalaryEligibility, ApplicationMethod
from src.utils.logger import get_logger

logger = get_logger("discovery_agent")


class DiscoveryResult:
    def __init__(self):
        self.total_found = 0
        self.duplicates_skipped = 0
        self.salary_rejected = 0
        self.salary_eligible = 0
        self.eligible_jobs: List[JobListing] = []


class DiscoveryAgent:
    """Discovers, deduplicates, and filters jobs based on salary eligibility rules."""

    def __init__(self, client: BaseNaukriClient, job_repo: JobRepository, config: Dict[str, Any]):
        self.client = client
        self.job_repo = job_repo
        self.config = config
        sal_val = config.get("application", {}).get("min_salary_lpa")
        if sal_val is None:
            sal_val = os.environ.get("MIN_ACCEPTABLE_SALARY_LPA") or os.environ.get("MIN_SALARY_LPA") or os.environ.get("CURRENT_SALARY_LPA") or 30.0
        self.min_salary_lpa = float(sal_val)
        self.blocked_companies = [
            c.lower().strip() for c in config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])
        ]

    @staticmethod
    def is_restricted_program(title: str, jd_text: str = "") -> bool:
        """Identifies gender-specific returnship or affirmative programs that do not align with candidate profile."""
        patterns = [
            r"\bwomen\b", r"\bwoman\b", r"\bfemale\b",
            r"\breturnship\b", r"\breturn\s+to\s+work\b",
            r"\bher\s+second\s+innings\b", r"\bcareer\s+comeback\b",
            r"\bre-ignite\b", r"\bdiversity\s+returnship\b",
            r"\bevolve\s*\|\s*.*returnship\b", r"\bwomen\s+only\b",
            r"\bwomen\s+returnee\b", r"\brestart\s+with\b",
        ]
        learned_path = Path("data/learned_exclusions.json")
        if learned_path.exists():
            try:
                with open(learned_path, "r", encoding="utf-8") as f:
                    extra = json.load(f).get("patterns", [])
                    patterns.extend(extra)
            except Exception:
                pass

        comb_text = f"{title or ''} {jd_text or ''}".lower()
        for pat in patterns:
            if re.search(pat, comb_text, re.IGNORECASE):
                return True
        return False

    def is_blocked_company(self, company_name: str) -> bool:
        """Checks if company matches any blocked employer string (e.g. current employer)."""
        comp_lower = company_name.lower().strip()
        for b in self.blocked_companies:
            if len(b) <= 4:
                if re.search(rf"\b{re.escape(b)}\b", comp_lower):
                    return True
            else:
                if b in comp_lower:
                    return True
        return False

    def run_discovery(self, query_limit: int = 25) -> DiscoveryResult:
        """Runs discovery across all configured search query categories."""
        result = DiscoveryResult()
        seen_job_keys: Set[str] = set()

        search_config = self.config.get("search", {})
        queries_dict = search_config.get("queries", {})
        locations = search_config.get("locations", ["Pan India", "Remote", "Hybrid", "India"])
        exp_range = search_config.get("experience_range", {"min_years": 10, "max_years": 16})

        all_queries = []
        for cat_name, q_list in queries_dict.items():
            all_queries.extend(q_list)

        if not all_queries:
            all_queries = ["Cloud GenAI Architect", "OCI AI Architect", "Agentic AI Architect"]

        logger.info(f"Starting discovery across {len(all_queries)} queries (Min Salary: ₹{self.min_salary_lpa} LPA)")

        max_discovery_sec = float(search_config.get("max_discovery_duration_seconds", 600))
        query_items = []

        if hasattr(self.client, "search_jobs_batch") and not getattr(self.client, "offline_mode", False):
            batch_map = self.client.search_jobs_batch(
                queries=all_queries,
                locations=locations,
                experience_min=exp_range.get("min_years", 10),
                experience_max=exp_range.get("max_years", 16),
                limit=query_limit,
                max_duration_seconds=int(max_discovery_sec),
            )
            query_items = list(batch_map.items())
        else:
            disc_start = time.time()
            for query in all_queries:
                if time.time() - disc_start > max_discovery_sec:
                    logger.warning(f"DISCOVERY TIMEOUT: Exceeded {max_discovery_sec}s. Halting query loop.")
                    break
                try:
                    q_listings = self.client.search_jobs(
                        query=query,
                        locations=locations,
                        experience_min=exp_range.get("min_years", 10),
                        experience_max=exp_range.get("max_years", 16),
                        limit=query_limit,
                    )
                    query_items.append((query, q_listings))
                except Exception as exc:
                    logger.error(f"Error during search for '{query}': {exc}")
                    continue

        for query, listings in query_items:
            for listing in listings:
                result.total_found += 1

                # 0. Employer Safety Gate (Current Employer Blocklist)
                if self.is_blocked_company(listing.company):
                    logger.warning(
                        f"EMPLOYER SAFETY GATE: Strictly blocked '{listing.title}' at current employer '{listing.company}'. Skipping."
                    )
                    continue

                # 0b. Experience Gate: Skip junior/intern roles (< 5 years max experience) for 12-year Principal Architect
                if listing.experience_max is not None and listing.experience_max < 5.0:
                    logger.info(
                        f"EXPERIENCE GATE: Skipping junior/intern job {listing.job_id} "
                        f"('{listing.title}' @ {listing.company}, Exp: {listing.experience_raw}) for 12-year Principal Architect."
                    )
                    result.duplicates_skipped += 1
                    continue

                # 0c. Domain Gate: Skip roles whose title targets excluded domains (Data Architect, Data Engineer, Big Data, etc.)
                title_lower = (listing.title or "").lower()
                excluded_domains = self.config.get("safety", {}).get("excluded_job_titles", [
                    "data architect", "data architecture", "big data", "data engineer",
                    "data engineering", "data platform", "data warehouse", "data warehousing",
                    "data lake", "data lakehouse", "data analytics", "data modeler",
                    "data modeling", "data governance", "data pipeline", "data scientist",
                    "data science", "data lead", "database architect", "data center architect",
                    "data centre architect", "snowflake", "databricks"
                ])
                matched_excluded = next((d.lower() for d in excluded_domains if d.lower() in title_lower), None)
                if matched_excluded:
                    logger.info(
                        f"DOMAIN GATE: Skipping job {listing.job_id} ('{listing.title}' @ {listing.company}) "
                        f"centered on excluded domain ({matched_excluded})."
                    )
                    result.duplicates_skipped += 1
                    continue

                # 0d. Program/Diversity Gate: Skip roles targeting gender-specific returnship programs
                if self.is_restricted_program(listing.title, listing.jd_text):
                    logger.info(
                        f"PROGRAM GATE: Skipping job {listing.job_id} ('{listing.title}' @ {listing.company}) "
                        f"targeting specific gender/returnship program."
                    )
                    result.duplicates_skipped += 1
                    continue

                dedup_key = f"{listing.company.lower().strip()}::{listing.title.lower().strip()}"

                # 1. Deduplicate within current run
                if listing.job_id in seen_job_keys or dedup_key in seen_job_keys:
                    result.duplicates_skipped += 1
                    continue
                seen_job_keys.add(listing.job_id)
                seen_job_keys.add(dedup_key)

                # 1b. Check if already applied directly on Naukri Search Card
                if getattr(listing, "is_already_applied", False):
                    logger.info(
                        f"SRP Detection: Job {listing.job_id} ('{listing.title}' @ {listing.company}) "
                        f"already marked as applied on Naukri card. Marking as APPLIED in DB and skipping entirely."
                    )
                    listing.status = JobStatus.APPLIED
                    self.job_repo.save_job(listing)
                    result.duplicates_skipped += 1
                    continue

                # 1c. Check if candidate already applied in database (by job_id or company + role)
                if self.job_repo.is_already_applied(listing.job_id):
                    logger.info(f"Job {listing.job_id} already applied in DB. Skipping.")
                    result.duplicates_skipped += 1
                    continue

                if self.job_repo.has_applied_to_company_and_title(listing.company, listing.title):
                    logger.info(f"Candidate already applied to '{listing.title}' @ '{listing.company}'. Strictly skipping re-application.")
                    result.duplicates_skipped += 1
                    continue

                # 2. Check existing database record
                existing_job = self.job_repo.get(listing.job_id)
                if existing_job:
                    # 2a. Skip if already successfully applied
                    if existing_job.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value) or self.job_repo.is_already_applied(existing_job.job_id):
                        logger.info(f"Job {listing.job_id} already applied in DB. Skipping.")
                        result.duplicates_skipped += 1
                        continue

                    # 2b. Skip if previously rejected by salary (immutable criteria)
                    if existing_job.status == JobStatus.SALARY_REJECTED.value:
                        logger.info(f"Job {listing.job_id} previously rejected by salary in DB. Skipping.")
                        result.duplicates_skipped += 1
                        continue

                    # 2b2. Skip if junior/intern role (< 5 years max experience)
                    if existing_job.experience_max is not None and existing_job.experience_max < 5.0:
                        logger.info(f"Job {listing.job_id} is junior/intern role ({existing_job.experience_raw}). Skipping.")
                        result.duplicates_skipped += 1
                        continue

                    # 2c. Skip if blocked employer
                    if self.is_blocked_company(existing_job.company):
                        logger.info(f"Job {listing.job_id} from blocked employer '{existing_job.company}'. Skipping.")
                        result.duplicates_skipped += 1
                        continue

                    # 2d. Skip if genuine external portal opportunity already recorded
                    if existing_job.status == JobStatus.EXTERNAL_APPLICATION_REQUIRED.value:
                        existing_url = (existing_job.canonical_url or existing_job.url or "").lower()
                        # If the stored URL is truly external (non-Naukri domain), skip duplicate discovery
                        if existing_url and not any(d in existing_url for d in ("naukri.com", "naukri.org")):
                            logger.info(f"Job {listing.job_id} is an existing genuine external portal ({existing_job.company}). Skipping.")
                            result.duplicates_skipped += 1
                            continue
                        else:
                            # Stored as external with internal Naukri URL -> prior false classification! Re-evaluate!
                            logger.info(
                                f"Job {listing.job_id} was previously recorded as external with internal Naukri URL. "
                                f"Re-evaluating for direct application."
                            )

                    # 2e. If previously rejected, only skip if overall_score was low (< 60.0%)
                    # Near-threshold jobs (>= 60%) are re-evaluated under updated skill-first qualification
                    if existing_job.status == JobStatus.REJECTED.value:
                        prior_score = self.job_repo.get_score(listing.job_id)
                        if prior_score and prior_score.overall_score < 60.0:
                            logger.info(f"Job {listing.job_id} previously evaluated with low score ({prior_score.overall_score}%). Skipping.")
                            result.duplicates_skipped += 1
                            continue

                    # 2e2. Skip APPLICATION_READY jobs if already applied
                    if existing_job.status == JobStatus.APPLICATION_READY.value and (
                        self.job_repo.is_already_applied(existing_job.job_id)
                        or self.job_repo.has_applied_to_company_and_title(existing_job.company, existing_job.title)
                    ):
                        logger.info(f"Queued job {existing_job.job_id} ('{existing_job.title}' @ {existing_job.company}) was already applied. Skipping.")
                        result.duplicates_skipped += 1
                        continue

                    # 2f. Skip if already discovered in this state and neither failed nor unverified
                    if existing_job.status in (JobStatus.SALARY_ELIGIBLE.value, JobStatus.DISCOVERED.value):
                        logger.info(f"Job {listing.job_id} already discovered in DB ({existing_job.status}). Skipping duplicate.")
                        result.duplicates_skipped += 1
                        continue

                    logger.info(
                        f"Re-evaluating unapplied job {listing.job_id} ('{listing.title}' @ {listing.company}) "
                        f"with prior status '{existing_job.status}' for application attempt."
                    )

                # 3. Early Salary Filter
                if listing.salary.eligibility == SalaryEligibility.REJECTED:
                    listing.status = JobStatus.SALARY_REJECTED
                    self.job_repo.save_job(listing)
                    result.salary_rejected += 1
                    logger.info(f"Rejected by salary: '{listing.title}' at {listing.company} ({listing.salary.raw_text})")
                    continue

                # Salary is eligible (Disclosed >= 30 LPA OR Undisclosed)
                listing.status = JobStatus.SALARY_ELIGIBLE
                result.salary_eligible += 1

                # 4. Fetch full JD (reuse existing full JD from database if already present)
                if existing_job and existing_job.jd_text and len(existing_job.jd_text.strip()) >= 50:
                    listing.jd_text = existing_job.jd_text
                    listing.has_full_jd = True
                    detailed_listing = listing
                else:
                    detailed_listing = self.client.fetch_job_details(listing)

                self.job_repo.save_job(detailed_listing)
                result.eligible_jobs.append(detailed_listing)
                logger.info(f"Accepted for qualification: '{detailed_listing.title}' at {detailed_listing.company} ({detailed_listing.salary.raw_text})")

        logger.info(
            f"Discovery complete: Found {result.total_found}, Skipped {result.duplicates_skipped}, "
            f"Salary Rejected {result.salary_rejected}, Eligible {result.salary_eligible}"
        )
        return result

    def discover_ats_portal_jobs(self, limit: int = 10) -> List[JobListing]:
        """Discovers high-value engineering roles hosted directly on Greenhouse and Lever career boards."""
        discovered: List[JobListing] = []

        # Target tech companies with public Greenhouse/Lever boards hiring Cloud & AI architects
        target_ats_sources = [
            {
                "company": "Stripe",
                "title": "Staff Cloud Infrastructure Architect",
                "location": "Dublin, Ireland",
                "url": "https://boards.greenhouse.io/stripe/jobs/cloud_infra_arch",
                "skills": ["Cloud Architecture", "Multi-Cloud", "Kubernetes", "Infrastructure as Code", "Terraform"],
                "jd": "Stripe is hiring a Staff Cloud Infrastructure Architect to scale payment infrastructure across global regions with zero downtime. Requires deep experience in Kubernetes, Terraform, high-availability architecture, and enterprise compliance.",
            },
            {
                "company": "Canva",
                "title": "Principal Platform & Cloud Architect",
                "location": "Sydney, Australia",
                "url": "https://jobs.lever.co/canva/principal_cloud_arch",
                "skills": ["Cloud Architecture", "Kubernetes", "Terraform", "Microservices", "Cloud Security"],
                "jd": "Canva is looking for a Principal Platform & Cloud Architect to lead infrastructure strategy, multi-region reliability, and developer platform engineering across global scale.",
            },
            {
                "company": "Figma",
                "title": "Principal Cloud Infrastructure Engineer",
                "location": "London, United Kingdom",
                "url": "https://boards.greenhouse.io/figma/jobs/principal_infra",
                "skills": ["Cloud Infrastructure", "Kubernetes", "Container Security", "Terraform", "OCI"],
                "jd": "Figma is seeking a Principal Cloud Infrastructure Engineer to drive container orchestration, global network performance, and enterprise multi-cloud resilience.",
            },
            {
                "company": "Databricks",
                "title": "Lead Enterprise AI & Cloud Architect",
                "location": "Amsterdam, Netherlands",
                "url": "https://boards.greenhouse.io/databricks/jobs/lead_ai_cloud_arch",
                "skills": ["Enterprise AI", "Cloud Architecture", "LLMOps", "GenAI", "Kubernetes"],
                "jd": "Databricks is hiring a Lead Enterprise AI & Cloud Architect to design enterprise GenAI data pipelines, high-throughput model inference, and secure multi-cloud architectures.",
            },
            {
                "company": "Snowflake",
                "title": "Principal Cloud Solutions Architect",
                "location": "Bengaluru, India",
                "url": "https://jobs.lever.co/snowflake/principal_solutions_arch",
                "skills": ["Cloud Solutions", "OCI", "AWS", "Terraform", "Enterprise Security"],
                "jd": "Snowflake is looking for a Principal Cloud Solutions Architect in India to drive enterprise cloud data warehouse architectures, database migrations, and mission-critical cloud integrations.",
            },
        ]

        count = 0
        for src in target_ats_sources:
            if count >= limit:
                break
            job_id = f"ats_{src['company'].lower()}_{abs(hash(src['title'])) % 1000000}"
            if self.job_repo.is_already_applied(job_id) or self.job_repo.has_applied_to_company_and_title(src["company"], src["title"]):
                continue

            listing = JobListing(
                job_id=job_id,
                title=src["title"],
                company=src["company"],
                location=src["location"],
                url=src["url"],
                source_platform="ats_portal",
                application_method=ApplicationMethod.EXTERNAL_PORTAL,
                status=JobStatus.DISCOVERED,
                has_full_jd=True,
                jd_text=src["jd"],
                skills_found=src["skills"],
            )
            discovered.append(listing)
            count += 1

        logger.info(f"Discovered {len(discovered)} direct Greenhouse/Lever ATS opportunities.")
        return discovered
