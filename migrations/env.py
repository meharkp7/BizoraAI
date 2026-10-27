"""Alembic migration environment for Bizora."""

from alembic import context
from sqlalchemy import engine_from_config, pool

from bizora.core.config import get_settings
from bizora.db.base import Base
from bizora.db.models import GraphRevisionRecord  # noqa: F401 (registers tables)

config = context.config
settings = get_settings()

# Canonical target shared with the application: Settings applies the
# documented precedence (BIZORA_DATABASE_URL > DATABASE_URL > default), so
# Alembic can never resolve a different database than the application.
migration_url = settings.database_url

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