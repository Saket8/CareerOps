"""Pydantic data models package."""

from src.models.candidate import (
    CandidateTruth,
    CandidateProfile,
    Certification,
    EmploymentRecord,
    EducationRecord,
)
from src.models.job import (
    JobStatus,
    SalaryEligibility,
    JobSalary,
    JobListing,
    ApplicationRecord,
)
from src.models.score import (
    JobScore,
    JobEvidence,
)
from src.models.report import (
    DailyReportData,
    WeeklyIntelligenceData,
    TopApplicationItem,
    MarketTrendItem,
)

__all__ = [
    "CandidateTruth",
    "CandidateProfile",
    "Certification",
    "EmploymentRecord",
    "EducationRecord",
    "JobStatus",
    "SalaryEligibility",
    "JobSalary",
    "JobListing",
    "ApplicationRecord",
    "JobScore",
    "JobEvidence",
    "DailyReportData",
    "WeeklyIntelligenceData",
    "TopApplicationItem",
    "MarketTrendItem",
]
