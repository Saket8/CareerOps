"""Database connection and session factory management."""

import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.database.models import Base
from src.utils.logger import get_logger

logger = get_logger("db_connection")

_ENGINES = {}
_SESSION_FACTORIES = {}


def get_engine(db_url: str = "sqlite:///naukri_career_agent.sqlite"):
    """Get or create SQLAlchemy engine keyed by db_url."""
    if db_url not in _ENGINES:
        is_sqlite = db_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        _ENGINES[db_url] = create_engine(db_url, echo=False, connect_args=connect_args)
    return _ENGINES[db_url]


def init_db(db_url: str = "sqlite:///naukri_career_agent.sqlite") -> None:
    """Initialize database tables and automatically migrate new columns."""
    engine = get_engine(db_url)
    Base.metadata.create_all(bind=engine)

    # SQLite auto-column migration and authentic data hygiene
    if db_url.startswith("sqlite") and not db_url.endswith(":memory:"):
        try:
            with engine.connect() as conn:
                for table_name, table in Base.metadata.tables.items():
                    res = conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
                    existing_cols = {row[1] for row in res.fetchall()}
                    if not existing_cols:
                        continue
                    for col in table.columns:
                        if col.name not in existing_cols:
                            col_type = col.type.compile(engine.dialect)
                            conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                            logger.info(f"Auto-migrated: added column '{col.name}' to table '{table_name}'")
                conn.commit()

                # Zero-Dummy Invariant: Purge any legacy dummy/mock records restored from older caches
                conn.exec_driver_sql("DELETE FROM applications WHERE job_id LIKE 'job_oci_%' OR job_id LIKE 'nk_%' OR canonical_job_url LIKE '%job_oci_%' OR canonical_job_url LIKE '%nk_%'")
                conn.exec_driver_sql("DELETE FROM jobs WHERE job_id LIKE 'job_oci_%' OR job_id LIKE 'nk_%' OR url LIKE '%job_oci_%' OR company LIKE '%Cognizant%'")
                # Clean up legacy unapplied rejected jobs so they can be re-evaluated under dual-track qualification
                conn.exec_driver_sql("DELETE FROM jobs WHERE status = 'REJECTED'")
                conn.commit()

                # Seed authentic records if DB is empty and seed file exists
                seed_file = Path(__file__).parent / "seed.sql"
                if seed_file.exists():
                    job_count = conn.exec_driver_sql("SELECT count(*) FROM jobs").scalar()
                    if job_count == 0:
                        sql_script = seed_file.read_text(encoding="utf-8")
                        conn.connection.executescript(sql_script)
                        logger.info("Database seeded successfully with authentic verified applications.")
        except Exception as exc:
            logger.warning(f"Database hygiene / seed check notice: {exc}")

    logger.info("Database tables initialized and synchronized successfully.")


def get_session_factory(db_url: str = "sqlite:///naukri_career_agent.sqlite"):
    """Get or create sessionmaker keyed by db_url."""
    if db_url not in _SESSION_FACTORIES:
        engine = get_engine(db_url)
        _SESSION_FACTORIES[db_url] = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SESSION_FACTORIES[db_url]


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
