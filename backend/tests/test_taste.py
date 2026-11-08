import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import RecommenderSettings
from app.main import create_app
from app.services.embedding import l2_normalize
from app.services.taste import (
    cluster_negative,
    cluster_positive,
    merge_small_clusters,
    recompute_taste,
    summarize,
    weighted_centroid,
)
from tests.conftest import FakeLlm

DIM = 1024


@pytest.fixture
def rec() -> RecommenderSettings:
    return RecommenderSettings(_env_file=None)


def blobs(sizes: list[int], dim: int = 8, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Eksenlere oturan belirgin gruplar: (vektörler, gerçek etiketler)."""
    rng = np.random.default_rng(seed)
    parts = []
    truth = []
    for label, size in enumerate(sizes):
        center = np.zeros(dim)
        center[label] = 1.0
        parts.append(center + rng.normal(0, 0.05, (size, dim)))
        truth += [label] * size
    return l2_normalize(np.vstack(parts).astype(np.float32)), np.array(truth)


def _same_partition(a: np.ndarray, b: np.ndarray) -> bool:
    return len(set(zip(a.tolist(), b.tolist(), strict=True))) == len(set(b.tolist()))


def test_finds_true_clusters(rec) -> None:
    x, truth = blobs([30, 30, 30])
    labels = cluster_positive(x, np.ones(len(x), dtype=np.float32), rec)
    assert len(np.unique(labels)) == 3
    assert _same_partition(labels, truth)


def test_same_input_same_clusters(rec) -> None:
    x, _ = blobs([25, 25, 25], seed=3)
    w = np.ones(len(x), dtype=np.float32)
    assert np.array_equal(cluster_positive(x, w, rec), cluster_positive(x, w, rec))


def test_below_threshold_is_single_cluster(rec) -> None:
    x, _ = blobs([7, 7])
    labels = cluster_positive(x, np.ones(len(x), dtype=np.float32), rec)
    assert len(x) < rec.cluster_min_positive
    assert set(labels.tolist()) == {0}


def test_small_cluster_merged_into_nearest() -> None:
    x = l2_normalize(np.array([[1, 0], [1, 0.1], [0.9, 0.3], [0, 1]], dtype=np.float32))
    w = np.ones(4, dtype=np.float32)
    # 1 ve 2 numaralı küme 8'in altında; hepsi tek kümede birleşir.
    merged = merge_small_clusters(x, w, np.array([0, 0, 1, 2]), min_size=2)
    assert merged[2] == merged[0]
    assert len(np.unique(merge_small_clusters(x, w, np.array([0, 0, 1, 2]), min_size=8))) == 1


def test_weighted_centroid_leans_to_heavier() -> None:
    x = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    c = weighted_centroid(x, np.array([1.0, 0.5], dtype=np.float32))
    assert np.linalg.norm(c) == pytest.approx(1.0)
    assert c[0] > c[1]


def test_summarize_weight_and_membership() -> None:
    x = np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    stats = summarize(x, np.array([1.0, 0.5, 0.5], dtype=np.float32), np.array([1, 1, 0]))
    assert [s.weight for s in stats] == [1.5, 0.5]
    assert stats[0].memberships == pytest.approx([1.0, 1.0])


def test_negative_split_rules(rec) -> None:
    x, _ = blobs([5, 5])
    assert set(cluster_negative(x, np.ones(10, dtype=np.float32), rec).tolist()) == {0}
    x, truth = blobs([10, 10, 10])
    labels = cluster_negative(x, np.ones(30, dtype=np.float32), rec)
    assert len(np.unique(labels)) <= rec.negative_max_clusters
    assert _same_partition(labels, truth)


def _seed(cur, vectors: np.ndarray, start: int = 1) -> list[int]:
    ids = []
    for offset, v in enumerate(vectors):
        i = start + offset
        padded = v.tolist() + [0.0] * (DIM - len(v))
        cur.execute(
            "INSERT INTO movies (tmdb_id, title_tr, title_original, embedding, embedding_stale,"
            " synced_at) VALUES (?, ?, ?, ?::FLOAT[1024], FALSE, current_timestamp::TIMESTAMP)",
            [i, f"Film {i}", f"Movie {i}", padded],
        )
        ids.append(i)
    return ids


def _rate(cur, ids: list[int], score: int) -> None:
    for i in ids:
        cur.execute("INSERT INTO ratings (movie_id, score) VALUES (?, ?)", [i, score])


def _partition(cur) -> set[tuple[int, ...]]:
    rows = cur.execute(
        "SELECT list(tcm.movie_id ORDER BY tcm.movie_id) FROM taste_cluster_movie tcm"
        " GROUP BY tcm.cluster_id"
    ).fetchall()
    return {tuple(r[0]) for r in rows}


def test_recompute_writes_clusters_and_is_repeatable(db, rec) -> None:
    cur = db.cursor()
    x, _ = blobs([20, 20], seed=1)
    ids = _seed(cur, x)
    _rate(cur, ids, 5)
    neg_x, _ = blobs([4], seed=2)
    neg_ids = _seed(cur, neg_x, start=100)
    _rate(cur, neg_ids, 1)

    assert recompute_taste(db, rec) == 3
    first = _partition(cur)
    assert set(ids[:20]) in [set(p) for p in first]
    row = cur.execute(
        "SELECT count(*), sum(weight) FROM taste_clusters WHERE is_negative"
    ).fetchone()
    assert row == (1, pytest.approx(4.0))

    recompute_taste(db, rec)
    assert _partition(cur) == first
    assert cur.execute("SELECT count(*) FROM taste_clusters").fetchone() == (3,)


def test_rating_three_not_used_and_dismissed_is_negative(db, rec) -> None:
    cur = db.cursor()
    x, _ = blobs([3], seed=4)
    ids = _seed(cur, x)
    _rate(cur, ids[:2], 3)
    cur.execute(
        "INSERT INTO recommendation_feedback (movie_id, action) VALUES (?, 'dismissed')", [ids[2]]
    )
    recompute_taste(db, rec)
    rows = cur.execute("SELECT is_negative, size, weight FROM taste_clusters").fetchall()
    assert rows == [(True, 1, pytest.approx(abs(rec.dismissed_weight)))]


def test_every_tenth_rating_triggers_job_and_api(settings, rec) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        cur = client.app.state.db.cursor()
        x, _ = blobs([12], seed=5)
        ids = _seed(cur, x)
        for i in ids[: rec.recompute_every_n_ratings - 1]:
            client.put(f"/api/ratings/{i}", json={"score": 5})
        assert not [j for j in client.get("/api/jobs").json() if j["type"] == "recompute_taste"]

        client.put(f"/api/ratings/{ids[rec.recompute_every_n_ratings - 1]}", json={"score": 5})
        for _ in range(100):
            jobs = [j for j in client.get("/api/jobs").json() if j["type"] == "recompute_taste"]
            if jobs and jobs[0]["status"] == "done":
                break
            time.sleep(0.05)
        assert jobs[0]["status"] == "done"

        body = client.get("/api/taste").json()
        assert len(body["clusters"]) == 1  # 15 pozitifin altında tek küme
        assert body["clusters"][0]["size"] == rec.recompute_every_n_ratings
        assert len(body["clusters"][0]["typical"]) == rec.cluster_typical_display
        assert body["negatives"] == []
