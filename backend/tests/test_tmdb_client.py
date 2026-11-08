import asyncio

import httpx
import pytest

from app.clients.tmdb import TmdbAuthError, TmdbClient, TmdbError, backoff_delay


class FakeTime:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _run(settings, responses: list[httpx.Response], tmdb_id: int = 1):
    """Sırayla verilen cevaplarla get_movie çalıştırır; (sonuç, zaman, istek sayısı) döndürür."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return responses[len(calls) - 1]

    t = FakeTime()

    async def go():
        client = TmdbClient(settings, httpx.MockTransport(handler), t.sleep, t.clock)
        async with client:
            return await client.get_movie(tmdb_id)

    return asyncio.run(go()), t, calls


@pytest.fixture
def tmdb_settings(settings):
    return settings.model_copy(update={"tmdb_read_token": "tok"})


def test_backoff_doubles() -> None:
    assert [backoff_delay(i, 1.0) for i in (1, 2, 3)] == [1.0, 2.0, 4.0]


def test_429_waits_retry_after(tmdb_settings) -> None:
    result, t, calls = _run(
        tmdb_settings,
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"id": 1})],
    )
    assert result == {"id": 1}
    assert t.now >= 7
    assert len(calls) == 2


def test_5xx_gives_up_after_max_attempts(tmdb_settings) -> None:
    with pytest.raises(TmdbError):
        _run(tmdb_settings, [httpx.Response(500)] * tmdb_settings.tmdb_max_attempts)


def test_404_returns_none(tmdb_settings) -> None:
    assert _run(tmdb_settings, [httpx.Response(404)])[0] is None


def test_bearer_header_sent(tmdb_settings) -> None:
    _, _, calls = _run(tmdb_settings, [httpx.Response(200, json={})])
    assert calls[0].headers["Authorization"] == "Bearer tok"


def test_missing_key_is_auth_error(settings) -> None:
    with pytest.raises(TmdbAuthError):
        _run(settings, [httpx.Response(200, json={})])
