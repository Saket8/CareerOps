"""Discovery Agent for executing multi-query job search and early salary filtering."""

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
        self.min_salary_lpa = float(config.get("application", {}).get("min_salary_lpa", 20.0))
        self.blocked_companies = [
            c.lower().strip() for c in config.get("safety", {}).get("blocked_companies", ["cognizant", "cts"])
        ]

    def is_blocked_company(self, company_name: str) -> bool:
        """Checks if company matches any blocked employer string (e.g. current employer)."""
        comp_lower = company_name.lower().strip()
        return any(b in comp_lower for b in self.blocked_companies)

    def run_discovery(self, query_limit: int = 25) -> DiscoveryResult:
        """Runs discovery across all configured search query categories."""
        result = DiscoveryResult()
        seen_job_keys: Set[str] = set()

        search_config = self.config.get("search", {})
        queries_dict = search_config.get("queries", {})
        locations = search_config.get("locations", ["Noida", "Gurgaon", "Delhi / NCR", "Bengaluru", "Remote"])
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

                dedup_key = f"{listing.company.lower().strip()}::{listing.title.lower().strip()}"

                # 1. Deduplicate within current run
                if listing.job_id in seen_job_keys or dedup_key in seen_job_keys:
                    result.duplicates_skipped += 1
                    continue
                seen_job_keys.add(listing.job_id)
                seen_job_keys.add(dedup_key)

                # 2. Deduplicate against database
                if self.job_repo.exists(listing.job_id):
                    logger.info(f"Job {listing.job_id} already exists in DB, skipping duplicate discovery")
                    result.duplicates_skipped += 1
                    continue

                # 3. Early Salary Filter
                if listing.salary.eligibility == SalaryEligibility.REJECTED:
                    listing.status = JobStatus.SALARY_REJECTED
                    self.job_repo.save_job(listing)
                    result.salary_rejected += 1
                    logger.info(f"Rejected by salary: '{listing.title}' at {listing.company} ({listing.salary.raw_text})")
                    continue

                # Salary is eligible (Disclosed >= 20 LPA OR Undisclosed)
                listing.status = JobStatus.SALARY_ELIGIBLE
                result.salary_eligible += 1

                # 4. Fetch full JD
                detailed_listing = self.client.fetch_job_details(listing)
                self.job_repo.save_job(detailed_listing)
                result.eligible_jobs.append(detailed_listing)
                logger.info(f"Accepted for qualification: '{detailed_listing.title}' at {detailed_listing.company} ({detailed_listing.salary.raw_text})")

        logger.info(
            f"Discovery complete: Found {result.total_found}, Skipped {result.duplicates_skipped}, "
            f"Salary Rejected {result.salary_rejected}, Eligible {result.salary_eligible}"
        )
        return result
