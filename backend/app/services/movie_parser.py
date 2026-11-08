"""TMDB film cevabını veritabanı satırlarına çevirir."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.config import AppSettings

WRITER_JOBS = {"Writer", "Screenplay"}
PROVIDER_TYPES = ("flatrate", "rent", "buy")
TURKISH = "tr"
ENGLISH = "en"
ENGLISH_PREFERRED_REGION = "US"


@dataclass(frozen=True)
class PersonCredit:
    id: int
    name: str
    profile_path: str | None
    role: str
    cast_order: int | None


@dataclass(frozen=True)
class Provider:
    id: int
    name: str
    type: str
    logo_path: str | None


@dataclass
class ParsedMovie:
    tmdb_id: int
    title_tr: str
    title_original: str
    original_language: str | None
    overview_tr: str | None
    overview_en: str | None
    release_date: date | None
    runtime: int | None
    vote_average: float | None
    vote_count: int | None
    popularity: float | None
    poster_path: str | None
    backdrop_path: str | None
    genres: list[tuple[int, str]] = field(default_factory=list)
    keywords: list[tuple[int, str]] = field(default_factory=list)
    people: list[PersonCredit] = field(default_factory=list)
    providers: list[Provider] = field(default_factory=list)


def _clean(value: Any) -> str | None:
    text = value.strip() if isinstance(value, str) else None
    return text or None


def _translation(raw: dict[str, Any], language: str) -> dict[str, Any]:
    items = [
        t
        for t in (raw.get("translations") or {}).get("translations", [])
        if t.get("iso_639_1") == language
    ]
    # Aynı dilin birden çok bölgesi varsa ABD çevirisi önce gelir.
    items.sort(key=lambda t: t.get("iso_3166_1") != ENGLISH_PREFERRED_REGION)
    return (items[0].get("data") or {}) if items else {}


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _unique(items: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return list(dict(items).items())


def skip_reason(raw: dict[str, Any], settings: AppSettings) -> str | None:
    """Film ikinci filtreden geçmiyorsa nedenini döndürür."""
    if raw.get("adult"):
        return "adult"
    if (raw.get("vote_count") or 0) < settings.tmdb_min_votes:
        return "low_votes"
    if (raw.get("runtime") or 0) < settings.tmdb_min_runtime:
        return "short_runtime"
    return None


def _parse_people(raw: dict[str, Any], cast_top_n: int) -> list[PersonCredit]:
    credits = raw.get("credits") or {}
    out: dict[tuple[int, str], PersonCredit] = {}
    for c in credits.get("crew", []):
        role = (
            "director"
            if c.get("job") == "Director"
            else "writer"
            if c.get("job") in WRITER_JOBS
            else None
        )
        if role:
            out[(c["id"], role)] = PersonCredit(
                c["id"], c.get("name") or "", _clean(c.get("profile_path")), role, None
            )
    cast = sorted(credits.get("cast", []), key=lambda c: c.get("order", cast_top_n))
    for c in cast[:cast_top_n]:
        out.setdefault(
            (c["id"], "cast"),
            PersonCredit(
                c["id"], c.get("name") or "", _clean(c.get("profile_path")), "cast", c.get("order")
            ),
        )
    return list(out.values())


def _parse_providers(raw: dict[str, Any], region: str) -> list[Provider]:
    data = ((raw.get("watch/providers") or {}).get("results") or {}).get(region) or {}
    out: dict[tuple[int, str], Provider] = {}
    for kind in PROVIDER_TYPES:
        for p in data.get(kind, []):
            out[(p["provider_id"], kind)] = Provider(
                p["provider_id"],
                p.get("provider_name") or "",
                kind,
                _clean(p.get("logo_path")),
            )
    return list(out.values())


def parse_movie(raw: dict[str, Any], settings: AppSettings, cast_top_n: int) -> ParsedMovie:
    tr = _translation(raw, TURKISH)
    en = _translation(raw, ENGLISH)
    original = _clean(raw.get("original_title")) or _clean(raw.get("title")) or ""
    language = _clean(raw.get("original_language"))
    title_tr = (
        (original if language == TURKISH else None)
        or _clean(tr.get("title"))
        or _clean(en.get("title"))
        or _clean(raw.get("title"))
        or original
    )
    return ParsedMovie(
        tmdb_id=raw["id"],
        title_tr=title_tr,
        title_original=original,
        original_language=language,
        overview_tr=_clean(raw.get("overview")) or _clean(tr.get("overview")),
        overview_en=_clean(en.get("overview")),
        release_date=_parse_date(raw.get("release_date")),
        runtime=raw.get("runtime"),
        vote_average=raw.get("vote_average"),
        vote_count=raw.get("vote_count"),
        popularity=raw.get("popularity"),
        poster_path=_clean(raw.get("poster_path")),
        backdrop_path=_clean(raw.get("backdrop_path")),
        genres=_unique([(g["id"], g.get("name") or "") for g in raw.get("genres", [])]),
        keywords=_unique(
            [
                (k["id"], k.get("name") or "")
                for k in (raw.get("keywords") or {}).get("keywords", [])
            ]
        ),
        people=_parse_people(raw, cast_top_n),
        providers=_parse_providers(raw, settings.tmdb_watch_region),
    )
