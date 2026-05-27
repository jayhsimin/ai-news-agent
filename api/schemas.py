"""
FastAPI 請求/回應 Schema 定義
"""

from typing import Any, Optional
from pydantic import BaseModel


class TriggerResponse(BaseModel):
    """手動觸發任務的回應"""
    success: bool
    task_id: Optional[str] = None
    message: str


class StatusResponse(BaseModel):
    """系統狀態回應"""
    app_name: str
    version: str
    services: dict[str, Any]
    qdrant_stats: dict[str, Any]


class HealthResponse(BaseModel):
    """健康檢查回應"""
    status: str
    services: dict[str, Any]


class TaskStatusResponse(BaseModel):
    """Celery 任務狀態查詢回應"""
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
