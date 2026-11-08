import numpy as np
import pytest
import scipy.sparse as sp
from fastapi.testclient import TestClient

from app.api.schemas import RecommendationFilters, RecommendationRequest
from app.config import RecommenderSettings
from app.main import create_app
from app.services.embedding import l2_normalize
from app.services.recommendations import Cluster, pick_surprise_cluster, recommend
from app.services.scoring import (
    RecommendationScorer,
    ScoreInputs,
    bayesian_quality,
    hybrid_similarity,
    mmr_select,
    popularity_percentile,
    weighted_jaccard,
)
from app.services.taste import recompute_taste
from tests.conftest import FakeLlm

DIM = 1024


@pytest.fixture
def rec() -> RecommenderSettings:
    return RecommenderSettings(_env_file=None)


def test_weighted_jaccard() -> None:
    a = sp.csr_matrix(np.array([[1, 1, 0], [0, 0, 0]], dtype=float))
    b = sp.csr_matrix(np.array([[1, 0, 1]], dtype=float))
    out = weighted_jaccard(a, b, np.array([2.0, 1.0, 1.0]))
    assert out[0, 0] == pytest.approx(2.0 / 4.0)
    assert out[1, 0] == 0.0


def test_hybrid_similarity(rec) -> None:
    out = hybrid_similarity(np.array([1.0]), np.array([0.0]), rec)
    assert out[0] == pytest.approx(rec.sim_semantic_weight)


def test_bayesian_quality_shrinks_low_votes() -> None:
    high_votes, low_votes = bayesian_quality(
        np.array([9.0, 9.0]), np.array([100000, 10]), m=500, catalog_mean=6.0
    )
    assert high_votes == pytest.approx(0.9, abs=0.01)
    assert low_votes == pytest.approx(0.606, abs=0.01)


def test_popularity_percentile() -> None:
    assert popularity_percentile(np.array([5.0, 1.0, 9.0])).tolist() == [0.5, 0.0, 1.0]


def _inputs(size: int = 1, **over) -> ScoreInputs:
    base = {k: np.zeros(size) for k in ScoreInputs.__dataclass_fields__}
    return ScoreInputs(**{**base, **over})


def test_scorer_matches_formula(rec) -> None:
    x = _inputs(
        cluster_sim=np.array([0.8]),
        best_five_sim=np.array([0.7]),
        quality=np.array([0.6]),
        repulsion_cos=np.array([0.9]),
        popularity=np.array([0.25]),
    )
    expected = 0.5 * 0.8 + 0.2 * 0.7 + 0.15 * 0.6 - 0.4 * 0.4 + 0.15 * 0.5 * 0.75
    assert RecommendationScorer(rec).score(x, 0.5)[0] == pytest.approx(expected)


def test_scorer_repulsion_below_threshold_is_free(rec) -> None:
    x = _inputs(repulsion_cos=np.array([0.3]), popularity=np.array([1.0]))
    assert RecommendationScorer(rec).score(x, 0.0)[0] == pytest.approx(0.0)


def test_scorer_watchlist_bonus(rec) -> None:
    x = _inputs(2, watchlist_cos=np.array([0.8, 0.2]))
    out = RecommendationScorer(rec).score(x, 0.0)
    assert out[0] == pytest.approx(0.2 * 0.3)
    assert out[1] == pytest.approx(0.0)


def test_exploration_favors_unknown(rec) -> None:
    x = _inputs(2, popularity=np.array([0.0, 1.0]))
    safe = RecommendationScorer(rec).score(x, 0.0)
    bold = RecommendationScorer(rec).score(x, 1.0)
    assert safe[0] == safe[1] and bold[0] > bold[1]


def test_mmr_diversifies() -> None:
    scores = np.array([1.0, 0.95, 0.6])
    sim = np.array([[1.0, 0.99, 0.0], [0.99, 1.0, 0.0], [0.0, 0.0, 1.0]])
    picked = mmr_select(scores, sim, [["a"], ["b"], ["c"]], 2, 0.7, 2)
    assert picked == [0, 2]


def test_mmr_director_cap() -> None:
    scores = np.array([1.0, 0.9, 0.8, 0.1])
    picked = mmr_select(scores, np.eye(4), [["a"], ["a"], ["a"], ["b"]], 4, 0.7, 2)
    assert picked == [0, 1, 3]


