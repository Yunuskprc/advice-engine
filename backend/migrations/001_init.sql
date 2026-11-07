-- Faz 0: JobRunner durum tablosu. Katalog tabloları Faz 1'de 002+ ile gelir.

CREATE SEQUENCE jobs_id_seq START 1;

CREATE TABLE jobs (
    id          BIGINT PRIMARY KEY DEFAULT nextval('jobs_id_seq'),
    type        VARCHAR NOT NULL,
    status      VARCHAR NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    progress    BIGINT NOT NULL DEFAULT 0,
    total       BIGINT,
    error       VARCHAR,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    started_at  TIMESTAMP,
    finished_at TIMESTAMP
);
