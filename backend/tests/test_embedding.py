import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import RecommenderSettings
from app.main import create_app
from app.services.embedding import (
    EmbedRow,
    build_embed_text,
    embed_pending,
    embedding_status,
    l2_normalize,
)
from app.services.similar import similar_movies
from tests.conftest import FakeLlm

DIM = 1024


def _vec(*head: float) -> list[float]:
    return list(head) + [0.0] * (DIM - len(head))


class CountingLlm(FakeLlm):
    def __init__(self) -> None:
        super().__init__()
        self.batches: list[int] = []

    def embed(self, model: str, inputs: list[str]) -> list[list[float]]:
        self.batches.append(len(inputs))
        return [_vec(3.0, 4.0) for _ in inputs]


@pytest.fixture
def rec() -> RecommenderSettings:
    return RecommenderSettings(_env_file=None)


def _add_movie(cur, tmdb_id: int, vector: list[float] | None = None) -> None:
    cur.execute(
        "INSERT INTO movies (tmdb_id, title_tr, title_original, embedding, embedding_stale,"
        " synced_at) VALUES (?, ?, ?, ?::FLOAT[1024], ?, current_timestamp::TIMESTAMP)",
        [tmdb_id, f"Film {tmdb_id}", f"Movie {tmdb_id}", vector, vector is None],
    )


def _row(**over) -> EmbedRow:
    base = {
        "tmdb_id": 1,
        "title_original": "Inception",
        "title_tr": "Başlangıç",
        "year": 2010,
        "overview_en": "Dreams.",
        "overview_tr": "Rüyalar.",
        "genres": ["Aksiyon"],
        "keywords": ["k1", "k2", "k3"],
        "directors": ["Christopher Nolan"],
    }
    return EmbedRow(**{**base, **over})


def test_embed_text_follows_template() -> None:
    assert build_embed_text(_row(), max_keywords=2) == (
        "Başlık: Inception (Başlangıç), 2010\n"
        "Türler: Aksiyon\n"
        "Etiketler: k1, k2\n"
        "Yönetmen: Christopher Nolan\n"
        "Özet: Dreams."
    )


def test_embed_text_falls_back_to_turkish_overview() -> None:
    assert build_embed_text(_row(overview_en=None), 20).endswith("Özet: Rüyalar.")


def test_l2_normalize() -> None:
    out = l2_normalize(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert out[0] == pytest.approx([0.6, 0.8])
    assert out[1] == pytest.approx([0.0, 0.0])


def test_embed_pending_batches_and_resumes(db, settings, rec) -> None:
    cur = db.cursor()
    for i in range(1, 6):
        _add_movie(cur, i)
    llm = CountingLlm()
    settings = settings.model_copy(update={"embed_batch_size": 2})
    totals: list[int] = []
    progress: list[int] = []

    assert embed_pending(db, llm, settings, rec, totals.append, progress.append) == 5
    assert llm.batches == [2, 2, 1]
    assert totals == [5] and progress == [2, 4, 5]
    assert embedding_status(cur) == (5, 5)
    stored = cur.execute("SELECT embedding FROM movies WHERE tmdb_id = 1").fetchone()[0]
    assert stored[:2] == pytest.approx((0.6, 0.8))

    llm.batches.clear()
    assert embed_pending(db, llm, settings, rec, totals.append, progress.append) == 0
    assert llm.batches == []


def test_similar_orders_by_cosine_and_excludes_self(db) -> None:
    cur = db.cursor()
    _add_movie(cur, 1, _vec(1.0, 0.0))
    _add_movie(cur, 2, _vec(0.0, 1.0))
    _add_movie(cur, 3, _vec(0.8, 0.6))
    _add_movie(cur, 4)  # embedding'siz film sonuçlara girmez

    result = similar_movies(db, 1, limit=10)
    assert [m.tmdb_id for m in result] == [3, 2]
    assert result[0].similarity == pytest.approx(0.8, abs=1e-5)


def test_similar_endpoint_errors_and_status(settings) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        cur = client.app.state.db.cursor()
        _add_movie(cur, 1)
        assert client.get("/api/movies/999/similar").status_code == 404
        assert client.get("/api/movies/1/similar").status_code == 409
        assert client.get("/api/embeddings/status").json() == {"total": 1, "ready": 0}
