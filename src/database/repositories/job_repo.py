"""Job repository for storing and querying job listings, scores, and evidence."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.database.models import JobModel, JobScoreModel, JobEvidenceModel, ApplicationModel
from src.models.job import JobListing, JobStatus, SalaryEligibility
from src.models.score import JobScore, JobEvidence
from src.utils.logger import get_logger

logger = get_logger("job_repo")


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def exists(self, job_id: str) -> bool:
        """Check if job exists by ID."""
        return self.session.query(JobModel).filter(JobModel.job_id == job_id).first() is not None

    def exists_by_company_and_title(self, company: str, title: str) -> bool:
        """Check if similar job already exists to avoid near-duplicates."""
        return (
            self.session.query(JobModel)
            .filter(
                func.lower(JobModel.company) == company.lower().strip(),
                func.lower(JobModel.title) == title.lower().strip(),
            )
            .first()
            is not None
        )

    def is_already_applied(self, job_id: str) -> bool:
        """Check if job has already been applied to (APPLIED or APPLIED_CONFIRMED) in jobs or applications."""
        job = self.get(job_id)
        if job and job.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value):
            return True
        app = self.session.query(ApplicationModel).filter(ApplicationModel.job_id == job_id).first()
        if app and (
            app.status in (JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value)
            or app.confirmation_reference == "ALREADY_APPLIED"
        ):
            return True
        return False

    def has_applied_to_company_and_title(self, company: str, title: str) -> bool:
        """Check if candidate already applied to this specific role and company."""
        comp_norm = company.lower().strip()
        title_norm = title.lower().strip()
        job_match = (
            self.session.query(JobModel)
            .filter(
                func.lower(JobModel.company) == comp_norm,
                func.lower(JobModel.title) == title_norm,
                JobModel.status.in_([JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value]),
            )
            .first()
        )
        if job_match:
            return True

        app_match = (
            self.session.query(ApplicationModel)
            .join(JobModel, ApplicationModel.job_id == JobModel.job_id)
            .filter(
                func.lower(JobModel.company) == comp_norm,
                func.lower(JobModel.title) == title_norm,
                ApplicationModel.status.in_([JobStatus.APPLIED.value, JobStatus.APPLIED_CONFIRMED.value]),
            )
            .first()
        )
        return app_match is not None

    def get(self, job_id: str) -> Optional[JobModel]:
        """Fetch job by ID."""
        return self.session.query(JobModel).filter(JobModel.job_id == job_id).first()

    def save_job(self, job: JobListing) -> JobModel:
        """Create or update a job listing."""
        existing = self.get(job.job_id)
        if existing:
            existing.title = job.title
            existing.company = job.company
            existing.location = job.location
            existing.work_mode = job.work_mode
            existing.experience_min = job.experience_min
            existing.experience_max = job.experience_max
            existing.experience_raw = job.experience_raw
            existing.salary_min = job.salary.min_lpa
            existing.salary_max = job.salary.max_lpa
            existing.salary_disclosed = job.salary.is_disclosed
            existing.salary_eligibility = job.salary.eligibility.value
            existing.salary_raw_text = job.salary.raw_text
            existing.url = job.url
            existing.canonical_url = job.canonical_url
            existing.jd_text = job.jd_text
            existing.status = job.status.value
            self.session.flush()
            return existing

        db_job = JobModel(
            job_id=job.job_id,
            title=job.title,
            company=job.company,
            location=job.location,
            work_mode=job.work_mode,
            experience_min=job.experience_min,
            experience_max=job.experience_max,
            experience_raw=job.experience_raw,
            salary_min=job.salary.min_lpa,
            salary_max=job.salary.max_lpa,
            salary_currency=job.salary.currency,
            salary_period=job.salary.period,
            salary_disclosed=job.salary.is_disclosed,
            salary_eligibility=job.salary.eligibility.value,
            salary_raw_text=job.salary.raw_text,
            posted_date=job.posted_date,
            url=job.url,
            canonical_url=job.canonical_url,
            jd_text=job.jd_text,
            source_query=job.source_query,
            source_platform=job.source_platform,
            application_method=job.application_method,
            status=job.status.value,
        )
        self.session.add(db_job)
        self.session.flush()
        return db_job

    def update_status(self, job_id: str, status: JobStatus) -> None:
        """Update job status."""
        job = self.get(job_id)
        if job:
            job.status = status.value
            self.session.flush()

    def save_score(self, score: JobScore) -> JobScoreModel:
        """Save or update multidimensional score."""
        existing = self.session.query(JobScoreModel).filter(JobScoreModel.job_id == score.job_id).first()
        if existing:
            existing.overall_score = score.overall_score
            existing.architecture_score = score.architecture_score
            existing.cloud_score = score.cloud_score
            existing.oci_score = score.oci_score
            existing.ai_score = score.ai_score
            existing.agentic_ai_score = score.agentic_ai_score
            existing.kubernetes_score = score.kubernetes_score
            existing.security_score = score.security_score
            existing.multicloud_score = score.multicloud_score
            existing.experience_alignment = score.experience_alignment
            existing.skill_alignment = score.skill_alignment
            existing.passed_threshold = score.passed_threshold
            existing.match_reasons = score.match_reasons
            existing.strengths = score.strengths
            existing.gaps = score.gaps
            existing.categories = score.categories
            self.session.flush()
            return existing

        db_score = JobScoreModel(
            job_id=score.job_id,
            overall_score=score.overall_score,
            architecture_score=score.architecture_score,
            cloud_score=score.cloud_score,
            oci_score=score.oci_score,
            ai_score=score.ai_score,
            agentic_ai_score=score.agentic_ai_score,
            kubernetes_score=score.kubernetes_score,
            security_score=score.security_score,
            multicloud_score=score.multicloud_score,
            experience_alignment=score.experience_alignment,
            skill_alignment=score.skill_alignment,
            passed_threshold=score.passed_threshold,
            match_reasons=score.match_reasons,
            strengths=score.strengths,
            gaps=score.gaps,
            categories=score.categories,
        )
        self.session.add(db_score)
        self.session.flush()
        return db_score

    def save_evidence(self, evidence: JobEvidence) -> JobEvidenceModel:
        """Save or update structured evidence."""
        existing = self.session.query(JobEvidenceModel).filter(JobEvidenceModel.job_id == evidence.job_id).first()
        if existing:
            existing.observed_facts = evidence.observed_facts
            existing.inferred_signals = evidence.inferred_signals
            existing.generated_actions = evidence.generated_actions
            existing.skills_found = evidence.skills_found
            existing.tools_found = evidence.tools_found
            existing.architecture_patterns = evidence.architecture_patterns
            self.session.flush()
            return existing

        db_evidence = JobEvidenceModel(
            job_id=evidence.job_id,
            observed_facts=evidence.observed_facts,
            inferred_signals=evidence.inferred_signals,
            generated_actions=evidence.generated_actions,
            skills_found=evidence.skills_found,
            tools_found=evidence.tools_found,
            architecture_patterns=evidence.architecture_patterns,
        )
        self.session.add(db_evidence)
        self.session.flush()
        return db_evidence

    def get_score(self, job_id: str) -> Optional[JobScoreModel]:
        """Fetch score by job ID."""
        return self.session.query(JobScoreModel).filter(JobScoreModel.job_id == job_id).first()

    def get_evidence(self, job_id: str) -> Optional[JobEvidenceModel]:
        """Fetch evidence by job ID."""
        return self.session.query(JobEvidenceModel).filter(JobEvidenceModel.job_id == job_id).first()

    def get_jobs_by_status(self, status: JobStatus) -> List[JobModel]:
        """Fetch all jobs matching a specific status."""
        return self.session.query(JobModel).filter(JobModel.status == status.value).all()

    def get_all_jobs(self) -> List[JobModel]:
        """Fetch all jobs."""
        return self.session.query(JobModel).all()
