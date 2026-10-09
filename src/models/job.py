"""Job and Application data models."""

from enum import Enum
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    # Lifecycle States per tasks/goal.md
    DISCOVERED = "DISCOVERED"
    ELIGIBLE = "ELIGIBLE"
    APPLICATION_STARTED = "APPLICATION_STARTED"
    FORM_COMPLETED = "FORM_COMPLETED"
    SUBMISSION_ATTEMPTED = "SUBMISSION_ATTEMPTED"
    APPLIED_CONFIRMED = "APPLIED_CONFIRMED"  # The ONLY status counting as successful application
    APPLICATION_FAILED = "APPLICATION_FAILED"
    APPLICATION_BLOCKED = "APPLICATION_BLOCKED"
    EXTERNAL_APPLICATION_REQUIRED = "EXTERNAL_APPLICATION_REQUIRED"
    NEEDS_MANUAL_INTERVENTION = "NEEDS_MANUAL_INTERVENTION"
    SUBMISSION_UNVERIFIED = "SUBMISSION_UNVERIFIED"

    # Pipeline Pipeline Intermediary States (for backward compatibility)
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
    DISQUALIFIED_DIVERSITY = "DISQUALIFIED_DIVERSITY"
    DISQUALIFIED_SCREENING = "DISQUALIFIED_SCREENING"
    READY_FOR_RETRY = "READY_FOR_RETRY"


class ApplicationMethod(str, Enum):
    NAUKRI_DIRECT = "NAUKRI_DIRECT"
    LINKEDIN_EASY_APPLY = "LINKEDIN_EASY_APPLY"
    EXTERNAL_PORTAL = "EXTERNAL_PORTAL"
    MANUAL_REQUIRED = "MANUAL_REQUIRED"


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
    has_full_jd: bool = False
    source_query: str = ""
    discovered_via_query: Optional[str] = ""
    skills_found: List[str] = Field(default_factory=list)
    source_platform: str = "naukri"
    application_method: str = "NAUKRI_DIRECT"
    status: JobStatus = JobStatus.DISCOVERED
    is_already_applied: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ApplicationRecord(BaseModel):
    application_id: str
    job_id: str
    application_method: str = "NAUKRI_DIRECT"
    source_job_url: str = ""
    canonical_job_url: Optional[str] = None
    application_url: Optional[str] = None
    external_application_url: Optional[str] = None
    external_portal: Optional[str] = None
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    status: JobStatus = JobStatus.APPLICATION_READY
    resume_version: Optional[str] = None
    resume_version_id: Optional[str] = None
    questions_detected: List[Dict[str, Any]] = Field(default_factory=list)
    questions_answered: Dict[str, Any] = Field(default_factory=dict)
    confirmation_detected: bool = False
    confirmation_text: Optional[str] = None
    confirmation_reference: Optional[str] = None
    final_url: Optional[str] = None
    verification_method: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    evidence_path: Optional[str] = None
    failure_reason: Optional[str] = None
    dry_run: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
