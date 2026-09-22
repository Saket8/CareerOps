"""Interview repository for storing generated interview preparation packs."""

from typing import Optional, List
from sqlalchemy.orm import Session

from src.database.models import InterviewPackModel


class InterviewRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_job_id(self, job_id: str) -> Optional[InterviewPackModel]:
        return self.session.query(InterviewPackModel).filter(InterviewPackModel.job_id == job_id).first()

    def save_pack(self, job_id: str, company: str, role: str, directory_path: str, question_count: int) -> InterviewPackModel:
        pack = InterviewPackModel(
            job_id=job_id,
            company=company,
            role=role,
            directory_path=directory_path,
            question_count=question_count,
        )
        self.session.add(pack)
        self.session.flush()
        return pack

    def get_all_packs(self) -> List[InterviewPackModel]:
        return self.session.query(InterviewPackModel).order_by(InterviewPackModel.created_at.desc()).all()
