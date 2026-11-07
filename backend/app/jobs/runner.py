"""Uygulama içi JobRunner: tek worker thread, işler sırayla çalışır.

Durum ve ilerleme `jobs` tablosunda tutulur. Aynı tipte kuyrukta bekleyen iş varsa
yenisi eklenmez (submit mevcut işin id'sini döndürür).
"""

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass

from app.db import Database

log = logging.getLogger(__name__)

_STOP = object()


@dataclass
class JobContext:
    job_id: int
    db: Database

    def set_total(self, total: int) -> None:
        self.db.cursor().execute("UPDATE jobs SET total = ? WHERE id = ?", [total, self.job_id])

    def set_progress(self, progress: int) -> None:
        self.db.cursor().execute(
            "UPDATE jobs SET progress = ? WHERE id = ?", [progress, self.job_id]
        )


JobFn = Callable[[JobContext], None]


class JobRunner:
    def __init__(self, db: Database, registry: dict[str, JobFn]) -> None:
        self.db = db
        self.registry = registry
        self._queue: queue.Queue[object] = queue.Queue()
        self._submit_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # Önceki oturumdan yarım kalan işler artık çalışmayacak.
        self.db.cursor().execute(
            "UPDATE jobs SET status = 'failed', error = 'Uygulama kapandığı için yarıda kaldı',"
            " finished_at = current_timestamp WHERE status IN ('queued', 'running')"
        )
        self._thread = threading.Thread(target=self._loop, name="job-runner", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        if self._thread is None:
            return
        self._queue.put(_STOP)
        self._thread.join(timeout)
        self._thread = None

    def submit(self, job_type: str) -> int:
        if job_type not in self.registry:
            raise KeyError(f"Bilinmeyen iş tipi: {job_type}")
        with self._submit_lock:
            cur = self.db.cursor()
            row = cur.execute(
                "SELECT id FROM jobs WHERE type = ? AND status = 'queued' LIMIT 1", [job_type]
            ).fetchone()
            if row:
                return int(row[0])
            row = cur.execute(
                "INSERT INTO jobs (type, status) VALUES (?, 'queued') RETURNING id", [job_type]
            ).fetchone()
            assert row is not None
            job_id = int(row[0])
        self._queue.put((job_id, job_type))
        return job_id

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            job_id, job_type = item  # type: ignore[misc]
            self._run_one(job_id, job_type)

    def _run_one(self, job_id: int, job_type: str) -> None:
        cur = self.db.cursor()
        cur.execute(
            "UPDATE jobs SET status = 'running', started_at = current_timestamp WHERE id = ?",
            [job_id],
        )
        try:
            self.registry[job_type](JobContext(job_id=job_id, db=self.db))
        except Exception as e:
            log.exception("İş başarısız: %s #%s", job_type, job_id)
            cur.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished_at = current_timestamp"
                " WHERE id = ?",
                [f"{type(e).__name__}: {e}", job_id],
            )
            return
        cur.execute(
            "UPDATE jobs SET status = 'done', finished_at = current_timestamp WHERE id = ?",
            [job_id],
        )
