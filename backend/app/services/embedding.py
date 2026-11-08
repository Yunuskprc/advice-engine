"""Film embedding hattı: metni üretir, Ollama'dan vektörü alır, normalize edip yazar."""

from collections.abc import Callable
from dataclasses import dataclass

import duckdb
import numpy as np

from app.clients.ollama import LlmClient
from app.config import AppSettings, RecommenderSettings
from app.db import Database


@dataclass(frozen=True)
class EmbedRow:
    tmdb_id: int
    title_original: str
    title_tr: str
    year: int | None
    overview_en: str | None
    overview_tr: str | None
    genres: list[str]
    keywords: list[str]
    directors: list[str]


def build_embed_text(row: EmbedRow, max_keywords: int) -> str:
    year = row.year if row.year is not None else ""
    overview = row.overview_en or row.overview_tr or ""
    return (
        f"Başlık: {row.title_original} ({row.title_tr}), {year}\n"
        f"Türler: {', '.join(row.genres)}\n"
        f"Etiketler: {', '.join(row.keywords[:max_keywords])}\n"
        f"Yönetmen: {', '.join(row.directors)}\n"
        f"Özet: {overview}"
    )


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Satır vektörlerini birim uzunluğa getirir; sıfır vektör olduğu gibi kalır."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def fetch_pending(cur: duckdb.DuckDBPyConnection, limit: int) -> list[EmbedRow]:
    """Embedding bekleyen filmleri popülerlik sırasıyla döndürür. Keyword'ler nadirden yaygına."""
    rows = cur.execute(
        "SELECT m.tmdb_id, m.title_original, m.title_tr, year(m.release_date),"
        " m.overview_en, m.overview_tr,"
        " (SELECT list(g.name_tr ORDER BY g.name_tr) FROM movie_genre mg"
        "   JOIN genres g ON g.id = mg.genre_id WHERE mg.movie_id = m.tmdb_id),"
        " (SELECT list(k.name ORDER BY k.df, k.id) FROM movie_keyword mk"
        "   JOIN keywords k ON k.id = mk.keyword_id WHERE mk.movie_id = m.tmdb_id),"
        " (SELECT list(p.name ORDER BY p.name) FROM movie_person mp"
        "   JOIN people p ON p.id = mp.person_id"
        "   WHERE mp.movie_id = m.tmdb_id AND mp.role = 'director')"
        " FROM movies m WHERE m.embedding_stale"
        " ORDER BY m.popularity DESC NULLS LAST, m.tmdb_id LIMIT ?",
        [limit],
    ).fetchall()
    return [
        EmbedRow(r[0], r[1], r[2], r[3], r[4], r[5], r[6] or [], r[7] or [], r[8] or [])
        for r in rows
    ]


def store_embeddings(cur: duckdb.DuckDBPyConnection, ids: list[int], vectors: np.ndarray) -> None:
    cur.execute(
        "UPDATE movies SET embedding = v.e, embedding_stale = FALSE"
        " FROM (SELECT unnest(?::BIGINT[]) AS id, unnest(?::FLOAT[1024][]) AS e) v"
        " WHERE movies.tmdb_id = v.id",
        [ids, vectors.tolist()],
    )


def embed_pending(
    db: Database,
    llm: LlmClient,
    settings: AppSettings,
    rec: RecommenderSettings,
    on_total: Callable[[int], None],
    on_progress: Callable[[int], None],
) -> int:
    """Bekleyen tüm filmleri işler. Yarıda kesilirse sonraki çalıştırma kaldığı yerden sürer."""
    cur = db.cursor()
    row = cur.execute("SELECT count(*) FROM movies WHERE embedding_stale").fetchone()
    on_total(int(row[0]) if row else 0)
    done = 0
    while rows := fetch_pending(cur, settings.embed_batch_size):
        texts = [build_embed_text(r, rec.embed_max_keywords) for r in rows]
        vectors = np.asarray(llm.embed(settings.ollama_embed_model, texts), dtype=np.float32)
        if vectors.shape != (len(rows), settings.embedding_dim):
            raise ValueError(
                f"Beklenmeyen embedding boyutu: {vectors.shape}, "
                f"beklenen ({len(rows)}, {settings.embedding_dim})"
            )
        store_embeddings(cur, [r.tmdb_id for r in rows], l2_normalize(vectors))
        done += len(rows)
        on_progress(done)
    return done


def embedding_status(cur: duckdb.DuckDBPyConnection) -> tuple[int, int]:
    """(toplam film, embedding'i hazır film) döndürür."""
    row = cur.execute(
        "SELECT count(*), count(*) FILTER (WHERE embedding IS NOT NULL AND NOT embedding_stale)"
        " FROM movies"
    ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])
