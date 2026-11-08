-- Faz 1: kullanıcı verisi, zevk modeli ve öneri tabloları (sonraki fazlarda doldurulur).

CREATE TABLE ratings (
    movie_id BIGINT PRIMARY KEY,
    score    INTEGER NOT NULL CHECK (score BETWEEN 1 AND 5),
    rated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE onboarding_skips (
    movie_id BIGINT PRIMARY KEY
);

CREATE SEQUENCE taste_clusters_id_seq START 1;

CREATE TABLE taste_clusters (
    id           BIGINT PRIMARY KEY DEFAULT nextval('taste_clusters_id_seq'),
    label        VARCHAR,
    label_locked BOOLEAN NOT NULL DEFAULT FALSE,
    description  VARCHAR,
    centroid     FLOAT[1024],
    weight       DOUBLE,
    size         INTEGER,
    top_keywords VARCHAR[],
    is_negative  BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at  TIMESTAMP
);

CREATE TABLE taste_cluster_movie (
    cluster_id BIGINT NOT NULL,
    movie_id   BIGINT NOT NULL,
    membership DOUBLE NOT NULL
);

CREATE TABLE recommendation_feedback (
    movie_id   BIGINT NOT NULL,
    action     VARCHAR NOT NULL CHECK (action IN ('dismissed', 'saved', 'watched')),
    cluster_id BIGINT,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE watchlist (
    movie_id BIGINT PRIMARY KEY,
    added_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE TABLE recommendation_explanations (
    movie_id     BIGINT NOT NULL,
    cluster_id   BIGINT NOT NULL,
    text         VARCHAR NOT NULL,
    generated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    PRIMARY KEY (movie_id, cluster_id)
);
