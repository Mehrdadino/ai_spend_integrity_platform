"""Alembic migration environment: loads app models and runs online/offline migrations.

``sys.path`` is adjusted so ``app.*`` imports resolve when Alembic is invoked
from the ``backend/`` directory. Importing all models registers tables on
``Base.metadata`` for autogenerate / revision scripts.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models import Bill, BillLineItem, Document, DocumentRawExtraction, Organization, Site, User  # noqa: E402, F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """DSN for migrations (same as runtime ``Settings.database_url``)."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Generate SQL to stdout / file without connecting (rare for this project)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in a single connection with NullPool (Alembic default pattern)."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
