"""
去重處理器
使用 Qdrant 向量資料庫進行語意相似度比較
當新文章與已存在文章的相似度超過門檻，視為重複內容跳過
"""

from loguru import logger
from collectors.base import NewsItem
from config import settings


class Deduplicator:
    """
    語意去重處理器
    透過向量相似度判斷文章是否重複，比單純比對 URL 更智慧
    例如：同一事件被多個來源報導 → 相似度高 → 視為重複
    """

    def __init__(self):
        from db.qdrant_store import QdrantStore
        self.store = QdrantStore()

    def is_duplicate(self, item: NewsItem, embedding: list[float]) -> bool:
        """
        檢查文章是否與已存在的內容重複

        判斷邏輯：
        1. 先用 URL hash 做精確比對（最快）
        2. 再用語意相似度比對（更智慧）
        """
        # 步驟一：精確 URL 比對，如果同一篇文章再次出現直接跳過
        if self.store.exists_by_source_id(item.get_source_id()):
            logger.debug(f"[去重] URL 重複：{item.title[:50]}")
            return True

        # 步驟二：語意相似度比對
        similar_items = self.store.search_similar(
            embedding=embedding,
            limit=5,
            score_threshold=settings.SIMILARITY_THRESHOLD,
        )

        if similar_items:
            top_match = similar_items[0]
            logger.debug(
                f"[去重] 語意重複（相似度 {top_match['score']:.3f}）：\n"
                f"  新文章：{item.title[:50]}\n"
                f"  已存在：{top_match['payload'].get('title', '')[:50]}"
            )
            return True

        return False

    def save_item(self, item: NewsItem, embedding: list[float]) -> str:
        """
        將新文章存入 Qdrant，以供後續去重比對
        回傳儲存後的 vector ID
        """
        vector_id = self.store.upsert(item=item, embedding=embedding)
        logger.debug(f"[去重] 已儲存：{item.title[:50]}（ID: {vector_id}）")
        return vector_id
