-- Kullanıcının seçtiği kategoriler: puanlama kartları için başlangıç eğilimi.
-- PK yoktur: seçim aynı transaction içinde silinip yeniden yazılır.

CREATE TABLE preferred_genres (
    genre_id BIGINT NOT NULL
);
