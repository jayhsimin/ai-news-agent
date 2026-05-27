"""
FastAPI 應用程式主進入點
AI 最新資訊自動推播 Agent 系統
"""

from contextlib import asynccontextmanager
from loguru import logger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    應用程式生命週期管理
    啟動時初始化必要資源，關閉時清理
    """
    # ── 啟動時執行 ──
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 啟動中...")

    # 初始化 Qdrant collection（若不存在則建立）
    try:
        from db.qdrant_store import QdrantStore
        store = QdrantStore()
        stats = store.get_stats()
        logger.info(f"✅ Qdrant 連接成功，已存 {stats.get('total_vectors', 0)} 個向量")
    except Exception as e:
        logger.warning(f"⚠️ Qdrant 初始化失敗（系統仍可啟動）：{e}")

    # 預載入 embedding 模型，避免第一次 task 執行時等待過久
    try:
        from processors.embedder import get_embedding_model
        get_embedding_model()
        logger.info("✅ Embedding 模型載入完成")
    except Exception as e:
        logger.warning(f"⚠️ Embedding 模型預載失敗（第一次執行時會自動重試）：{e}")

    # 檢查 Ollama 是否可用
    try:
        from processors.summarizer import Summarizer
        summarizer = Summarizer()
        ollama_ok = await summarizer.check_ollama_available()
        if ollama_ok:
            logger.info(f"✅ Ollama 服務正常，使用模型：{settings.OLLAMA_MODEL}")
        else:
            logger.warning(
                f"⚠️ Ollama 服務無法連接（{settings.OLLAMA_BASE_URL}）\n"
                f"   請執行：docker exec -it ai-news-ollama ollama pull {settings.OLLAMA_MODEL}"
            )
    except Exception as e:
        logger.warning(f"⚠️ Ollama 檢查失敗：{e}")

    if settings.is_telegram_configured:
        logger.info("✅ Telegram Bot 已設定")
    else:
        logger.warning("⚠️ Telegram Bot 未設定，推播功能將停用")

    logger.info(f"📋 採集間隔：每 {settings.COLLECT_INTERVAL_MINUTES} 分鐘")
    logger.info(f"📊 推播門檻：分數 >= {settings.MIN_RELEVANCE_SCORE}/10")
    logger.info("✅ 系統啟動完成！\n")

    yield  # 應用程式運行中

    # ── 關閉時執行 ──
    logger.info(f"👋 {settings.APP_NAME} 正在關閉...")


# 建立 FastAPI 應用程式
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "AI 最新資訊自動推播 Agent 系統\n\n"
        "自動採集 Reddit / HackerNews / GitHub / arXiv 的 AI 相關資訊，\n"
        "使用本地 LLM 分析後推播到 Telegram。"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 設定（本地開發用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載路由
app.include_router(router)
