"""Migration-currency tests: Alembic head must match the ORM models.

Self-contained: upgrades run against a throwaway SQLite file, never
against Postgres.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import UniqueConstraint

import bizora.auth.models  # noqa: F401 (register tables for currency check)
import bizora.db.models  # noqa: F401 (register tables for currency check)
import bizora.queue.models  # noqa: F401 (register tables for currency check)
from bizora.core.config import get_settings
from bizora.db.base import Base

WORKTREE_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_HEAD = "0009_project_members"
EXPECTED_REVISION_COUNT = 9


def _script() -> ScriptDirectory:
    """Return the Alembic script directory for this checkout."""
    config = Config()
    config.set_main_option("script_location", str(WORKTREE_ROOT / "migrations"))
    return ScriptDirectory.from_config(config)


def test_chain_is_linear_with_single_head() -> None:
    script = _script()

    assert script.get_heads() == [EXPECTED_HEAD]

    revisions = list(script.walk_revisions())
    assert len(revisions) == EXPECTED_REVISION_COUNT
    by_revision = {revision.revision: revision for revision in revisions}

    bases = [r for r in revisions if r.down_revision is None]
    assert len(bases) == 1
    assert bases[0].revision == "0001_graph_revisions"

    parents: list[str] = []
    for revision in revisions:
        if revision.down_revision is None:
            continue
        assert isinstance(revision.down_revision, str)
        assert revision.down_revision in by_revision
        parents.append(revision.down_revision)
    assert len(set(parents)) == len(parents)


def test_upgrade_head_covers_all_models(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    db_path = tmp_path / "currency.db"
    monkeypatch.setenv("BIZORA_DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    get_settings.cache_clear()
    try:
        config = Config()
        config.set_main_option(
            "script_location", str(WORKTREE_ROOT / "migrations")
        )
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite+pysqlite:///{db_path}")
    try:
        inspector = inspect(engine)
        migrated = set(inspector.get_table_names()) - {"alembic_version"}
        assert migrated == set(Base.metadata.tables)

        for table_name, table in Base.metadata.tables.items():
            columns = inspector.get_columns(table_name)
            assert {c["name"] for c in columns} == set(table.columns.keys())
            for column in columns:
                expected = table.columns[column["name"]].nullable
                assert column["nullable"] == expected, (table_name, column["name"])

            migrated_indexes = {
                index["name"] for index in inspector.get_indexes(table_name)
            }
            for index in table.indexes:
                assert index.name in migrated_indexes, (table_name, index.name)

            migrated_uniques = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints(table_name)
            }
            for constraint in table.constraints:
                if isinstance(constraint, UniqueConstraint):
                    assert constraint.name in migrated_uniques, (
                        table_name,
                        constraint.name,
                    )
    finally:
        engine.dispose()


def test_index_backfill_revision_follows_extracted_tables() -> None:
    """Pin the regression: 0006 omitted the model-declared index."""
    script = _script()
    revisions = {r.revision: r for r in script.walk_revisions()}
    assert "0007_extracted_tables_index" in revisions
    assert (
        revisions["0007_extracted_tables_index"].down_revision
        == "0006_extracted_tables"
    )
