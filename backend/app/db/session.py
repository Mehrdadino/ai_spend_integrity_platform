"""Database engine and FastAPI session dependency.

Uses a module-level singleton engine/factory pattern suitable for a single
worker process. ``get_db`` commits on successful request completion and rolls
back on any exception so routes do not leak partial transactions.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_engine = None
_SessionLocal = None


def get_engine():
    """Lazily create the SQLAlchemy engine (sync ``psycopg2`` URL)."""
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,  # Drop dead connections before checkout.
        )
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _engine


def get_session_factory():
    """Return the bound session factory (initializes engine if needed)."""
    get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield one Session per request; commit or rollback."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