def test_surprise_cluster_probability_uses_exponent() -> None:
    clusters = [Cluster(1, np.zeros(2), 100.0), Cluster(2, np.zeros(2), 1.0)]
    rng = np.random.default_rng(0)
    picks = [pick_surprise_cluster(clusters, 0.5, rng).id for _ in range(2000)]
    assert picks.count(2) / len(picks) == pytest.approx(1 / 11, abs=0.03)


def _vec(rng: np.random.Generator) -> list[float]:
    head = np.array([1.0, 0.0, 0.0, 0.0]) + rng.normal(0, 0.1, 4)
    return l2_normalize(head[np.newaxis, :])[0].tolist() + [0.0] * (DIM - 4)


def _seed(cur, n: int, director_every: int = 1) -> None:
    rng = np.random.default_rng(7)
    cur.execute("INSERT INTO people (id, name) VALUES (1, 'Ortak Yönetmen')")
    cur.execute("INSERT INTO keywords (id, name, df) VALUES (1, 'zaman', 5)")
    cur.execute("INSERT INTO genres (id, name_tr) VALUES (18, 'Dram'), (35, 'Komedi')")
    for i in range(1, n + 1):
        cur.execute(
            "INSERT INTO movies (tmdb_id, title_tr, title_original, original_language,"
            " release_date, runtime, vote_average, vote_count, popularity, poster_path,"
            " embedding, embedding_stale, synced_at)"
            " VALUES (?, ?, ?, ?, ?, 100, 7.5, 1000, ?, '/p.jpg', ?::FLOAT[1024], FALSE,"
            " current_timestamp::TIMESTAMP)",
            [
                i,
                f"Film {i}",
                f"Movie {i}",
                "tr" if i % 5 == 0 else "en",
                f"{1990 + i % 30}-01-01",
                float(i),
                _vec(rng),
            ],
        )
        director = 1 if i % director_every == 0 else 1000 + i
        if director != 1:
            cur.execute("INSERT INTO people (id, name) VALUES (?, ?)", [director, f"Y{director}"])
        cur.execute(
            "INSERT INTO movie_person (movie_id, person_id, role) VALUES (?, ?, 'director')",
            [i, director],
        )
        cur.execute("INSERT INTO movie_keyword (movie_id, keyword_id) VALUES (?, 1)", [i])
        cur.execute(
            "INSERT INTO movie_genre (movie_id, genre_id) VALUES (?, ?)",
            [i, 18 if i % 2 == 0 else 35],
        )


@pytest.fixture
def seeded(db, rec):
    cur = db.cursor()
    _seed(cur, 80, director_every=3)
    for i in range(1, 19):
        cur.execute("INSERT INTO ratings (movie_id, score) VALUES (?, 5)", [i])
    cur.execute("INSERT INTO watchlist (movie_id) VALUES (20)")
    cur.execute("INSERT INTO recommendation_feedback (movie_id, action) VALUES (21, 'dismissed')")
    recompute_taste(db, rec)
    return db


def _ids(response) -> list[int]:
    return [m.tmdb_id for m in response.items]


def test_recommend_excludes_rated_dismissed_watchlist(seeded, rec) -> None:
    ids = _ids(recommend(seeded, rec, RecommendationRequest()))
    assert len(ids) == rec.result_count
    assert not set(ids) & (set(range(1, 19)) | {20, 21})


def test_recommend_director_cap(seeded, rec) -> None:
    ids = _ids(recommend(seeded, rec, RecommendationRequest()))
    assert len([i for i in ids if i % 3 == 0]) <= rec.max_per_director


def test_recommend_filters_and_exclude(seeded, rec) -> None:
    first = _ids(recommend(seeded, rec, RecommendationRequest()))
    second = _ids(recommend(seeded, rec, RecommendationRequest(exclude=first)))
    assert second and not set(first) & set(second)

    domestic = recommend(
        seeded, rec, RecommendationRequest(filters=RecommendationFilters(origin="domestic"))
    )
    assert domestic.items and all(m.tmdb_id % 5 == 0 for m in domestic.items)

    comedy = recommend(
        seeded, rec, RecommendationRequest(filters=RecommendationFilters(genres_exclude=[18]))
    )
    assert comedy.items and all(m.tmdb_id % 2 == 1 for m in comedy.items)


