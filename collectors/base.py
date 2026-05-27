"""
Collector 基礎模組
定義統一的資料 Schema 與 BaseCollector 抽象介面
所有 collector 必須繼承此模組，確保輸出格式一致
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """
    統一的新聞資料 Schema
    所有 collector 必須回傳此格式，確保下游 processor 可統一處理
    """
    source: str = Field(..., description="資料來源，例如 reddit / hackernews / github / arxiv")
    title: str = Field(..., description="標題")
    content: str = Field(default="", description="正文內容（可為空）")
    url: str = Field(..., description="原始連結")
    author: str = Field(default="unknown", description="作者")
    published_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="發布時間（ISO 8601 格式）"
    )
    tags: list[str] = Field(default_factory=list, description="標籤清單")

    # ── 以下為 processor 填入的欄位，collector 不負責 ──
    summary: Optional[str] = Field(default=None, description="LLM 摘要（由 processor 填入）")
    category: Optional[str] = Field(default=None, description="分類（由 processor 填入）")
    relevance_score: Optional[float] = Field(default=None, description="相關性分數 0~10（由 processor 填入）")
    is_duplicate: bool = Field(default=False, description="是否為重複資訊（由 deduplicator 填入）")
    embedding_id: Optional[str] = Field(default=None, description="Qdrant 向量 ID")

    def get_full_text(self) -> str:
        """取得用於 embedding 的完整文字（標題 + 內容）"""
        parts = [self.title]
        if self.content:
            # 取前 1000 字，避免超過 embedding 模型上限
            parts.append(self.content[:1000])
        return " ".join(parts)

    def get_source_id(self) -> str:
        """從 URL 生成唯一識別碼，用於查重"""
        import hashlib
        return hashlib.md5(self.url.encode()).hexdigest()


class BaseCollector(ABC):
    """
    Collector 抽象基底類別
    所有資料來源的 collector 必須繼承並實作 collect() 方法
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def collect(self) -> list[NewsItem]:
        """
        採集資料並回傳 NewsItem 清單
        子類別必須實作此方法
        """
        raise NotImplementedError

    async def safe_collect(self) -> list[NewsItem]:
        """
        帶有例外處理的採集方法
        任何 collector 失敗時，不影響其他 collector 的執行
        """
        from loguru import logger
        try:
            items = await self.collect()
            logger.info(f"[{self.name}] 採集完成，共 {len(items)} 筆")
            return items
        except Exception as e:
            logger.error(f"[{self.name}] 採集失敗：{e}")
            return []
