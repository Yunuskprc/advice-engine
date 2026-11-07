"""Uygulama ayarları. Tüm eşikler ve katsayılar burada veya .env'de durur."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class AppSettings(BaseSettings):
    """Ortam ayarları (.env)."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Yollar
    db_path: Path = Path("data/film.duckdb")
    migrations_dir: Path = Path("backend/migrations")
    frontend_dist: Path = Path("frontend/dist")

    # DuckDB
    duckdb_extensions: list[str] = ["vss", "fts"]

    # Sunucu
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "bge-m3"
    ollama_chat_model: str = "qwen3:8b"
    ollama_timeout_s: float = 120.0
    ollama_health_timeout_s: float = 2.0
    ollama_ping_max_tokens: int = 32
    embedding_dim: int = 1024

    # TMDB (Faz 1)
    tmdb_read_token: str = ""
    tmdb_api_key: str = ""

    # Örnek iş (Faz 0 kabul testi)
    demo_job_steps: int = 10
    demo_job_step_seconds: float = 0.5

    @field_validator("db_path", "migrations_dir", "frontend_dist")
    @classmethod
    def _resolve(cls, v: Path) -> Path:
        return v if v.is_absolute() else (PROJECT_ROOT / v).resolve()


class RecommenderSettings(BaseSettings):
    """Öneri motoru katsayıları (MIMARI.md). .env'de REC_ önekiyle ezilebilir."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE, env_file_encoding="utf-8", env_prefix="REC_", extra="ignore"
    )

    # Hibrit benzerlik
    sim_semantic_weight: float = 0.75
    sim_structural_weight: float = 0.25

    # Yapısal özellik ağırlıkları
    feat_keyword_weight: float = 1.0  # IDF ile çarpılır
    feat_director_weight: float = 1.5
    feat_writer_weight: float = 0.8
    feat_cast_weight: float = 0.4
    feat_genre_weight: float = 0.3
    feat_language_weight: float = 0.2
    feat_cast_top_n: int = 5
    embed_max_keywords: int = 20

    # Puan ağırlıkları
    rating_weights: dict[int, float] = {5: 1.0, 4: 0.5, 3: 0.0, 2: -0.5, 1: -1.0}
    dismissed_weight: float = -0.3
    watchlist_weight: float = 0.2

    # Kümeleme
    cluster_min_positive: int = 15
    cluster_k_min: int = 2
    cluster_k_max: int = 10
    cluster_k_per_n: int = 8  # k_max = min(cluster_k_max, n / cluster_k_per_n)
    cluster_min_size: int = 8
    cluster_n_init: int = 5
    cluster_random_state: int = 42
    negative_split_threshold: int = 10
    negative_max_clusters: int = 3
    recompute_every_n_ratings: int = 10

    # Aday toplama
    candidate_center_top_n: int = 400
    candidate_typical_n: int = 10
    candidate_per_typical_n: int = 30
    candidate_min_vote_count: int = 50
    surprise_weight_exponent: float = 0.5

    # Skorlama
    score_cluster_weight: float = 0.50
    score_best_five_weight: float = 0.20
    score_quality_weight: float = 0.15
    score_repulsion_weight: float = 0.40
    score_repulsion_threshold: float = 0.5
    score_explore_weight: float = 0.15
    bayes_m: int = 500

    # Çeşitlendirme
    mmr_lambda: float = 0.7
    mmr_pool_size: int = 200
    result_count: int = 20
    max_per_director: int = 2


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


@lru_cache
def get_recommender_settings() -> RecommenderSettings:
    return RecommenderSettings()
