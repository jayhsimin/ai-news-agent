"""
Embedding 處理器
使用 sentence-transformers 的 all-MiniLM-L6-v2 模型
將文字轉換為 384 維向量，用於去重與語意搜尋
完全本地執行，免費，不需要 API Key
"""

from functools import lru_cache
from loguru import logger
import numpy as np


@lru_cache(maxsize=1)
def get_embedding_model():
    """
    單例模式載入 embedding 模型
    使用 lru_cache 確保整個應用生命週期只載入一次，避免記憶體浪費
    模型約 80MB，第一次執行時自動從 HuggingFace 下載
    """
    from sentence_transformers import SentenceTransformer
    from config import settings

    logger.info(f"載入 embedding 模型：{settings.EMBEDDING_MODEL}")
    model = SentenceTransformer(settings.EMBEDDING_MODEL)
    logger.info("Embedding 模型載入完成")
    return model


class Embedder:
    """
    文字向量化處理器
    將 NewsItem 的文字內容轉換為固定維度的向量
    """

    def __init__(self):
        # 延遲載入，避免 import 時就佔用記憶體
        self._model = None

    @property
    def model(self):
        """懶載入模型"""
        if self._model is None:
            self._model = get_embedding_model()
        return self._model

    def embed(self, text: str) -> list[float]:
        """
        將單段文字轉換為向量

        回傳值：長度 384 的 float list（符合 Qdrant 儲存格式）
        """
        if not text or not text.strip():
            # 空文字回傳零向量（避免 Qdrant 儲存失敗）
            from config import settings
            return [0.0] * settings.VECTOR_SIZE

        embedding = self.model.encode(
            text,
            normalize_embeddings=True,  # 正規化，讓 cosine similarity = dot product
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """
        批次向量化，效率比逐一呼叫高
        適合一次處理多篇文章時使用
        """
        if not texts:
            return []

        logger.debug(f"批次 embedding：{len(texts)} 筆文字")
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """
        計算兩向量的 cosine 相似度（0~1）
        由於向量已正規化，直接做 dot product 即可
        """
        a = np.array(vec1)
        b = np.array(vec2)
        # 向量正規化後 dot product = cosine similarity
        return float(np.dot(a, b))
