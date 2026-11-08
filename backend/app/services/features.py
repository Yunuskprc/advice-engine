"""Filmlerin yapısal özelliklerini (keyword, kişi, tür, dil) DuckDB'den matrise çevirir."""

import math
from dataclasses import dataclass

import duckdb
import numpy as np
import scipy.sparse as sp

from app.config import RecommenderSettings

Feature = tuple[str, str]  # (tür, değer): ("keyword", "123"), ("director", "45"), ...


@dataclass
class FeatureSet:
    row_of: dict[int, int]
    matrix: sp.csr_matrix
    weights: np.ndarray
    by_movie: dict[int, set[Feature]]
    df: dict[str, int]  # keyword id -> df

    def rows(self, ids: list[int]) -> sp.csr_matrix:
        return self.matrix[[self.row_of[i] for i in ids]]


def load_features(
    cur: duckdb.DuckDBPyConnection, ids: list[int], rec: RecommenderSettings
) -> FeatureSet:
    catalog = cur.execute("SELECT count(*) FROM movies").fetchone()
    assert catalog is not None
    n_movies = max(int(catalog[0]), 1)
    rows = cur.execute(
        """
        WITH f AS (SELECT unnest($ids::BIGINT[]) AS id)
        SELECT mk.movie_id, 'keyword' AS kind, mk.keyword_id::VARCHAR AS value, k.df
        FROM movie_keyword mk JOIN keywords k ON k.id = mk.keyword_id
        WHERE mk.movie_id IN (SELECT id FROM f)
        UNION ALL
        SELECT mp.movie_id, mp.role, mp.person_id::VARCHAR, NULL FROM movie_person mp
        WHERE mp.movie_id IN (SELECT id FROM f)
        UNION ALL
        SELECT mg.movie_id, 'genre', mg.genre_id::VARCHAR, NULL FROM movie_genre mg
        WHERE mg.movie_id IN (SELECT id FROM f)
        UNION ALL
        SELECT m.tmdb_id, 'language', m.original_language, NULL FROM movies m
        WHERE m.tmdb_id IN (SELECT id FROM f) AND m.original_language IS NOT NULL
        """,
        {"ids": ids},
    ).fetchall()

    kind_weight = {
        "director": rec.feat_director_weight,
        "writer": rec.feat_writer_weight,
        "cast": rec.feat_cast_weight,
        "genre": rec.feat_genre_weight,
        "language": rec.feat_language_weight,
    }
    row_of = {movie_id: i for i, movie_id in enumerate(ids)}
    column_of: dict[Feature, int] = {}
    weights: list[float] = []
    by_movie: dict[int, set[Feature]] = {i: set() for i in ids}
    df: dict[str, int] = {}
    row_index: list[int] = []
    col_index: list[int] = []

    # IDF 0-1 aralığına ölçeklenir; yoksa keyword'ler yönetmen gibi sinyalleri bastırırdı.
    log_n = math.log1p(n_movies)
    for movie_id, kind, value, keyword_df in rows:
        feature: Feature = (kind, value)
        if feature not in by_movie[movie_id]:
            by_movie[movie_id].add(feature)
            column = column_of.get(feature)
            if column is None:
                column = len(column_of)
                column_of[feature] = column
                if kind == "keyword":
                    count = max(int(keyword_df or 0), 1)
                    df[value] = count
                    weights.append(rec.feat_keyword_weight * math.log1p(n_movies / count) / log_n)
                else:
                    weights.append(kind_weight[kind])
            row_index.append(row_of[movie_id])
            col_index.append(column)

    matrix = sp.csr_matrix(
        (np.ones(len(row_index), dtype=np.float64), (row_index, col_index)),
        shape=(len(ids), max(len(column_of), 1)),
    )
    return FeatureSet(
        row_of=row_of,
        matrix=matrix,
        weights=np.array(weights if weights else [0.0], dtype=np.float64),
        by_movie=by_movie,
        df=df,
    )
