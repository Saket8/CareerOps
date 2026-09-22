"""Job and Application data models."""

from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    PARSED = "PARSED"
    SALARY_REJECTED = "SALARY_REJECTED"
    SALARY_ELIGIBLE = "SALARY_ELIGIBLE"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    HIGH_MATCH = "HIGH_MATCH"
    RESUME_READY = "RESUME_READY"
    ATS_VALIDATED = "ATS_VALIDATED"
    APPLICATION_READY = "APPLICATION_READY"
    APPLIED = "APPLIED"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    NEEDS_DATA = "NEEDS_DATA"


class SalaryEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REJECTED = "REJECTED"
    UNDISCLOSED = "UNDISCLOSED"


class JobSalary(BaseModel):
    min_lpa: Optional[float] = None
    max_lpa: Optional[float] = None
    currency: str = "INR"
    period: str = "per_annum"
    is_disclosed: bool = False
    eligibility: SalaryEligibility = SalaryEligibility.UNDISCLOSED
    raw_text: str = ""
    rejection_reason: Optional[str] = None


class JobListing(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    work_mode: str = "onsite"  # remote, hybrid, onsite
    experience_min: Optional[float] = None
    experience_max: Optional[float] = None
    experience_raw: str = ""
    salary: JobSalary = Field(default_factory=JobSalary)
    posted_date: Optional[str] = None
    url: str
    canonical_url: Optional[str] = None
    jd_text: str = ""
    source_query: str = ""
    source_platform: str = "naukri"
    application_method: str = "standard"
    status: JobStatus = JobStatus.DISCOVERED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApplicationRecord(BaseModel):
    application_id: str
    job_id: str
    resume_version_id: Optional[str] = None
    submitted_at: Optional[datetime] = None
    status: JobStatus = JobStatus.APPLICATION_READY
    application_method: str = "standard"
    confirmation_reference: Optional[str] = None
    questions_answered: Dict[str, Any] = Field(default_factory=dict)
    failure_reason: Optional[str] = None
    dry_run: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
