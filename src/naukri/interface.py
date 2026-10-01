"""Abstract interface for Naukri access."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from src.models.job import JobListing, ApplicationRecord
from src.models.candidate import CandidateTruth


class SafetyBarrierException(Exception):
    """Raised when an anti-automation barrier (CAPTCHA, MFA, bot detection) is encountered."""
    def __init__(self, barrier_type: str, message: str, page_content: Optional[str] = None):
        super().__init__(f"Safety barrier detected [{barrier_type}]: {message}")
        self.barrier_type = barrier_type
        self.page_content = page_content


class BaseNaukriClient(ABC):
    """Abstract base class for all Naukri platform clients (API, Browser, Mock)."""

    @abstractmethod
    def search_jobs(
        self,
        query: str,
        locations: Optional[List[str]] = None,
        experience_min: Optional[int] = None,
        experience_max: Optional[int] = None,
        limit: int = 25,
    ) -> List[JobListing]:
        """Search for job listings matching the query."""
        pass

    @abstractmethod
    def fetch_job_details(self, job_listing: JobListing) -> JobListing:
        """Fetch full job description and metadata for a listing."""
        pass

    @abstractmethod
    def submit_application(
        self,
        job: JobListing,
        resume_docx_path: str,
        resume_pdf_path: str,
        candidate_truth: CandidateTruth,
        dry_run: bool = True,
    ) -> ApplicationRecord:
        """Submit application to a qualifying job."""
        pass

    def refresh_profile_resume(self, resume_path: Optional[str] = None) -> Dict[str, Any]:
        """Re-upload master CV to candidate's Naukri profile to refresh profile freshness timestamp."""
        return {"success": True, "message": "Default base client refresh noop"}
