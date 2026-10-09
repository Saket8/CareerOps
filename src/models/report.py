"""Reporting and telemetry models."""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TopApplicationItem(BaseModel):
    company: str
    role: str
    salary: str
    match_score: float
    key_factors: List[str]
    resume_used: str
    status: str
    url: str
    method: str = "Naukri Direct"
    reason: Optional[str] = None
    evidence_path: Optional[str] = None
    confirmation_ref: Optional[str] = None
    cover_letter_path: Optional[str] = None
    outreach_target: Optional[str] = None
    outreach_inmail: Optional[str] = None
    outreach_search_url: Optional[str] = None


class DailyReportData(BaseModel):
    run_id: str
    date: str
    start_time: datetime
    end_time: datetime
    dry_run: bool = True
    jobs_scanned: int = 0
    salary_rejected: int = 0
    qualified_jobs: int = 0
    strong_matches: int = 0
    resumes_generated: int = 0
    applications_submitted: int = 0  # Total processed/attempted
    applications_confirmed: int = 0  # Confirmed on-platform (Level 1-5)
    applications_unverified: int = 0  # Submitted but unverified
    applications_external: int = 0  # External portal redirected
    applications_manual_intervention: int = 0  # Questions missing facts
    blocked_applications: int = 0  # Blocked by safety/auth/captcha
    failed_applications: int = 0  # Technical failures
    interview_packs_generated: int = 0
    profile_refresh_status: Optional[str] = None
    top_applications: List[TopApplicationItem] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class MarketTrendItem(BaseModel):
    item_name: str
    category: str  # skill, platform, architecture, role
    current_count: int
    previous_count: int
    trend: str  # INCREASING, DECREASING, STABLE, NEW, DISAPPEARING


class WeeklyIntelligenceData(BaseModel):
    run_id: str
    week_number: str
    date_range: str
    total_jobs_analyzed: int
    salary_stats: Dict[str, Any]
    trends: List[MarketTrendItem]
    top_companies: List[Dict[str, Any]]
    top_roles: List[Dict[str, Any]]
    recurring_skills: List[Dict[str, Any]]
    candidate_resume_gaps: List[str]
    recommended_learning: List[str]
    recommended_search_queries: List[str]
