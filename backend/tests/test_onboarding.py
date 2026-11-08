from collections import Counter

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import RecommenderSettings
from app.main import create_app
from app.services.catalog import finalize_catalog
from app.services.onboarding import (
    Affinity,
    Candidate,
    apply_turkish_quota,
    boundary_scores,
    candidate_fit,
    pick_farthest,
    pick_lowest,
    pick_warmup,
    pool_size,
    popularity_weight,
    preference_priors,
    rank_by_relevance,
    stage_for,
    turkish_interval,
    watch_propensity,
)
from app.services.search import fold_text
from tests.conftest import FakeLlm

DIM = 1024


@pytest.fixture
def rec() -> RecommenderSettings:
    return RecommenderSettings(_env_file=None)


def _c(i: int, director: str | None = None, genre: str = "Dram", year: int = 2000) -> Candidate:
    return Candidate(i, f"F{i}", f"M{i}", year, "/p.jpg", (genre,), (director or f"D{i}",))


def _vec(*head: float) -> list[float]:
    return list(head) + [0.0] * (DIM - len(head))


def test_stage_boundaries(rec) -> None:
    assert stage_for(0, rec) == "warmup"
    assert stage_for(rec.onboarding_warmup_ratings, rec) == "explore"
    assert stage_for(rec.onboarding_explore_ratings, rec) == "refine"


def test_warmup_turkish_quota_every_fifth_card() -> None:
    pool = [_c(i) for i in range(1, 30)]
    tr = [_c(i) for i in range(100, 105)]
    picks = pick_warmup(pool, tr, 10, 0, 5, Counter(), Counter(), 25)
    assert [i for i, c in enumerate(picks, 1) if c.tmdb_id >= 100] == [5, 10]


def test_warmup_balances_genres() -> None:
    pool = [_c(1, genre="A"), _c(2, genre="A"), _c(3, genre="B")]
    picks = pick_warmup(pool, [], 2, 0, 5, Counter(), Counter(), 25)
    assert {c.genres[0] for c in picks} == {"A", "B"}


def test_warmup_no_same_director_in_a_row() -> None:
    pool = [_c(1, "X"), _c(2, "X"), _c(3, "Y")]
    picks = pick_warmup(pool, [], 3, 0, 5, Counter(), Counter(), 25)
    assert [c.directors[0] for c in picks] == ["X", "Y", "X"]


def test_farthest_prefers_unknown_region() -> None:
    pool = [_c(1), _c(2), _c(3)]
    vectors = np.array([[1.0, 0.0], [0.9, 0.436], [0.0, 1.0]], dtype=np.float32)
    anchors = np.array([[1.0, 0.0]], dtype=np.float32)
    assert pick_farthest(pool, vectors, anchors, 1)[0].tmdb_id == 3


def test_boundary_prefers_between_clusters() -> None:
    vectors = np.array([[1.0, 0.0], [0.707, 0.707]], dtype=np.float32)
    centroids = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    scores = boundary_scores(vectors, centroids, 0.5)
    assert pick_lowest([_c(1), _c(2)], scores, 1)[0].tmdb_id == 2


def test_fold_text() -> None:
    assert fold_text("  Kış   UYKUSU ") == "kis uykusu"
    assert fold_text("İNCİR Çekirdeği") == "incir cekirdegi"


def _seed(cur, count: int) -> None:
    for i in range(1, count + 1):
        cur.execute(
            "INSERT INTO movies (tmdb_id, title_tr, title_original, original_language, vote_count,"
            " poster_path, embedding, embedding_stale, release_date, synced_at)"
            " VALUES (?, ?, ?, ?, ?, '/p.jpg', ?::FLOAT[1024], FALSE, DATE '2000-01-01',"
            " current_timestamp::TIMESTAMP)",
            [i, f"Film {i}", f"Movie {i}", "tr" if i % 4 == 0 else "en", 1000 - i, _vec(1.0)],
        )


def _client(settings):
    return TestClient(create_app(settings, llm=FakeLlm()))


