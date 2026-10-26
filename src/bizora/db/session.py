
"""Database engine and session lifecycle management."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from bizora.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create the process-wide engine on first use."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the shared factory for database sessions."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db_session() -> Iterator[Session]:
    """Yield a session and always close it after use."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()