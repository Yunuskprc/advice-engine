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
    embed_batch_size: int = 64

    # TMDB
    tmdb_read_token: str = ""
    tmdb_api_key: str = ""
    tmdb_base_url: str = "https://api.themoviedb.org/3"
    tmdb_export_url: str = "https://files.tmdb.org/p/exports/movie_ids_{date}.json.gz"
    tmdb_export_lookback_days: int = 3
    tmdb_language: str = "tr-TR"
    tmdb_watch_region: str = "TR"
    tmdb_timeout_s: float = 30.0

    # TMDB katalog filtreleri
    tmdb_min_popularity: float = 1.0
    tmdb_min_votes: int = 20
    tmdb_min_runtime: int = 40
    tmdb_priority_languages: list[str] = ["tr"]
    tmdb_discover_max_pages: int = 500

    # TMDB hız sınırı ve yeniden deneme
    tmdb_rate_per_s: float = 30.0
    tmdb_rate_burst: int = 5
    tmdb_max_concurrency: int = 20
    tmdb_max_attempts: int = 5
    tmdb_backoff_base_s: float = 1.0
    tmdb_retry_after_default_s: float = 5.0

    # Import ve senkron
    tmdb_batch_size: int = 500
    tmdb_changes_max_days: int = 14
    tmdb_sync_overlap_days: int = 1

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
    cluster_top_keywords: int = 10
    cluster_typical_display: int = 5
    cluster_title_genres: int = 2
    cluster_domestic_share: float = 0.5
    insight_min_answers: int = 20
    insight_high: float = 1.2
    insight_low: float = 0.6
    insight_favorite_count: int = 3
    insight_avoid_count: int = 3

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
    score_watchlist_threshold: float = 0.5
    bayes_m: int = 500

    # Benzer filmler
    similar_default_limit: int = 20
    similar_max_limit: int = 100

    # Puanlama modu
    onboarding_warmup_ratings: int = 30
    onboarding_explore_ratings: int = 150
    # Türk filmi sıklığı izleme eğilimine bağlıdır (kaç kartta bir).
    onboarding_tr_every_min: int = 3
    onboarding_tr_every_max: int = 7
    onboarding_warmup_window: int = 8
    onboarding_tr_pool: int = 500
    # Puan arttıkça havuz büyür, popülerliğin payı azalır (0 puandan keşif sonuna kadar).
    onboarding_pool_start: int = 300
    onboarding_pool_end: int = 3000
    onboarding_pop_weight_start: float = 1.0
    onboarding_pop_weight_end: float = 0.2
    # Önceki cevaplara uyum: tür/dönem izlenme eğilimi.
    onboarding_fit_weight: float = 6.0
    onboarding_fit_strength: float = 2.0
    onboarding_fit_genre_share: float = 0.45
    onboarding_fit_decade_share: float = 0.25
    onboarding_fit_language_share: float = 0.30
    # İzleme oranı bu değerin altındaysa popülerlik daha yavaş azalır.
    onboarding_hit_target: float = 0.5
    onboarding_shortlist: int = 300
    # Seçilen kategoriler: başlangıç eğilimi, puan arttıkça genel izleme oranına esner.
    onboarding_pref_selected: float = 0.9
    onboarding_pref_other: float = 0.2
    onboarding_pref_relax_ratings: int = 60
    onboarding_pref_influence_end: float = 0.15
    onboarding_batch: int = 12
    onboarding_max_batch: int = 30
    onboarding_target_ratings: int = 100
    onboarding_refine_mid_similarity: float = 0.5

    # Arama
    search_default_limit: int = 20
    search_max_limit: int = 50
    search_fuzzy_threshold: float = 0.85

    # Çeşitlendirme
    mmr_lambda: float = 0.7
    mmr_pool_size: int = 200
    result_count: int = 20
    max_per_director: int = 2

    # Açıklama ve filtre seçenekleri
    explain_ref_count: int = 2
    explain_keyword_count: int = 3
    filter_provider_limit: int = 30


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()


@lru_cache
def get_recommender_settings() -> RecommenderSettings:
    return RecommenderSettings()