def test_answered_cards_do_not_repeat_and_undo_returns(settings) -> None:
    with _client(settings) as client:
        cur = client.app.state.db.cursor()
        _seed(cur, 12)
        first = client.get("/api/onboarding/next", params={"count": 2}).json()["cards"]
        a, b = first[0]["tmdb_id"], first[1]["tmdb_id"]
        assert client.put(f"/api/ratings/{a}", json={"score": 5}).status_code == 204
        assert client.put(f"/api/onboarding/skips/{b}").status_code == 204

        ids = [
            c["tmdb_id"]
            for c in client.get("/api/onboarding/next", params={"count": 10}).json()["cards"]
        ]
        assert a not in ids and b not in ids

        assert client.delete(f"/api/ratings/{a}").status_code == 204
        body = client.get("/api/onboarding/progress").json()
        assert (body["rated"], body["skipped"]) == (0, 1)


def test_exclude_param_keeps_queue_out(settings) -> None:
    with _client(settings) as client:
        _seed(client.app.state.db.cursor(), 5)
        cards = client.get("/api/onboarding/next", params={"exclude": [1, 2], "count": 5}).json()
        assert {c["tmdb_id"] for c in cards["cards"]} == {3, 4, 5}


def test_invalid_score_rejected(settings) -> None:
    with _client(settings) as client:
        _seed(client.app.state.db.cursor(), 1)
        assert client.put("/api/ratings/1", json={"score": 6}).status_code == 422
        assert client.put("/api/ratings/999", json={"score": 5}).status_code == 404


def test_search_exact_typo_and_turkish_folding(settings) -> None:
    with _client(settings) as client:
        cur = client.app.state.db.cursor()
        for i, title in enumerate(["Esaretin Bedeli", "Kış Uykusu", "Inception"], 1):
            cur.execute(
                "INSERT INTO movies (tmdb_id, title_tr, title_original, vote_count, synced_at)"
                " VALUES (?, ?, ?, 10, current_timestamp::TIMESTAMP)",
                [i, title, title],
            )
        finalize_catalog(cur)

        def top(q: str) -> str | None:
            rows = client.get("/api/search", params={"q": q}).json()
            return rows[0]["title_tr"] if rows else None

        assert top("esaretin bedli") == "Esaretin Bedeli"
        assert top("kis uykusu") == "Kış Uykusu"
        assert top("incepton") == "Inception"
        assert top("qqqqqq") is None


def test_movie_detail_and_404(settings) -> None:
    with _client(settings) as client:
        _seed(client.app.state.db.cursor(), 1)
        client.put("/api/ratings/1", json={"score": 4})
        client.put("/api/watchlist/1")
        body = client.get("/api/movies/1").json()
        assert body["my_rating"] == 4 and body["in_watchlist"] is True
        assert client.get("/api/movies/2").status_code == 404


def test_warmup_keeps_popular_first_over_balance() -> None:
    # Havuzun başı aynı türden; denge için derinlerdeki az popüler filme inilmez.
    pool = [_c(i, genre="A") for i in range(1, 6)] + [_c(99, genre="B")]
    picks = pick_warmup(pool, [], 2, 0, 5, Counter(), Counter(), 3)
    assert 99 not in [c.tmdb_id for c in picks]


def test_skips_do_not_advance_stage(settings, rec) -> None:
    with _client(settings) as client:
        cur = client.app.state.db.cursor()
        _seed(cur, rec.onboarding_warmup_ratings + 5)
        for i in range(1, rec.onboarding_warmup_ratings + 2):
            client.put(f"/api/onboarding/skips/{i}")
        assert client.get("/api/onboarding/progress").json()["stage"] == "warmup"


def test_popularity_decays_with_ratings(rec) -> None:
    assert pool_size(0, rec) == rec.onboarding_pool_start
    assert pool_size(rec.onboarding_explore_ratings, rec) == rec.onboarding_pool_end
    assert popularity_weight(0, rec) == pytest.approx(rec.onboarding_pop_weight_start)
    assert popularity_weight(30, rec) < popularity_weight(0, rec)
    assert popularity_weight(10_000, rec) == pytest.approx(rec.onboarding_pop_weight_end)


