"""
Pipeline Tasks
Celery 任務定義：完整的 AI 資訊採集 → 分析 → 推播 pipeline
支援整體執行和分段執行兩種模式
"""

import asyncio
from datetime import datetime
from loguru import logger

from tasks.celery_app import celery_app


def run_async(coro):
    """
    在同步 Celery task 中執行非同步代碼
    注意：每個 task 呼叫都建立新的 event loop，避免 loop 衝突
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 若已有 running loop（不常見），使用 nest_asyncio
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@celery_app.task(
    name="tasks.pipeline.run_full_pipeline",
    bind=True,
    max_retries=2,
    default_retry_delay=60,  # 失敗後 60 秒重試
)
def run_full_pipeline(self):
    """
    完整 pipeline：採集 → 分析 → 推播
    這是定時排程的主要入口任務
    """
    start_time = datetime.utcnow()
    logger.info(f"[Pipeline] 開始執行完整 pipeline，時間：{start_time.isoformat()}")

    try:
        result = run_async(_async_full_pipeline())

        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"[Pipeline] 完整 pipeline 執行完成，耗時：{elapsed:.1f}s")
        return result

    except Exception as exc:
        logger.error(f"[Pipeline] Pipeline 執行失敗：{exc}")
        # 自動重試
        raise self.retry(exc=exc)


async def _async_full_pipeline() -> dict:
    """
    非同步版本的完整 pipeline 邏輯
    依序執行三個 Agent，每個 Agent 的輸出傳入下一個
    """
    from agents.collector_agent import CollectorAgent
    from agents.analyzer_agent import AnalyzerAgent
    from agents.publisher_agent import PublisherAgent

    stats = {}

    # ── 階段 1：採集 ──
    logger.info("[Pipeline] 階段 1/3：資料採集")
    collector = CollectorAgent()
    collect_result = await collector.safe_run()
    stats["collect"] = collect_result.metadata

    if not collect_result.data:
        logger.warning("[Pipeline] 採集結果為空，pipeline 提前結束")
        return {"status": "empty", "stats": stats}

    # ── 階段 2：分析 ──
    logger.info(f"[Pipeline] 階段 2/3：分析 {len(collect_result.data)} 篇文章")
    analyzer = AnalyzerAgent()
    analyze_result = await analyzer.safe_run(collect_result.data)
    stats["analyze"] = analyze_result.metadata

    # ── 階段 3：推播 ──
    logger.info("[Pipeline] 階段 3/3：推播通知")
    publisher = PublisherAgent()
    publish_result = await publisher.safe_run(analyze_result.data)
    stats["publish"] = publish_result.metadata

    return {
        "status": "completed",
        "stats": stats,
        "pushed_count": publish_result.metadata.get("pushed", 0),
    }


@celery_app.task(name="tasks.pipeline.collect_task", queue="collect")
def collect_task():
    """
    單獨執行採集任務（供手動觸發使用）
    回傳採集的文章清單序列化結果
    """
    logger.info("[Task] 執行獨立採集任務")
    result = run_async(_async_collect())
    return result


async def _async_collect() -> dict:
    from agents.collector_agent import CollectorAgent
    agent = CollectorAgent()
    result = await agent.safe_run()
    # 序列化回傳（Celery 需要 JSON 可序列化的結果）
    return {
        "count": len(result.data) if result.data else 0,
        "stats": result.metadata,
    }


@celery_app.task(name="tasks.pipeline.health_check_task", queue="collect")
def health_check_task():
    """
    健康檢查任務，確認各服務是否正常運作
    可透過 API 手動觸發
    """
    result = run_async(_async_health_check())
    return result


async def _async_health_check() -> dict:
    """檢查各服務連線狀態"""
    import httpx
    from config import settings
    from db.qdrant_store import QdrantStore

    status = {}

    # 檢查 Ollama
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            ollama_models = resp.json().get("models", [])
            status["ollama"] = {
                "ok": True,
                "models": [m["name"] for m in ollama_models],
            }
    except Exception as e:
        status["ollama"] = {"ok": False, "error": str(e)}

    # 檢查 Qdrant
    try:
        store = QdrantStore()
        qdrant_stats = store.get_stats()
        status["qdrant"] = {"ok": True, **qdrant_stats}
    except Exception as e:
        status["qdrant"] = {"ok": False, "error": str(e)}

    # 檢查 Telegram
    if settings.is_telegram_configured:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getMe"
                )
                tg_data = resp.json()
                status["telegram"] = {
                    "ok": tg_data.get("ok", False),
                    "bot_name": tg_data.get("result", {}).get("username", ""),
                }
        except Exception as e:
            status["telegram"] = {"ok": False, "error": str(e)}
    else:
        status["telegram"] = {"ok": False, "reason": "未設定 Bot Token"}

    return status
