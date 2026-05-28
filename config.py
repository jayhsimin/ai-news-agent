"""
全域設定模組
使用 pydantic-settings 管理所有環境變數，支援 .env 檔案載入
"""

from functools import lru_cache
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    系統全域設定，所有值均可透過環境變數或 .env 覆蓋
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定義的環境變數，避免啟動錯誤
    )

    # ── 應用程式基本設定 ──
    APP_NAME: str = "AI News Agent"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ── Redis / Celery ──
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # ── Qdrant 向量資料庫 ──
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "ai_news"
    VECTOR_SIZE: int = 384  # all-MiniLM-L6-v2 輸出維度

    # ── Ollama 本地 LLM ──
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_TIMEOUT: int = 120  # 秒

    # ── Embedding 設定 ──
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    SIMILARITY_THRESHOLD: float = 0.85  # 去重門檻

    # ── Reddit（免費官方 API）──
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USER_AGENT: str = "ai-news-agent/1.0"
    REDDIT_SUBREDDITS: str = "LocalLLaMA,MachineLearning,singularity,artificial"
    REDDIT_POST_LIMIT: int = 25

    # ── Telegram ──
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TELEGRAM_ENABLED: bool = True

    # ── 排程設定 ──
    COLLECT_INTERVAL_MINUTES: int = 180

    # ── Groq API（GitHub Actions 雲端 LLM，免費）──
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # ── 推播品質門檻 ──
    MIN_RELEVANCE_SCORE: float = 6.0  # 分數低於此值不推播（0~10）

    @field_validator("SIMILARITY_THRESHOLD")
    @classmethod
    def validate_similarity(cls, v: float) -> float:
        """確保相似度門檻在合理範圍內"""
        if not 0.0 <= v <= 1.0:
            raise ValueError("SIMILARITY_THRESHOLD 必須在 0.0 ~ 1.0 之間")
        return v

    @field_validator("MIN_RELEVANCE_SCORE")
    @classmethod
    def validate_score(cls, v: float) -> float:
        """確保相關性分數門檻在合理範圍內"""
        if not 0.0 <= v <= 10.0:
            raise ValueError("MIN_RELEVANCE_SCORE 必須在 0.0 ~ 10.0 之間")
        return v

    @property
    def reddit_subreddits_list(self) -> list[str]:
        """將逗號分隔的 subreddit 字串轉為清單"""
        return [s.strip() for s in self.REDDIT_SUBREDDITS.split(",") if s.strip()]

    @property
    def is_telegram_configured(self) -> bool:
        """檢查 Telegram 是否已設定完整"""
        return bool(
            self.TELEGRAM_ENABLED
            and self.TELEGRAM_BOT_TOKEN
            and self.TELEGRAM_CHAT_ID
        )

    @property
    def is_reddit_configured(self) -> bool:
        """檢查 Reddit API 是否已設定完整"""
        return bool(self.REDDIT_CLIENT_ID and self.REDDIT_CLIENT_SECRET)


@lru_cache()
def get_settings() -> Settings:
    """取得快取的設定實例（整個應用程式生命週期只建立一次）"""
    return Settings()


# 全域設定實例，方便直接 import 使用
settings = get_settings()
