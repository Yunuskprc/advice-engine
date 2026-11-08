"""Öneri matematiği: yapısal/hibrit benzerlik, skorlama ve MMR. Saf numpy/scipy fonksiyonları."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

from app.config import RecommenderSettings


def weighted_jaccard(a: sp.csr_matrix, b: sp.csr_matrix, weights: np.ndarray) -> np.ndarray:
    """İkili özellik matrisleri arasında ağırlıklı Jaccard: w(a∩b) / w(a∪b)."""
    intersection = (a @ sp.diags(weights) @ b.T).toarray()
    weight_a = np.asarray(a @ weights).ravel()
    weight_b = np.asarray(b @ weights).ravel()
    union = weight_a[:, np.newaxis] + weight_b[np.newaxis, :] - intersection
    return np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)


def hybrid_similarity(
    cosine: np.ndarray, structural: np.ndarray, rec: RecommenderSettings
) -> np.ndarray:
    return rec.sim_semantic_weight * cosine + rec.sim_structural_weight * structural


def bayesian_quality(
    vote_average: np.ndarray, vote_count: np.ndarray, m: float, catalog_mean: float
) -> np.ndarray:
    """(v/(v+m))·R + (m/(v+m))·C, 0-1 aralığında (TMDB puanı 10 üzerindendir)."""
    v = vote_count.astype(np.float64)
    return ((v / (v + m)) * vote_average + (m / (v + m)) * catalog_mean) / TMDB_MAX_RATING


TMDB_MAX_RATING = 10.0


def popularity_percentile(popularity: np.ndarray) -> np.ndarray:
    """Adaylar içindeki popülerlik sırası: 0 en az bilinen, 1 en popüler."""
    n = len(popularity)
    if n < 2:
        return np.ones(n)
    ranks = np.empty(n)
    ranks[np.argsort(popularity, kind="stable")] = np.arange(n)
    return ranks / (n - 1)


@dataclass(frozen=True)
class ScoreInputs:
    cluster_sim: np.ndarray
    best_five_sim: np.ndarray
    quality: np.ndarray
    repulsion_cos: np.ndarray
    watchlist_cos: np.ndarray
    popularity: np.ndarray


class RecommendationScorer:
    def __init__(self, rec: RecommenderSettings) -> None:
        self.rec = rec

    def score(self, x: ScoreInputs, exploration: float) -> np.ndarray:
        r = self.rec
        repulsion = np.maximum(0.0, x.repulsion_cos - r.score_repulsion_threshold)
        watchlist = np.maximum(0.0, x.watchlist_cos - r.score_watchlist_threshold)
        return (
            r.score_cluster_weight * x.cluster_sim
            + r.score_best_five_weight * x.best_five_sim
            + r.score_quality_weight * x.quality
            - r.score_repulsion_weight * repulsion
            + r.watchlist_weight * watchlist
            + r.score_explore_weight * exploration * (1.0 - x.popularity)
        )


def mmr_select(
    scores: np.ndarray,
    similarity: np.ndarray,
    directors: Sequence[Sequence[str]],
    count: int,
    lam: float,
    max_per_director: int,
) -> list[int]:
    """MMR ile çeşitlendirir; aynı yönetmenden en fazla `max_per_director` film alır."""
    n = len(scores)
    available = np.ones(n, dtype=bool)
    max_sim = np.zeros(n)
    used: dict[str, int] = {}
    selected: list[int] = []
    while len(selected) < count:
        for i in np.flatnonzero(available):
            if any(used.get(d, 0) >= max_per_director for d in directors[int(i)]):
                available[i] = False
        if not available.any():
            break
        mmr = lam * scores - (1.0 - lam) * max_sim
        mmr[~available] = -np.inf
        best = int(np.argmax(mmr))
        selected.append(best)
        available[best] = False
        for d in directors[best]:
            used[d] = used.get(d, 0) + 1
        max_sim = np.maximum(max_sim, similarity[best])
    return selected
