"""`film` komut satırı aracı."""

import time
from typing import Annotated

import typer
from rich.console import Console

from app.clients.ollama import OllamaClient, has_model
from app.config import PROJECT_ROOT, get_settings
from app.db import Database, DatabaseLockedError, apply_migrations

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


def _open_db() -> Database:
    s = get_settings()
    db = Database(s.db_path, s.duckdb_extensions)
    try:
        db.connect()
    except DatabaseLockedError as e:
        console.print(f"[bold red]Hata:[/] {e}")
        raise typer.Exit(1) from e
    return db


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Örn. 0.0.0.0 (LAN erişimi)")] = None,
    port: Annotated[int | None, typer.Option()] = None,
    reload: Annotated[bool, typer.Option(help="Geliştirme modu")] = False,
) -> None:
    """FastAPI sunucusunu başlatır."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=host or s.app_host,
        port=port or s.app_port,
        reload=reload,
        reload_dirs=[str(PROJECT_ROOT / "backend")] if reload else None,
    )


@app.command()
def migrate() -> None:
    """Bekleyen migration'ları uygular."""
    db = _open_db()
    try:
        done = apply_migrations(db.cursor(), get_settings().migrations_dir)
    finally:
        db.close()
    if done:
        console.print("[green]Uygulandı:[/] " + ", ".join(done))
    else:
        console.print("Bekleyen migration yok.")


@app.command("import-catalog")
def import_catalog() -> None:
    """TMDB katalog importu (uygulama kapalıyken çalışır)."""
    db = _open_db()
    try:
        apply_migrations(db.cursor(), get_settings().migrations_dir)
        console.print(
            "[yellow]Katalog importu Faz 1'de eklenecek.[/] Veritabanı yazılabilir durumda."
        )
    finally:
        db.close()


@app.command("ollama-ping")
def ollama_ping() -> None:
    """Embedding ve sohbet modelinden cevap alınabildiğini doğrular."""
    s = get_settings()
    client = OllamaClient(s.ollama_url, s.ollama_timeout_s)
    try:
        models = client.list_models(timeout=s.ollama_health_timeout_s)
    except Exception as e:
        console.print(f"[bold red]Ollama'ya ulaşılamadı[/] ({s.ollama_url}): {type(e).__name__}")
        raise typer.Exit(1) from e

    failed = False
    for m in (s.ollama_embed_model, s.ollama_chat_model):
        if not has_model(models, m):
            console.print(f"[red]✗ Model yüklü değil:[/] {m}  →  ollama pull {m}")
            failed = True
    if failed:
        raise typer.Exit(1)

    t = time.perf_counter()
    try:
        vec = client.embed(s.ollama_embed_model, ["Esaretin Bedeli (1994)"])[0]
    except Exception as e:
        console.print(f"[red]✗ Embedding hatası:[/] {e}")
        raise typer.Exit(1) from e
    dt = time.perf_counter() - t
    dim_ok = len(vec) == s.embedding_dim
    mark = "[green]✓[/]" if dim_ok else "[red]✗[/]"
    console.print(
        f"{mark} {s.ollama_embed_model}: {len(vec)} boyut (beklenen {s.embedding_dim}), {dt:.2f} sn"
    )

    t = time.perf_counter()
    try:
        answer = client.generate(
            s.ollama_chat_model,
            "Tek kelimeyle cevap ver: Türkiye'nin başkenti neresi?",
            max_tokens=s.ollama_ping_max_tokens,
        )
    except Exception as e:
        console.print(f"[red]✗ Sohbet modeli hatası:[/] {e}")
        raise typer.Exit(1) from e
    dt = time.perf_counter() - t
    console.print(f"[green]✓[/] {s.ollama_chat_model}: {answer.strip()!r}, {dt:.2f} sn")

    if not dim_ok:
        raise typer.Exit(1)
