-- Kategori seçimi yerine zevk grupları (grup, tür ve dil eğilimine çevrilir).
-- PK yoktur: seçim aynı transaction içinde silinip yeniden yazılır.

DROP TABLE preferred_genres;

CREATE TABLE preferred_groups (
    group_id VARCHAR NOT NULL
);
