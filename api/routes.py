"""
FastAPI 路由定義
提供系統狀態查詢、手動觸發、健康檢查等端點
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from loguru import logger

from api.schemas import TriggerResponse, StatusResponse, HealthResponse, TaskStatusResponse
from config import settings

router = APIRouter()


@router.get("/", summary="歡迎頁面")
async def root():
    """系統基本資訊"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "/api/status",
    }


@router.get("/api/status", response_model=StatusResponse, summary="系統狀態")
async def get_status():
    """
    取得系統整體狀態
    包含各服務連線狀況和 Qdrant 統計
    """
    from db.qdrant_store import QdrantStore

    services = {
        "redis": {"configured": True},
        "qdrant": {"configured": True},
        "ollama": {"url": settings.OLLAMA_BASE_URL, "model": settings.OLLAMA_MODEL},
        "telegram": {"configured": settings.is_telegram_configured},
        "reddit": {"configured": settings.is_reddit_configured},
    }

    try:
        store = QdrantStore()
        qdrant_stats = store.get_stats()
    except Exception as e:
        qdrant_stats = {"error": str(e)}

    return StatusResponse(
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
        services=services,
        qdrant_stats=qdrant_stats,
    )


@router.post("/api/trigger/pipeline", response_model=TriggerResponse, summary="手動觸發完整 Pipeline")
async def trigger_pipeline():
    """
    手動觸發完整的採集 → 分析 → 推播 pipeline
    任務在 Celery Worker 背景執行，立即回傳 task_id
    """
    try:
        from tasks.pipeline import run_full_pipeline
        task = run_full_pipeline.delay()
        logger.info(f"[API] 手動觸發 pipeline，task_id：{task.id}")
        return TriggerResponse(
            success=True,
            task_id=task.id,
            message=f"Pipeline 已啟動，task_id：{task.id}",
        )
    except Exception as e:
        logger.error(f"[API] 觸發 pipeline 失敗：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/trigger/collect", response_model=TriggerResponse, summary="手動觸發採集")
async def trigger_collect():
    """
    只執行採集步驟（不含分析和推播）
    用於測試採集器是否正常運作
    """
    try:
        from tasks.pipeline import collect_task
        task = collect_task.delay()
        return TriggerResponse(
            success=True,
            task_id=task.id,
            message=f"採集任務已啟動，task_id：{task.id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/trigger/health-check", response_model=TriggerResponse, summary="觸發健康檢查")
async def trigger_health_check():
    """
    觸發非同步健康檢查（檢查 Ollama / Qdrant / Telegram）
    """
    try:
        from tasks.pipeline import health_check_task
        task = health_check_task.delay()
        return TriggerResponse(
            success=True,
            task_id=task.id,
            message=f"健康檢查已啟動，task_id：{task.id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/task/{task_id}", response_model=TaskStatusResponse, summary="查詢任務狀態")
async def get_task_status(task_id: str):
    """
    查詢 Celery 任務執行狀態與結果
    """
    from celery.result import AsyncResult
    from tasks.celery_app import celery_app

    task_result = AsyncResult(task_id, app=celery_app)

    return TaskStatusResponse(
        task_id=task_id,
        status=task_result.status,
        result=task_result.result if task_result.successful() else None,
        error=str(task_result.result) if task_result.failed() else None,
    )


@router.get("/api/health", summary="快速健康檢查")
async def health_check():
    """
    輕量級健康檢查（不需要 Celery Worker 也能回應）
    適合 load balancer / container healthcheck 使用
    """
    return {"status": "ok", "service": settings.APP_NAME}
