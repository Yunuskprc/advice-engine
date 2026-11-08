"""TMDB istemcisi: hız sınırı, yeniden deneme ve loglama burada toplanır.

Uygulama `TmdbApi` arayüzüne bağımlıdır; testlerde fake kullanılır.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self

import httpx

from app.config import AppSettings

log = logging.getLogger(__name__)

APPEND_TO_RESPONSE = "keywords,credits,translations,watch/providers,release_dates"
_DOWNLOAD_CHUNK_BYTES = 1 << 16

Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]


class TmdbError(RuntimeError):
    """TMDB isteği yeniden denemelere rağmen başarısız oldu."""


class TmdbAuthError(TmdbError):
    """Anahtar eksik veya geçersiz. Tüm işi durdurur."""


class TmdbApi(Protocol):
    async def get_movie(self, tmdb_id: int) -> dict[str, Any] | None: ...

    async def get_changes(self, start: date, end: date, page: int) -> dict[str, Any]: ...

    async def download_export(self, dest_dir: Path, today: date) -> Path: ...

    async def discover_language(self, language: str, page: int) -> dict[str, Any]: ...


def backoff_delay(attempt: int, base: float) -> float:
    """1. başarısızlık için `base`, sonraki her başarısızlıkta iki katı."""
    return base * 2 ** (attempt - 1)


class TokenBucket:
    """Async token bucket. `pause` tüm istekleri belirtilen süre boyunca bekletir."""

    def __init__(self, rate: float, burst: int, clock: Clock, sleep: Sleep) -> None:
        self.rate = rate
        self.burst = burst
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._last = clock()
        self._paused_until = 0.0

    def pause(self, seconds: float) -> None:
        self._paused_until = max(self._paused_until, self._clock() + seconds)

    async def acquire(self) -> None:
        while True:
            now = self._clock()
            if now < self._paused_until:
                await self._sleep(self._paused_until - now)
                continue
            self._tokens = min(self.burst, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= 1:
                self._tokens -= 1
                return
            await self._sleep((1 - self._tokens) / self.rate)


class TmdbClient:
    def __init__(
        self,
        settings: AppSettings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        self.s = settings
        self._sleep = sleep
        self._bucket = TokenBucket(settings.tmdb_rate_per_s, settings.tmdb_rate_burst, clock, sleep)
        self._http = httpx.AsyncClient(
            base_url=settings.tmdb_base_url,
            timeout=settings.tmdb_timeout_s,
            transport=transport,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=settings.tmdb_max_concurrency),
        )

    async def __aenter__(self) -> Self:
        self._auth({})  # Anahtar yoksa iş başlamadan hata ver.
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._http.aclose()

    def _auth(self, params: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
        if self.s.tmdb_read_token:
            return {"Authorization": f"Bearer {self.s.tmdb_read_token}"}, params
        if self.s.tmdb_api_key:
            return {}, {**params, "api_key": self.s.tmdb_api_key}
        raise TmdbAuthError(".env içinde TMDB_READ_TOKEN veya TMDB_API_KEY tanımlı değil.")

    def _retry_after(self, response: httpx.Response) -> float:
        try:
            return float(response.headers["Retry-After"])
        except (KeyError, ValueError):
            return self.s.tmdb_retry_after_default_s

    async def _on_failure(self, failures: int, what: str) -> int:
        failures += 1
        if failures >= self.s.tmdb_max_attempts:
            raise TmdbError(f"{what}: {failures} denemede başarısız")
        await self._sleep(backoff_delay(failures, self.s.tmdb_backoff_base_s))
        return failures

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        headers, query = self._auth(params)
        failures = 0
        while True:
            await self._bucket.acquire()
            try:
                r = await self._http.get(path, params=query, headers=headers)
            except httpx.TransportError as e:
                failures = await self._on_failure(failures, f"{path} ({type(e).__name__})")
                continue
            if r.status_code == 429:
                delay = self._retry_after(r)
                log.warning("TMDB 429, %.1f sn bekleniyor", delay)
                self._bucket.pause(delay)
                continue
            if r.status_code >= 500:
                failures = await self._on_failure(failures, f"{path} (HTTP {r.status_code})")
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 401:
                raise TmdbAuthError(
                    "TMDB anahtarı geçersiz (HTTP 401). .env dosyasını kontrol edin."
                )
            if r.status_code >= 400:
                raise TmdbError(f"{path}: HTTP {r.status_code}")
            return r.json()

    async def get_movie(self, tmdb_id: int) -> dict[str, Any] | None:
        return await self._get(
            f"/movie/{tmdb_id}",
            {"language": self.s.tmdb_language, "append_to_response": APPEND_TO_RESPONSE},
        )

    async def get_changes(self, start: date, end: date, page: int) -> dict[str, Any]:
        params = {"start_date": start.isoformat(), "end_date": end.isoformat(), "page": page}
        data = await self._get("/movie/changes", params)
        if data is None:
            raise TmdbError("/movie/changes: HTTP 404")
        return data

    async def discover_language(self, language: str, page: int) -> dict[str, Any]:
        """Belirli bir orijinal dildeki, oy eşiğini geçen filmleri listeler."""
        data = await self._get(
            "/discover/movie",
            {
                "with_original_language": language,
                "vote_count.gte": self.s.tmdb_min_votes,
                "sort_by": "vote_count.desc",
                "include_adult": "false",
                "page": page,
            },
        )
        if data is None:
            raise TmdbError("/discover/movie: HTTP 404")
        return data

    async def download_export(self, dest_dir: Path, today: date) -> Path:
        """En güncel günlük ID export'unu diske indirir (key gerekmez, belleğe alınmaz)."""
        for days_back in range(self.s.tmdb_export_lookback_days + 1):
            day = today - timedelta(days=days_back)
            url = self.s.tmdb_export_url.format(date=day.strftime("%m_%d_%Y"))
            dest = dest_dir / url.rsplit("/", 1)[-1]
            try:
                async with self._http.stream("GET", url) as r:
                    if r.status_code in (403, 404):
                        continue  # O günün dosyası henüz yayınlanmamış.
                    r.raise_for_status()
                    with dest.open("wb") as f:
                        async for chunk in r.aiter_bytes(_DOWNLOAD_CHUNK_BYTES):
                            f.write(chunk)
            except httpx.HTTPError as e:
                raise TmdbError(f"Export indirilemedi: {type(e).__name__}") from e
            return dest
        raise TmdbError("Son günlere ait TMDB export dosyası bulunamadı.")
