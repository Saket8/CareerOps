"""SQLAlchemy database tables for career agent state persistence."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class JobModel(Base):
    __tablename__ = "jobs"

    job_id = Column(String(128), primary_key=True)
    title = Column(String(256), nullable=False)
    company = Column(String(256), nullable=False)
    location = Column(String(256), nullable=False)
    work_mode = Column(String(64), default="onsite")
    experience_min = Column(Float, nullable=True)
    experience_max = Column(Float, nullable=True)
    experience_raw = Column(String(128), default="")
    
    # Salary
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(16), default="INR")
    salary_period = Column(String(32), default="per_annum")
    salary_disclosed = Column(Boolean, default=False)
    salary_eligibility = Column(String(32), default="UNDISCLOSED")
    salary_raw_text = Column(String(256), default="")
    
    posted_date = Column(String(64), nullable=True)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    jd_text = Column(Text, default="")
    source_query = Column(String(256), default="")
    source_platform = Column(String(64), default="naukri")
    application_method = Column(String(64), default="standard")
    status = Column(String(64), default="DISCOVERED", index=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    score = relationship("JobScoreModel", back_populates="job", uselist=False, cascade="all, delete-orphan")
    evidence = relationship("JobEvidenceModel", back_populates="job", uselist=False, cascade="all, delete-orphan")
    applications = relationship("ApplicationModel", back_populates="job", cascade="all, delete-orphan")
    interview_packs = relationship("InterviewPackModel", back_populates="job", cascade="all, delete-orphan")
    failure_analyses = relationship("ApplicationFailureAnalysisModel", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_jobs_company_title", "company", "title"),
        Index("ix_jobs_salary_eligibility", "salary_eligibility"),
    )

    def to_listing(self):
        """Convert ORM model to JobListing domain model."""
        from src.models.job import JobListing, JobSalary, SalaryEligibility, JobStatus
        try:
            eligibility = SalaryEligibility(self.salary_eligibility)
        except Exception:
            eligibility = SalaryEligibility.UNDISCLOSED

        try:
            status = JobStatus(self.status)
        except Exception:
            status = JobStatus.DISCOVERED

        sal = JobSalary(
            min_lpa=self.salary_min,
            max_lpa=self.salary_max,
            currency=self.salary_currency or "INR",
            period=self.salary_period or "per_annum",
            is_disclosed=bool(self.salary_disclosed),
            eligibility=eligibility,
            raw_text=self.salary_raw_text or "Not Disclosed",
        )

        return JobListing(
            job_id=self.job_id,
            title=self.title,
            company=self.company,
            location=self.location,
            work_mode=self.work_mode or "onsite",
            experience_min=self.experience_min,
            experience_max=self.experience_max,
            experience_raw=self.experience_raw or "",
            salary=sal,
            posted_date=self.posted_date,
            url=self.url,
            canonical_url=self.canonical_url,
            jd_text=self.jd_text or "",
            has_full_jd=bool(self.jd_text and len(self.jd_text.strip()) >= 50),
            source_query=self.source_query or "",
            source_platform=self.source_platform or "naukri",
            application_method=self.application_method or "standard",
            status=status,
        )


class JobScoreModel(Base):
    __tablename__ = "job_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), ForeignKey("jobs.job_id"), unique=True, nullable=False)
    overall_score = Column(Float, nullable=False)
    architecture_score = Column(Float, default=0.0)
    cloud_score = Column(Float, default=0.0)
    oci_score = Column(Float, default=0.0)
    ai_score = Column(Float, default=0.0)
    agentic_ai_score = Column(Float, default=0.0)
    kubernetes_score = Column(Float, default=0.0)
    security_score = Column(Float, default=0.0)
    multicloud_score = Column(Float, default=0.0)
    experience_alignment = Column(Float, default=0.0)
    skill_alignment = Column(Float, default=0.0)
    passed_threshold = Column(Boolean, default=False)
    match_reasons = Column(JSON, default=list)
    strengths = Column(JSON, default=list)
    gaps = Column(JSON, default=list)
    categories = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="score")


class JobEvidenceModel(Base):
    __tablename__ = "job_evidence"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), ForeignKey("jobs.job_id"), unique=True, nullable=False)
    observed_facts = Column(JSON, default=list)
    inferred_signals = Column(JSON, default=list)
    generated_actions = Column(JSON, default=list)
    skills_found = Column(JSON, default=list)
    tools_found = Column(JSON, default=list)
    architecture_patterns = Column(JSON, default=list)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="evidence")


class ApplicationModel(Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("uq_applications_job_id", "job_id", unique=True),
    )

    application_id = Column(String(128), primary_key=True)
    job_id = Column(String(128), ForeignKey("jobs.job_id"), nullable=False, unique=True, index=True)
    resume_version_id = Column(String(128), ForeignKey("resume_versions.version_id"), nullable=True)
    resume_version = Column(String(128), nullable=True)
    application_method = Column(String(64), default="NAUKRI_DIRECT")
    source_job_url = Column(Text, default="")
    canonical_job_url = Column(Text, nullable=True)
    application_url = Column(Text, nullable=True)
    external_application_url = Column(Text, nullable=True)
    external_portal = Column(String(128), nullable=True)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    status = Column(String(64), default="APPLICATION_READY", index=True)
    questions_detected = Column(JSON, default=list)
    questions_answered = Column(JSON, default=dict)
    confirmation_detected = Column(Boolean, default=False)
    confirmation_text = Column(Text, nullable=True)
    confirmation_reference = Column(String(256), nullable=True)
    final_url = Column(Text, nullable=True)
    verification_method = Column(String(128), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    evidence_path = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    dry_run = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="applications")
    resume_version_rel = relationship("ResumeVersionModel")
    events = relationship("ApplicationEventModel", back_populates="application", cascade="all, delete-orphan")


class ApplicationEventModel(Base):
    __tablename__ = "application_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(String(128), ForeignKey("applications.application_id"), nullable=False)
    from_status = Column(String(64), nullable=False)
    to_status = Column(String(64), nullable=False)
    reason = Column(String(256), nullable=True)
    payload = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    application = relationship("ApplicationModel", back_populates="events")


class ResumeVersionModel(Base):
    __tablename__ = "resume_versions"

    version_id = Column(String(128), primary_key=True)
    job_id = Column(String(128), nullable=True, index=True)
    is_master = Column(Boolean, default=False)
    file_path_docx = Column(Text, nullable=True)
    file_path_pdf = Column(Text, nullable=True)
    checksum = Column(String(64), nullable=True)
    ats_score = Column(Float, default=0.0)
    ats_validation_details = Column(JSON, default=dict)
    tailoring_diff = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class InterviewPackModel(Base):
    __tablename__ = "interview_packs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), ForeignKey("jobs.job_id"), nullable=False)
    company = Column(String(256), nullable=False)
    role = Column(String(256), nullable=False)
    directory_path = Column(Text, nullable=False)
    question_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="interview_packs")


class MarketSignalModel(Base):
    __tablename__ = "market_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_date = Column(String(32), nullable=False, index=True)  # YYYY-MM-DD
    item_name = Column(String(128), nullable=False)
    category = Column(String(64), nullable=False)  # skill, platform, architecture, role
    frequency = Column(Integer, default=1)
    trend = Column(String(32), default="STABLE")  # INCREASING, DECREASING, STABLE, NEW, DISAPPEARING
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    run_id = Column(String(128), primary_key=True)
    run_type = Column(String(64), default="daily")  # daily, weekly, adhoc
    start_time = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    end_time = Column(DateTime, nullable=True)
    status = Column(String(64), default="RUNNING")
    dry_run = Column(Boolean, default=True)
    jobs_scanned = Column(Integer, default=0)
    salary_rejected = Column(Integer, default=0)
    qualified_jobs = Column(Integer, default=0)
    applications_submitted = Column(Integer, default=0)
    blocked_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    metadata_json = Column(JSON, default=dict)


class ApplicationFailureAnalysisModel(Base):
    __tablename__ = "application_failure_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(128), ForeignKey("jobs.job_id"), nullable=False, index=True)
    application_id = Column(String(128), nullable=True, index=True)
    run_id = Column(String(128), nullable=True, index=True)
    company = Column(String(256), nullable=False)
    job_title = Column(String(256), nullable=False)
    job_url = Column(Text, nullable=True)
    failure_status = Column(String(64), nullable=False, index=True)
    raw_failure_reason = Column(Text, nullable=True)
    screening_questions = Column(JSON, default=list)
    screening_answers = Column(JSON, default=dict)
    evidence_path = Column(Text, nullable=True)
    root_cause_category = Column(String(64), nullable=False, index=True)
    analysis_summary = Column(Text, nullable=False)
    self_healing_action = Column(String(64), nullable=True)
    self_healing_details = Column(JSON, default=dict)
    healing_status = Column(String(32), default="RESOLVED", index=True)
    retry_eligible = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    job = relationship("JobModel", back_populates="failure_analyses")
