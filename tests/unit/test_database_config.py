"""Regression tests for unified database target resolution.

Canonical source: bizora.core.config.Settings. Precedence:
BIZORA_DATABASE_URL (any source) > DATABASE_URL (legacy process-env
override) > built-in default. The application engine and Alembic must
resolve the same target.
"""

import os
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from bizora.core.config import DEFAULT_DATABASE_URL, Settings

REPO_ROOT = Path(__file__).parent.parent.parent


def make_settings(monkeypatch: pytest.MonkeyPatch, **env: str | None) -> Settings:
    """Build settings with an isolated database environment."""
    for var in ("BIZORA_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        if value is None:
            continue
        monkeypatch.setenv(var, value)
    return Settings(_env_file=None)


def test_default_database_url_when_nothing_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(monkeypatch)

    assert settings.database_url == DEFAULT_DATABASE_URL


def test_primary_url_wins_over_legacy_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.warns(UserWarning, match="BIZORA_DATABASE_URL"):
        settings = make_settings(
            monkeypatch,
            BIZORA_DATABASE_URL="sqlite+pysqlite:////tmp/primary.db",
            DATABASE_URL="sqlite+pysqlite:////tmp/legacy.db",
        )

    assert settings.database_url == "sqlite+pysqlite:////tmp/primary.db"


def test_matching_urls_do_not_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        settings = make_settings(
            monkeypatch,
            BIZORA_DATABASE_URL="sqlite+pysqlite:////tmp/same.db",
            DATABASE_URL="sqlite+pysqlite:////tmp/same.db",
        )

    assert settings.database_url == "sqlite+pysqlite:////tmp/same.db"
    assert [w for w in caught if "DATABASE_URL" in str(w.message)] == []


def test_legacy_url_applies_when_primary_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(monkeypatch, DATABASE_URL="sqlite+pysqlite:////tmp/legacy.db")

    assert settings.database_url == "sqlite+pysqlite:////tmp/legacy.db"


def test_blank_legacy_url_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(monkeypatch, DATABASE_URL="   ")

    assert settings.database_url == DEFAULT_DATABASE_URL


def test_blank_primary_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="must not be empty"):
        make_settings(monkeypatch, BIZORA_DATABASE_URL="  ")


def test_invalid_primary_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="valid SQLAlchemy database URL"):
        make_settings(monkeypatch, BIZORA_DATABASE_URL="not-a-database-url")


def test_invalid_legacy_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError, match="valid SQLAlchemy database URL"):
        make_settings(monkeypatch, DATABASE_URL="not-a-database-url")


def test_error_messages_never_echo_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(
            monkeypatch,
            BIZORA_DATABASE_URL="://admin:sup3r-s3cret@db/x",
        )

    assert "sup3r-s3cret" not in str(exc_info.value)


def _run_alembic(
    tmp_path: Path, *args: str, extra_env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run alembic hermetically: no .env pickup, repo config by path."""
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "src"),
        **extra_env,
    }
    env.pop("BIZORA_DATABASE_URL", None)
    env.pop("DATABASE_URL", None)
    env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(REPO_ROOT / "alembic.ini"),
            *args,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _has_table(db_path: Path, table: str) -> bool:
    import sqlite3

    if not db_path.exists():
        return False
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def test_alembic_applies_to_legacy_url_target(tmp_path: Path) -> None:
    """The real Alembic path must honor DATABASE_URL when primary is unset."""
    target = tmp_path / "legacy.db"

    result = _run_alembic(
        tmp_path,
        "upgrade",
        "head",
        extra_env={"DATABASE_URL": f"sqlite+pysqlite:///{target}"},
    )

    assert result.returncode == 0, result.stderr[-1000:]
    assert _has_table(target, "graph_revisions")
    assert _has_table(target, "metric_records")


def test_alembic_prefers_primary_over_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """App and Alembic must agree on BIZORA_DATABASE_URL when both are set."""
    primary = tmp_path / "primary.db"
    legacy = tmp_path / "legacy.db"

    result = _run_alembic(
        tmp_path,
        "upgrade",
        "head",
        extra_env={
            "BIZORA_DATABASE_URL": f"sqlite+pysqlite:///{primary}",
            "DATABASE_URL": f"sqlite+pysqlite:///{legacy}",
        },
    )

    assert result.returncode == 0, result.stderr[-1000:]
    assert _has_table(primary, "graph_revisions")
    assert not legacy.exists()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        settings = make_settings(
            monkeypatch,
            BIZORA_DATABASE_URL=f"sqlite+pysqlite:///{primary}",
            DATABASE_URL=f"sqlite+pysqlite:///{legacy}",
        )
    assert settings.database_url == f"sqlite+pysqlite:///{primary}"
