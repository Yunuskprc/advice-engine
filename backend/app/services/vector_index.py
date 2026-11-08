"""Bellekteki embedding matrisi: öneri başına 11 vektör aramasını numpy ile yapar."""

import duckdb
import numpy as np

from app.db import Database


class VectorIndex:
    def __init__(self) -> None:
        self._ids = np.empty(0, dtype=np.int64)
        self._matrix = np.empty((0, 0), dtype=np.float32)

    def __len__(self) -> int:
        return len(self._ids)

    def refresh(self, db: Database) -> None:
        """Embedding'leri yeniden yükler. Atama tek adımdır, okuyan istekler etkilenmez."""
        data = (
            db.cursor()
            .execute(
                "SELECT tmdb_id, embedding FROM movies WHERE embedding IS NOT NULL ORDER BY tmdb_id"
            )
            .fetchnumpy()
        )
        ids = np.asarray(data["tmdb_id"], dtype=np.int64)
        matrix = (
            np.stack(list(data["embedding"])).astype(np.float32)
            if len(ids)
            else np.empty((0, 0), dtype=np.float32)
        )
        self._ids, self._matrix = ids, matrix

    def ensure_fresh(self, db: Database, cur: duckdb.DuckDBPyConnection) -> None:
        row = cur.execute("SELECT count(embedding) FROM movies").fetchone()
        if row is not None and int(row[0]) != len(self._ids):
            self.refresh(db)

    def nearest(
        self, queries: np.ndarray, allowed: np.ndarray, counts: list[int]
    ) -> list[list[int]]:
        """Her sorgu için izin verilen filmler içinde en benzer ID'leri, sıralı döndürür."""
        ids, matrix = self._ids, self._matrix
        mask = np.isin(ids, allowed, assume_unique=True)
        candidates = ids[mask]
        if len(candidates) == 0:
            return [[] for _ in counts]
        similarities = matrix[mask] @ queries.T
        out: list[list[int]] = []
        for column, count in enumerate(counts):
            size = min(count, len(candidates))
            values = similarities[:, column]
            top = np.argpartition(-values, size - 1)[:size]
            top = top[np.argsort(-values[top], kind="stable")]
            out.append([int(i) for i in candidates[top]])
        return out
