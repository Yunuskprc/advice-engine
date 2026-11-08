"""Film detayı."""

from app.api.schemas import MovieDetail, PersonOut, ProviderOut
from app.db import Database
from app.services.similar import MovieNotFoundError


def movie_detail(db: Database, tmdb_id: int) -> MovieDetail:
    cur = db.cursor()
    m = cur.execute(
        "SELECT title_tr, title_original, year(release_date), runtime,"
        " coalesce(overview_tr, overview_en), vote_average, vote_count, poster_path, backdrop_path,"
        " (SELECT score FROM ratings WHERE movie_id = tmdb_id),"
        " EXISTS (SELECT 1 FROM watchlist WHERE movie_id = tmdb_id)"
        " FROM movies WHERE tmdb_id = ?",
        [tmdb_id],
    ).fetchone()
    if m is None:
        raise MovieNotFoundError(tmdb_id)

    genres = cur.execute(
        "SELECT g.name_tr FROM movie_genre mg JOIN genres g ON g.id = mg.genre_id"
        " WHERE mg.movie_id = ? ORDER BY g.name_tr",
        [tmdb_id],
    ).fetchall()
    keywords = cur.execute(
        "SELECT k.name FROM movie_keyword mk JOIN keywords k ON k.id = mk.keyword_id"
        " WHERE mk.movie_id = ? ORDER BY k.df, k.id",
        [tmdb_id],
    ).fetchall()
    people = cur.execute(
        "SELECT mp.role, p.id, p.name, p.profile_path FROM movie_person mp"
        " JOIN people p ON p.id = mp.person_id"
        " WHERE mp.movie_id = ? AND mp.role IN ('director', 'cast')"
        " ORDER BY mp.cast_order NULLS LAST, p.name",
        [tmdb_id],
    ).fetchall()
    providers = cur.execute(
        "SELECT provider_id, provider_name, type, logo_path FROM movie_providers"
        " WHERE movie_id = ? ORDER BY type, provider_name",
        [tmdb_id],
    ).fetchall()

    def persons(role: str) -> list[PersonOut]:
        return [PersonOut(id=p[1], name=p[2], profile_path=p[3]) for p in people if p[0] == role]

    return MovieDetail(
        tmdb_id=tmdb_id,
        title_tr=m[0],
        title_original=m[1],
        year=m[2],
        runtime=m[3],
        overview=m[4],
        vote_average=m[5],
        vote_count=m[6],
        poster_path=m[7],
        backdrop_path=m[8],
        my_rating=m[9],
        in_watchlist=m[10],
        genres=[g[0] for g in genres],
        keywords=[k[0] for k in keywords],
        directors=persons("director"),
        cast=persons("cast"),
        providers=[ProviderOut(id=p[0], name=p[1], type=p[2], logo_path=p[3]) for p in providers],
    )
