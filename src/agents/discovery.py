"""Discovery Agent for executing multi-query job search and early salary filtering."""

import re
from typing import List, Dict, Any, Set
from sqlalchemy.orm import Session

from src.naukri.interface import BaseNaukriClient
from src.database.repositories.job_repo import JobRepository
from src.models.job import JobListing, JobStatus, SalaryEligibility
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
        self.min_salary_lpa = float(config.get("application", {}).get("min_salary_lpa", 30.0))
        self.blocked_companies = [
            c.lower().strip() for c in config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])
        ]

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

        for query in all_queries:
            try:
                listings = self.client.search_jobs(
                    query=query,
                    locations=locations,
                    experience_min=exp_range.get("min_years", 10),
                    experience_max=exp_range.get("max_years", 16),
                    limit=query_limit,
                )
            except Exception as exc:
                logger.error(f"Error during search for '{query}': {exc}")
                continue

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

                # 0c. Domain Gate: Skip roles whose title targets excluded technologies (Snowflake, Databricks)
                title_lower = (listing.title or "").lower()
                if any(tech in title_lower for tech in ["snowflake", "databricks"]):
                    logger.info(
                        f"DOMAIN GATE: Skipping job {listing.job_id} ('{listing.title}' @ {listing.company}) "
                        f"centered on excluded technology (Snowflake/Databricks)."
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
                    logger.info(f"Job {listing.job_id} ('{listing.title}' @ {listing.company}) already marked as applied on Naukri card. Skipping.")
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
                    if existing_job.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value):
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
