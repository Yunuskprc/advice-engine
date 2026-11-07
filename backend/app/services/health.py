"""DuckDB ve Ollama durum kontrolü."""

from app.api.schemas import DbHealth, HealthResponse, OllamaHealth
from app.clients.ollama import LlmClient, has_model
from app.config import AppSettings
from app.db import Database


def check_db(db: Database) -> DbHealth:
    try:
        cur = db.cursor()
        version = cur.execute("SELECT version()").fetchone()[0]  # type: ignore[index]
        loaded = [
            r[0]
            for r in cur.execute(
                "SELECT extension_name FROM duckdb_extensions() WHERE loaded ORDER BY 1"
            ).fetchall()
        ]
        migrations = [
            r[0] for r in cur.execute("SELECT version FROM schema_migrations ORDER BY 1").fetchall()
        ]
        return DbHealth(
            ok=True, version=version, extensions=loaded, migrations=migrations, path=str(db.path)
        )
    except Exception as e:
        return DbHealth(ok=False, error=f"{type(e).__name__}: {e}", path=str(db.path))


def check_ollama(client: LlmClient, settings: AppSettings) -> OllamaHealth:
    base = OllamaHealth(
        ok=False,
        url=settings.ollama_url,
        embed_model=settings.ollama_embed_model,
        chat_model=settings.ollama_chat_model,
    )
    try:
        models = client.list_models(timeout=settings.ollama_health_timeout_s)
    except Exception as e:
        base.error = f"Ollama'ya ulaşılamadı: {type(e).__name__}"
        return base
    base.reachable = True
    base.embed_model_present = has_model(models, settings.ollama_embed_model)
    base.chat_model_present = has_model(models, settings.ollama_chat_model)
    base.ok = base.embed_model_present and base.chat_model_present
    if not base.ok:
        missing = [
            m
            for m, present in (
                (settings.ollama_embed_model, base.embed_model_present),
                (settings.ollama_chat_model, base.chat_model_present),
            )
            if not present
        ]
        base.error = "Eksik model: " + ", ".join(missing)
    return base


def check_health(db: Database, client: LlmClient, settings: AppSettings) -> HealthResponse:
    db_h = check_db(db)
    ol_h = check_ollama(client, settings)
    return HealthResponse(ok=db_h.ok and ol_h.ok, db=db_h, ollama=ol_h)
