"""
Qdrant 向量資料庫操作層
負責向量的儲存、查詢、和去重比對
Collection 在首次使用時自動建立
"""

import uuid
from typing import Optional
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    SearchRequest,
)

from collectors.base import NewsItem
from config import settings


class QdrantStore:
    """
    Qdrant 向量資料庫存取層
    提供 upsert、search、exists 等操作
    """

    def __init__(self):
        # 初始化 Qdrant 客戶端（同步版本，與 Celery tasks 相容）
        self._client = None

    @property
    def client(self) -> QdrantClient:
        """懶載入 Qdrant 客戶端並確保 collection 存在"""
        if self._client is None:
            self._client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                timeout=30,
            )
            self._ensure_collection()
        return self._client

    def _ensure_collection(self) -> None:
        """
        確保 Qdrant collection 存在
        若不存在則自動建立，使用 Cosine 相似度（與正規化 embedding 相容）
        """
        try:
            existing = [c.name for c in self._client.get_collections().collections]
            if settings.QDRANT_COLLECTION not in existing:
                self._client.create_collection(
                    collection_name=settings.QDRANT_COLLECTION,
                    vectors_config=VectorParams(
                        size=settings.VECTOR_SIZE,      # 384（all-MiniLM-L6-v2）
                        distance=Distance.COSINE,        # cosine 相似度
                    ),
                )
                logger.info(f"Qdrant collection '{settings.QDRANT_COLLECTION}' 建立完成")
            else:
                logger.debug(f"Qdrant collection '{settings.QDRANT_COLLECTION}' 已存在")
        except Exception as e:
            logger.error(f"Qdrant collection 初始化失敗：{e}")
            raise

    def upsert(self, item: NewsItem, embedding: list[float]) -> str:
        """
        儲存文章向量至 Qdrant
        使用 URL 的 MD5 hash 作為 deterministic ID，避免重複插入

        回傳值：儲存的 point ID（UUID 格式）
        """
        # 使用 source_id 的 hash 生成 UUID，確保同一 URL 不重複插入
        source_id = item.get_source_id()
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_id))

        payload = {
            "source_id": source_id,
            "source": item.source,
            "title": item.title,
            "url": item.url,
            "author": item.author,
            "published_at": item.published_at,
            "tags": item.tags,
            "summary": item.summary or "",
            "category": item.category or "",
            "relevance_score": item.relevance_score or 0.0,
        }

        self.client.upsert(
            collection_name=settings.QDRANT_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )
        return point_id

    def exists_by_source_id(self, source_id: str) -> bool:
        """
        透過 source_id 判斷文章是否已存在（精確比對）
        比語意搜尋快，優先使用
        """
        try:
            results = self.client.scroll(
                collection_name=settings.QDRANT_COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="source_id",
                            match=MatchValue(value=source_id),
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False,
            )
            return len(results[0]) > 0
        except Exception as e:
            logger.error(f"Qdrant exists 查詢失敗：{e}")
            return False

    def search_similar(
        self,
        embedding: list[float],
        limit: int = 5,
        score_threshold: float = 0.85,
    ) -> list[dict]:
        """
        語意相似度搜尋
        找出相似度超過門檻的文章，用於去重判斷

        回傳值：[{"score": float, "payload": dict}, ...]
        """
        try:
            results = self.client.search(
                collection_name=settings.QDRANT_COLLECTION,
                query_vector=embedding,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )
            return [
                {"score": hit.score, "payload": hit.payload}
                for hit in results
            ]
        except Exception as e:
            logger.error(f"Qdrant 語意搜尋失敗：{e}")
            return []

    def get_stats(self) -> dict:
        """取得 collection 統計資訊（供 API 狀態頁面顯示）"""
        try:
            info = self.client.get_collection(settings.QDRANT_COLLECTION)
            return {
                "total_vectors": info.vectors_count,
                "indexed_vectors": info.indexed_vectors_count,
                "status": info.status.value,
            }
        except Exception as e:
            logger.error(f"Qdrant 取得統計失敗：{e}")
            return {"error": str(e)}
