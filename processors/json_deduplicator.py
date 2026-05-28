"""
JSON 檔案型去重器
以 URL MD5 hash 為基礎，不依賴 Qdrant 或 Redis
適用於 GitHub Actions 無狀態環境，透過 actions/cache 在 run 之間持久化
"""

import json
import hashlib
from pathlib import Path
from loguru import logger

from collectors.base import NewsItem

# 保留最近 N 筆，避免 JSON 無限增長
MAX_SEEN_ENTRIES = 3000
DEFAULT_CACHE_FILE = "seen_urls.json"


class JsonDeduplicator:
    """
    URL hash 去重器
    讀寫 seen_urls.json，在 GitHub Actions run 之間透過 cache 持久化
    """

    def __init__(self, cache_path: str = DEFAULT_CACHE_FILE):
        self.cache_path = Path(cache_path)
        self._seen: set[str] = self._load()

    def _load(self) -> set[str]:
        if self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                logger.info(f"[去重] 載入快取 {len(data)} 筆：{self.cache_path}")
                return set(data)
            except Exception as e:
                logger.warning(f"[去重] 快取讀取失敗，從空白開始：{e}")
        return set()

    def save(self) -> None:
        """將目前已見 URL 集合寫回 JSON 檔（GitHub Actions cache 會持久化此檔）"""
        entries = list(self._seen)
        # 超過上限時保留最新的（list 尾端為最近加入）
        if len(entries) > MAX_SEEN_ENTRIES:
            entries = entries[-MAX_SEEN_ENTRIES:]
        self.cache_path.write_text(
            json.dumps(entries, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"[去重] 快取已儲存 {len(entries)} 筆 → {self.cache_path}")

    def is_duplicate(self, item: NewsItem) -> bool:
        return self._url_hash(item.url) in self._seen

    def mark_seen(self, item: NewsItem) -> None:
        self._seen.add(self._url_hash(item.url))

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()