def test_watch_propensity_example() -> None:
    p = watch_propensity(Counter({"Korku": 2}), Counter({"Korku": 8}), strength=2.0, overall=0.5)
    assert p["Korku"] == pytest.approx(3 / 12)


def test_no_answers_keeps_popularity_order(rec) -> None:
    pool = [_c(i, genre="A") for i in range(1, 5)]
    ranked = rank_by_relevance(pool, 0, rec, Affinity(genres={}, decades={}))
    assert [c.tmdb_id for c in ranked] == [1, 2, 3, 4]


def test_unwatched_genre_falls_behind(rec) -> None:
    pool = [_c(i, genre="Korku") for i in range(1, 4)] + [_c(i, genre="Dram") for i in range(4, 7)]
    affinity = Affinity(genres={"Korku": 0.25, "Dram": 0.75}, decades={})
    ranked = [c.genres[0] for c in rank_by_relevance(pool, 0, rec, affinity)]
    assert ranked[0] == "Dram"
    assert ranked.index("Korku") > 0


def test_skips_lower_genre_in_next_cards(settings) -> None:
    with _client(settings) as client:
        cur = client.app.state.db.cursor()
        cur.execute("INSERT INTO genres (id, name_tr) VALUES (27, 'Korku'), (18, 'Dram')")
        _seed(cur, 40)
        for i in range(1, 41):
            cur.execute(
                "INSERT INTO movie_genre (movie_id, genre_id) VALUES (?, ?)",
                [i, 27 if i % 2 else 18],
            )
        for i in range(1, 9):
            if i % 2:
                client.put(f"/api/onboarding/skips/{i}")
            else:
                client.put(f"/api/ratings/{i}", json={"score": 4})
        cards = client.get("/api/onboarding/next", params={"count": 10}).json()["cards"]
        drama = sum(c["tmdb_id"] % 2 == 0 for c in cards)
        assert drama > len(cards) / 2


def test_untested_genre_starts_at_overall_rate(rec) -> None:
    affinity = Affinity(genres={"A": 0.9}, decades={}, default=0.8)
    assert candidate_fit(_c(1, genre="B"), affinity, rec) == pytest.approx(0.5)


def test_preference_prior_relaxes_toward_overall(rec) -> None:
    start = preference_priors(["Dram", "Aksiyon"], {"Dram"}, 0.5, 0, rec)
    assert start["Dram"] == pytest.approx(rec.onboarding_pref_selected)
    assert start["Aksiyon"] == pytest.approx(rec.onboarding_pref_other)
    later = preference_priors(["Dram", "Aksiyon"], {"Dram"}, 0.5, 30, rec)
    assert start["Aksiyon"] < later["Aksiyon"] < 0.5
    assert later["Dram"] < start["Dram"]
    assert preference_priors(["Dram"], set(), 0.5, 0, rec) == {}


def test_answers_override_unselected_genre_prior() -> None:
    p = watch_propensity(
        Counter({"Aksiyon": 3}), Counter(), strength=2.0, overall=0.5, priors={"Aksiyon": 0.2}
    )
    assert p["Aksiyon"] == pytest.approx((3 + 0.4) / 5)
    assert p["Aksiyon"] > 0.5


def _seed_genres(cur, count: int) -> None:
    cur.execute("INSERT INTO genres (id, name_tr) VALUES (35, 'Komedi'), (28, 'Aksiyon')")
    _seed(cur, count)
    for i in range(1, count + 1):
        cur.execute(
            "INSERT INTO movie_genre (movie_id, genre_id) VALUES (?, ?)",
            [i, 28 if i % 2 else 35],
        )


