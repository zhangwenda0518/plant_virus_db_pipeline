"""SQLAlchemy engine + session context manager."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from neblab_rag.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        get_settings().postgres_dsn,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


@contextmanager
def get_session() -> Generator[Session]:
    sm = sessionmaker(bind=get_engine(), expire_on_commit=False)
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
