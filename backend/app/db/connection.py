"""DuckDB bağlantı yönetimi. Bağlantıyı sadece bu modül açar.

Process başına tek bağlantı vardır; her thread kendi cursor'ını kullanır.
"""

import threading
from pathlib import Path

import duckdb

# DuckDB'nin kendi (dilden bağımsız) mesajları; Windows'un OS mesajı yerelleştirilmiş olabilir.
_LOCK_HINTS = ("file is already open", "conflicting lock")


class DatabaseLockedError(RuntimeError):
    """DuckDB dosyası başka bir process tarafından yazma modunda açık."""


class Database:
    def __init__(self, path: Path, extensions: list[str] | None = None) -> None:
        self.path = path
        self.extensions = extensions or []
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._local = threading.local()

    def connect(self) -> None:
        if self._conn is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = duckdb.connect(str(self.path))
        except duckdb.IOException as e:
            if any(h in str(e).lower() for h in _LOCK_HINTS):
                raise DatabaseLockedError(
                    f"Veritabanı dosyası kullanımda: {self.path}\n"
                    "Uygulama (film serve) açık olabilir. Önce uygulamayı kapatıp tekrar deneyin."
                ) from e
            raise
        for ext in self.extensions:
            self._conn.install_extension(ext)
            self._conn.load_extension(ext)

    def cursor(self) -> duckdb.DuckDBPyConnection:
        """Çağıran thread'e ait cursor'ı döndürür (yoksa oluşturur)."""
        if self._conn is None:
            raise RuntimeError("Database.connect() çağrılmadı")
        cur = getattr(self._local, "cursor", None)
        if cur is None:
            cur = self._conn.cursor()
            for ext in self.extensions:
                cur.load_extension(ext)
            self._local.cursor = cur
        return cur

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._local = threading.local()