def test_preferences_flow_and_selected_genre_first(settings) -> None:
    with _client(settings) as client:
        _seed_genres(client.app.state.db.cursor(), 40)
        assert client.get("/api/onboarding/preferences").json()["completed"] is False
        assert client.put("/api/onboarding/preferences", json={"group_ids": []}).status_code == 422
        bad = client.put("/api/onboarding/preferences", json={"group_ids": ["yok"]})
        assert bad.status_code == 422

        body = client.put(
            "/api/onboarding/preferences", json={"group_ids": ["yerli_komedi", "yok"]}
        ).json()
        assert body["completed"] is True
        assert [g["id"] for g in body["groups"] if g["selected"]] == ["yerli_komedi"]

        cards = client.get("/api/onboarding/next", params={"count": 10}).json()["cards"]
        assert sum(c["tmdb_id"] % 2 == 0 for c in cards) > len(cards) / 2


def _lang(i: int, language: str, year: int = 2015) -> Candidate:
    return Candidate(i, f"F{i}", f"M{i}", year, "/p.jpg", ("Dram",), (f"D{i}",), language)


def test_unwatched_language_and_decade_fall_behind(rec) -> None:
    affinity = Affinity(
        genres={},
        decades={1980: 0.05, 2010: 0.4},
        default=0.25,
        languages={"ja": 0.05, "en": 0.4},
    )
    japanese = candidate_fit(_lang(1, "ja"), affinity, rec)
    english = candidate_fit(_lang(2, "en"), affinity, rec)
    old = candidate_fit(_lang(3, "en", year=1985), affinity, rec)
    assert japanese < english and old < english


def test_low_hit_rate_keeps_popular_pool(rec) -> None:
    rated = rec.onboarding_explore_ratings
    assert pool_size(rated, rec, 0.5) == rec.onboarding_pool_end
    assert pool_size(rated, rec, 0.1) < pool_size(rated, rec, 0.4) < rec.onboarding_pool_end
    assert popularity_weight(rated, rec, 0.1) > popularity_weight(rated, rec, 0.5)


def test_turkish_interval_follows_propensity(rec) -> None:
    def every(p: float) -> int:
        return turkish_interval(Affinity({}, {}, 0.5, languages={"tr": p}), rec)

    assert every(1.0) == rec.onboarding_tr_every_min
    assert every(0.0) == rec.onboarding_tr_every_max
    assert every(0.8) < every(0.2)


def test_quota_applies_in_later_stages() -> None:
    picks = [_c(i) for i in range(1, 7)]
    tr = [_c(100), _c(101)]
    out = apply_turkish_quota(picks, tr, position=0, every=3)
    assert [c.tmdb_id for c in out] == [1, 2, 100, 4, 5, 101]


def test_page_answers_are_saved_together_and_can_be_removed(settings) -> None:
    with _client(settings) as client:
        _seed(client.app.state.db.cursor(), 6)
        answers = {
            "ratings": [{"movie_id": 1, "score": 5}, {"movie_id": 999, "score": 4}],
            "skips": [1, 2, 3],
        }
        assert client.post("/api/onboarding/answers", json=answers).status_code == 204
        body = client.get("/api/onboarding/progress").json()
        assert (body["rated"], body["skipped"]) == (1, 2)  # 1 puanlı, 999 katalogda yok

        cards = client.get("/api/onboarding/next", params={"count": 10}).json()["cards"]
        assert not {c["tmdb_id"] for c in cards} & {1, 2, 3}

        removed = client.post("/api/onboarding/answers/remove", json={"movie_ids": [1, 2, 3]})
        assert removed.status_code == 204
        body = client.get("/api/onboarding/progress").json()
        assert (body["rated"], body["skipped"]) == (0, 0)


def test_domestic_group_raises_turkish_frequency(settings, rec) -> None:
    with _client(settings) as client:
        cur = client.app.state.db.cursor()
        _seed(cur, 5)
        client.put("/api/onboarding/preferences", json={"group_ids": ["yerli_komedi"]})
        from app.services.onboarding import _load_affinity

        affinity = _load_affinity(cur, rec, 0)
        assert affinity.languages["tr"] == pytest.approx(rec.onboarding_pref_selected)
        assert turkish_interval(affinity, rec) < rec.onboarding_tr_every_max
