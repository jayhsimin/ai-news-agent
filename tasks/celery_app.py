"""
Celery 應用程式設定
配置 Broker（Redis）、Result Backend、定時排程
"""

from celery import Celery
from config import settings

# 建立 Celery 應用實例
celery_app = Celery(
    "ai_news_agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks.pipeline"],  # 自動載入 task 模組
)

# ── Celery 全域設定 ──
celery_app.conf.update(
    # 序列化設定
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,  # 結果保留 1 小時

    # 時區設定
    timezone="Asia/Taipei",
    enable_utc=True,

    # Worker 設定
    worker_prefetch_multiplier=1,   # 每個 worker 一次只取一個任務，避免記憶體爆炸
    task_acks_late=True,            # 任務完成後才 ack，確保不遺失

    # 任務隊列設定
    task_routes={
        "tasks.pipeline.collect_task": {"queue": "collect"},
        "tasks.pipeline.analyze_task": {"queue": "analyze"},
        "tasks.pipeline.notify_task": {"queue": "notify"},
        "tasks.pipeline.run_full_pipeline": {"queue": "collect"},
    },

    # 定時排程（Celery Beat）
    beat_schedule={
        # 主採集 pipeline：每 N 分鐘執行一次
        "run-ai-news-pipeline": {
            "task": "tasks.pipeline.run_full_pipeline",
            "schedule": settings.COLLECT_INTERVAL_MINUTES * 60,  # 轉換為秒
            "options": {"queue": "collect"},
        },
    },
)
