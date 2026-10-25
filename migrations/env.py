"""Alembic environment for the asynchronous JalDrishti database URL."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from jaldrishti.persistence import metadata
from jaldrishti_api.config import get_settings
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = metadata
MANAGED_TABLE_NAMES = frozenset(table.name for table in target_metadata.tables.values())


def _include_name(
    name: str | None,
    type_: str,
    _parent_names: dict[str, str | None],
) -> bool:
    """Limit autogeneration to JalDrishti-owned tables.

    PostGIS installs extension-owned catalog and optional geocoder tables. They
    are intentionally outside application metadata and must never appear as
    destructive operations in an Alembic autogenerate/check run.
    """

    return type_ != "table" or name in MANAGED_TABLE_NAMES


def run_migrations_offline() -> None:
    """Generate SQL without creating an engine."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_name=_include_name,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_name=_include_name,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations through SQLAlchemy's async engine."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
