-- Faz 1: katalog tabloları.
-- İlişki tablolarında PK yoktur: senkronda satırlar aynı transaction içinde silinip yeniden
-- yazılır, DuckDB'nin unique index kontrolü bu desende hata verebilir. Tekillik yazarken sağlanır.

CREATE TABLE movies (
    tmdb_id           BIGINT PRIMARY KEY,
    title_tr          VARCHAR NOT NULL,
    title_original    VARCHAR NOT NULL,
    original_language VARCHAR,
    overview_tr       VARCHAR,
    overview_en       VARCHAR,
    release_date      DATE,
    runtime           INTEGER,
    vote_average      DOUBLE,
    vote_count        INTEGER,
    popularity        DOUBLE,
    poster_path       VARCHAR,
    backdrop_path     VARCHAR,
    embedding         FLOAT[1024],
    embedding_stale   BOOLEAN NOT NULL DEFAULT TRUE,
    synced_at         TIMESTAMP NOT NULL
);

CREATE TABLE genres (
    id      BIGINT PRIMARY KEY,
    name_tr VARCHAR NOT NULL
);

CREATE TABLE movie_genre (
    movie_id BIGINT NOT NULL,
    genre_id BIGINT NOT NULL
);

CREATE TABLE keywords (
    id   BIGINT PRIMARY KEY,
    name VARCHAR NOT NULL,
    df   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE movie_keyword (
    movie_id   BIGINT NOT NULL,
    keyword_id BIGINT NOT NULL
);

CREATE TABLE people (
    id           BIGINT PRIMARY KEY,
    name         VARCHAR NOT NULL,
    profile_path VARCHAR
);

CREATE TABLE movie_person (
    movie_id   BIGINT NOT NULL,
    person_id  BIGINT NOT NULL,
    role       VARCHAR NOT NULL CHECK (role IN ('director', 'writer', 'cast')),
    cast_order INTEGER
);

CREATE TABLE movie_providers (
    movie_id      BIGINT NOT NULL,
    provider_id   BIGINT NOT NULL,
    provider_name VARCHAR NOT NULL,
    type          VARCHAR NOT NULL CHECK (type IN ('flatrate', 'rent', 'buy')),
    logo_path     VARCHAR
);

CREATE TABLE skipped_tmdb_ids (
    tmdb_id BIGINT PRIMARY KEY,
    reason  VARCHAR NOT NULL
);
