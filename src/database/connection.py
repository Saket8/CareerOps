"""Database connection and session factory management."""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.database.models import Base
from src.utils.logger import get_logger

logger = get_logger("db_connection")

_ENGINE = None
_SESSION_FACTORY = None


def get_engine(db_url: str = "sqlite:///naukri_career_agent.sqlite"):
    """Get or create singleton SQLAlchemy engine."""
    global _ENGINE
    if _ENGINE is None:
        is_sqlite = db_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        _ENGINE = create_engine(db_url, echo=False, connect_args=connect_args)
    return _ENGINE


def init_db(db_url: str = "sqlite:///naukri_career_agent.sqlite") -> None:
    """Initialize database tables."""
    engine = get_engine(db_url)
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables initialized successfully.")


def get_session_factory(db_url: str = "sqlite:///naukri_career_agent.sqlite"):
    """Get or create sessionmaker."""
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        engine = get_engine(db_url)
        _SESSION_FACTORY = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SESSION_FACTORY


@contextmanager
def get_db_session(db_url: str = "sqlite:///naukri_career_agent.sqlite") -> Generator[Session, None, None]:
    """Context manager for scoped database sessions."""
    session_factory = get_session_factory(db_url)
    session: Session = session_factory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database transaction error: {exc}")
        raise
    finally:
        session.close()
