"""
Alembic migration environment — async SQLAlchemy setup.
Why async: Our entire stack uses asyncpg. Running sync migrations
against an async engine causes driver conflicts.
"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from core.config import get_settings
from db.base_model import Base

# Load our models so Alembic can detect schema changes
import db.models  # noqa: F401 — registers all models against Base.metadata

# Alembic config
alembic_config = context.config
settings = get_settings()

# Override sqlalchemy.url with our dynamic settings
alembic_config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up logging from alembic.ini
if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)

# Target our Base metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations without a live DB connection.
    Why: Useful for generating SQL scripts to review before applying.
    """
    url = alembic_config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,      # Detect column type changes
        compare_server_default=True,  # Detect default value changes
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations against async engine.
    Why async_engine_from_config: asyncpg requires an async engine.
    Alembic runs sync under the hood via run_sync().
    """
    connectable = async_engine_from_config(
        alembic_config.get_section(alembic_config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()