def test_recommend_explanation(seeded, rec) -> None:
    text = recommend(seeded, rec, RecommendationRequest()).items[0].explanation
    assert "(5★)" in text and "ile benzer" in text and "zaman" in text


def test_exploration_lowers_popularity(seeded, rec) -> None:
    def avg_popularity(level: float) -> float:
        response = recommend(seeded, rec, RecommendationRequest(exploration=level))
        return float(np.mean(_ids(response)))  # seed'de popülerlik = id

    assert avg_popularity(1.0) < avg_popularity(0.0)


def test_api_feedback_and_watchlist(settings, rec) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        db = client.app.state.db
        cur = db.cursor()
        _seed(cur, 40)
        for i in range(1, 19):
            cur.execute("INSERT INTO ratings (movie_id, score) VALUES (?, 5)", [i])
        recompute_taste(db, rec)

        body = client.post("/api/recommendations", json={}).json()
        target = body["items"][0]["tmdb_id"]
        cluster_id = body["cluster_id"]
        response = client.post(
            f"/api/recommendations/{target}/feedback",
            json={"action": "saved", "cluster_id": cluster_id},
        )
        assert response.status_code == 204
        assert [m["tmdb_id"] for m in client.get("/api/watchlist").json()] == [target]

        again = client.post("/api/recommendations", json={"cluster_id": cluster_id}).json()
        assert target not in [m["tmdb_id"] for m in again["items"]]
        assert client.post("/api/recommendations", json={"cluster_id": 9999}).status_code == 404
        options = client.get("/api/recommendations/options").json()
        assert {g["name"] for g in options["genres"]} == {"Dram", "Komedi"}


def test_no_clusters_returns_empty(settings) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        assert client.post("/api/recommendations", json={}).json() == {
            "cluster_id": None,
            "items": [],
        }


def test_vector_index_respects_allowed_and_order(db) -> None:
    from app.services.vector_index import VectorIndex

    cur = db.cursor()
    for tmdb_id, head in ((1, (1.0, 0.0)), (2, (0.8, 0.6)), (3, (0.0, 1.0))):
        vector = list(head) + [0.0] * (DIM - 2)
        cur.execute(
            "INSERT INTO movies (tmdb_id, title_tr, title_original, embedding, synced_at)"
            " VALUES (?, 'a', 'a', ?::FLOAT[1024], current_timestamp::TIMESTAMP)",
            [tmdb_id, vector],
        )
    index = VectorIndex()
    index.ensure_fresh(db, cur)
    query = np.zeros((1, DIM), dtype=np.float32)
    query[0, 0] = 1.0
    assert index.nearest(query, np.array([1, 2, 3]), [2]) == [[1, 2]]
    assert index.nearest(query, np.array([2, 3]), [5]) == [[2, 3]]
    assert index.nearest(query, np.array([], dtype=np.int64), [5]) == [[]]


def test_feedback_can_be_undone(settings, rec) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        db = client.app.state.db
        cur = db.cursor()
        _seed(cur, 30)
        for i in range(1, 19):
            cur.execute("INSERT INTO ratings (movie_id, score) VALUES (?, 5)", [i])
        recompute_taste(db, rec)
        target = client.post("/api/recommendations", json={}).json()["items"][0]["tmdb_id"]

        client.post(f"/api/recommendations/{target}/feedback", json={"action": "saved"})
        assert client.delete(f"/api/recommendations/{target}/feedback/saved").status_code == 204
        assert client.get("/api/watchlist").json() == []
        assert cur.execute("SELECT count(*) FROM recommendation_feedback").fetchone() == (0,)


def test_taste_response_has_turkish_titles_and_insights(settings, rec) -> None:
    with TestClient(create_app(settings, llm=FakeLlm())) as client:
        db = client.app.state.db
        cur = db.cursor()
        _seed(cur, 30)
        for i in range(1, 19):
            cur.execute("INSERT INTO ratings (movie_id, score) VALUES (?, 5)", [i])
        for i in range(19, 26):
            cur.execute("INSERT INTO onboarding_skips (movie_id) VALUES (?)", [i])
        recompute_taste(db, rec)
        body = client.get("/api/taste").json()
        assert {"Dram", "Komedi"} & set(body["clusters"][0]["auto_title"].split(" · "))
        assert body["insights"]["rated"] == 18
        assert body["insights"]["skipped"] == 7
