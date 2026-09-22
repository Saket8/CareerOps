"""Resume repository for tracking master and tailored ATS resume versions."""

from typing import Optional, List
from sqlalchemy.orm import Session

from src.database.models import ResumeVersionModel


class ResumeRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_version_id(self, version_id: str) -> Optional[ResumeVersionModel]:
        return self.session.query(ResumeVersionModel).filter(ResumeVersionModel.version_id == version_id).first()

    def get_by_job_id(self, job_id: str) -> Optional[ResumeVersionModel]:
        return (
            self.session.query(ResumeVersionModel)
            .filter(ResumeVersionModel.job_id == job_id)
            .order_by(ResumeVersionModel.created_at.desc())
            .first()
        )

    def save_version(
        self,
        version_id: str,
        job_id: Optional[str] = None,
        is_master: bool = False,
        file_path_docx: Optional[str] = None,
        file_path_pdf: Optional[str] = None,
        checksum: Optional[str] = None,
        ats_score: float = 0.0,
        ats_validation_details: Optional[dict] = None,
        tailoring_diff: Optional[dict] = None,
    ) -> ResumeVersionModel:
        version = self.get_by_version_id(version_id)
        if version:
            version.job_id = job_id
            version.is_master = is_master
            version.file_path_docx = file_path_docx
            version.file_path_pdf = file_path_pdf
            version.checksum = checksum
            version.ats_score = ats_score
            version.ats_validation_details = ats_validation_details or {}
            version.tailoring_diff = tailoring_diff or {}
        else:
            version = ResumeVersionModel(
                version_id=version_id,
                job_id=job_id,
                is_master=is_master,
                file_path_docx=file_path_docx,
                file_path_pdf=file_path_pdf,
                checksum=checksum,
                ats_score=ats_score,
                ats_validation_details=ats_validation_details or {},
                tailoring_diff=tailoring_diff or {},
            )
            self.session.add(version)
        self.session.flush()
        return version
