"""SQLAlchemy declarative base shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root class for metadata and mapper configuration (see ``alembic/env.py``)."""

    pass
