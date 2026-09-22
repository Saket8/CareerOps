"""Candidate model schema ensuring strict adherence to truth layer."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CandidateProfile(BaseModel):
    name: str
    title: str
    current_organization: str
    current_role: str
    email: str
    phone: str
    location: str
    preferred_locations: List[str] = Field(default_factory=list)
    total_experience_years: float
    cloud_experience_years: float
    oci_experience_years: float
    kubernetes_experience_years: float = 5.0
    notice_period_days: int = 30
    willing_to_relocate: bool = True
    work_authorization: str = "Indian Citizen"
    current_salary_disclosed: bool = False
    current_salary_lpa: Optional[float] = None
    min_acceptable_salary_lpa: Optional[float] = None
    target_salary_lpa: Optional[float] = None


class Certification(BaseModel):
    name: str
    year: Optional[int] = None
    issuer: str = "Oracle"
    verified: bool = True
    source: str


class EmploymentRecord(BaseModel):
    company: str
    client: Optional[str] = None
    role: str
    start_date: str
    end_date: str
    duration: Optional[str] = None
    responsibilities: List[str] = Field(default_factory=list)


class EducationRecord(BaseModel):
    degree: str
    field: str
    institution: str
    score: Optional[str] = None


class CandidateTruth(BaseModel):
    candidate: CandidateProfile
    verified_competencies: Dict[str, Any]
    certifications: List[Certification]
    employment_history: List[EmploymentRecord]
    education: List[EducationRecord]
