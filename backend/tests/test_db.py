import subprocess
import sys
import textwrap

import pytest

from app.db import Database, DatabaseLockedError, apply_migrations


def test_migrations_idempotent(db: Database, settings) -> None:
    assert apply_migrations(db.cursor(), settings.migrations_dir) == []
    versions = db.cursor().execute("SELECT version FROM schema_migrations").fetchall()
    assert ("001_init",) in versions
    db.cursor().execute("SELECT count(*) FROM jobs").fetchone()


def test_extensions_loaded(db: Database) -> None:
    loaded = {
        r[0]
        for r in db.cursor()
        .execute("SELECT extension_name FROM duckdb_extensions() WHERE loaded")
        .fetchall()
    }
    assert {"vss", "fts"} <= loaded


def test_locked_file_gives_clear_error(tmp_path) -> None:
    path = tmp_path / "busy.duckdb"
    holder = textwrap.dedent(f"""
        import duckdb, sys, time
        c = duckdb.connect({str(path)!r})
        print("ready", flush=True)
        sys.stdin.readline()
    """)
    proc = subprocess.Popen(
        [sys.executable, "-c", holder], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
        with pytest.raises(DatabaseLockedError, match="Uygulama"):
            Database(path).connect()
    finally:
        proc.communicate("\n", timeout=10)
