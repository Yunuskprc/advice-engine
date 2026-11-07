"""Düz SQL migration runner. Uygulananlar schema_migrations tablosunda tutulur."""

from pathlib import Path

import duckdb


def apply_migrations(cur: duckdb.DuckDBPyConnection, migrations_dir: Path) -> list[str]:
    """Henüz uygulanmamış migration'ları sırayla uygular, uygulananların adını döndürür."""
    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version VARCHAR PRIMARY KEY,"
        " applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp)"
    )
    applied = {row[0] for row in cur.execute("SELECT version FROM schema_migrations").fetchall()}
    done: list[str] = []
    for f in sorted(migrations_dir.glob("*.sql")):
        if f.stem in applied:
            continue
        cur.execute("BEGIN TRANSACTION")
        try:
            cur.execute(f.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (version) VALUES (?)", [f.stem])
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        done.append(f.stem)
    return done
