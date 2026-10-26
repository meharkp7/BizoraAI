"""Alembic migration environment for Bizora."""



import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from bizora.core.config import get_settings
from bizora.db.base import Base
from bizora.db.models import GraphRevisionRecord

config = context.config
settings = get_settings()

# Allow a one-command database override for local migration checks.
migration_url = os.environ.get("DATABASE_URL", settings.database_url)

config.set_main_option(
    "sqlalchemy.url",
    migration_url.replace("%", "%%"),
)

target_metadata = GraphRevisionRecord.metadata

config = context.config
settings = get_settings()

# Escape percent signs for ConfigParser interpolation.
config.set_main_option(
    "sqlalchemy.url",
    migration_url.replace("%", "%%"),
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=migration_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()