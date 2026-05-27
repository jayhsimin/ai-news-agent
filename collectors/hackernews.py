"""
Hacker News Collector
使用官方免費 Firebase API（無需金鑰）
抓取 Top Stories 並以 AI 相關關鍵字過濾
"""

import asyncio
from datetime import datetime, timezone
from loguru import logger
import httpx

from collectors.base import BaseCollector, NewsItem

# HackerNews Firebase API 基礎 URL（完全免費，無需認證）
HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"

# 用於過濾 AI 相關內容的關鍵字
AI_KEYWORDS = {
    "ai", "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "machine learning", "deep learning", "neural", "transformer",
    "openai", "anthropic", "hugging face", "diffusion", "stable diffusion",
    "chatgpt", "copilot", "embedding", "vector", "rag", "agent",
    "langchain", "pytorch", "tensorflow", "jax", "ollama", "localai",
    "mlops", "model", "inference", "finetune", "lora", "quantization",
    "benchmark", "reasoning", "multimodal",
}


class HackerNewsCollector(BaseCollector):
    """
    Hacker News 資料採集器
    使用 Firebase Realtime Database API 抓取文章
    """

    def __init__(self, top_n: int = 200):
        super().__init__(name="HackerNews")
        # top_n：從前幾名的 top stories 中過濾，越大覆蓋越廣但越慢
        self.top_n = top_n

    async def collect(self) -> list[NewsItem]:
        """
        採集 HackerNews Top Stories 中的 AI 相關文章
        """
        async with httpx.AsyncClient(timeout=30) as client:
            # 取得最新 Top Stories ID 列表
            top_ids = await self._fetch_top_ids(client)
            if not top_ids:
                return []

            # 只取前 top_n 筆，避免請求過多
            target_ids = top_ids[:self.top_n]

            # 並發抓取文章詳情（每批 20 個，避免過度並發）
            items = []
            batch_size = 20
            for i in range(0, len(target_ids), batch_size):
                batch = target_ids[i:i + batch_size]
                tasks = [self._fetch_item(client, story_id) for story_id in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, NewsItem):
                        items.append(result)

            logger.debug(f"[HackerNews] 從 {len(target_ids)} 筆中篩選出 {len(items)} 筆 AI 相關文章")
            return items

    async def _fetch_top_ids(self, client: httpx.AsyncClient) -> list[int]:
        """取得 Top Stories 的 ID 列表"""
        try:
            resp = await client.get(f"{HN_BASE_URL}/topstories.json")
            resp.raise_for_status()
            return resp.json() or []
        except Exception as e:
            logger.error(f"[HackerNews] 取得 Top Stories ID 失敗：{e}")
            return []

    async def _fetch_item(self, client: httpx.AsyncClient, item_id: int) -> NewsItem | None:
        """
        取得單篇文章詳情並判斷是否為 AI 相關
        非 AI 相關的文章直接返回 None 跳過
        """
        try:
            resp = await client.get(f"{HN_BASE_URL}/item/{item_id}.json")
            resp.raise_for_status()
            data = resp.json()

            if not data:
                return None

            # 只處理 story 類型（排除 job、poll 等）
            if data.get("type") != "story":
                return None

            title = data.get("title", "")
            url = data.get("url", f"https://news.ycombinator.com/item?id={item_id}")
            text = data.get("text", "")  # Ask HN / Show HN 的內文

            # 以關鍵字判斷是否 AI 相關（標題或內文）
            combined = (title + " " + text).lower()
            if not self._is_ai_related(combined):
                return None

            published_at = datetime.fromtimestamp(
                data.get("time", 0), tz=timezone.utc
            ).isoformat()

            score = data.get("score", 0)
            comments = data.get("descendants", 0)

            return NewsItem(
                source="hackernews",
                title=title,
                content=text[:1000] if text else "",
                url=url,
                author=data.get("by", "unknown"),
                published_at=published_at,
                tags=["hackernews", f"score:{score}", f"comments:{comments}"],
            )
        except Exception as e:
            logger.debug(f"[HackerNews] 取得 item {item_id} 失敗：{e}")
            return None

    def _is_ai_related(self, text: str) -> bool:
        """判斷文字是否包含 AI 相關關鍵字"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in AI_KEYWORDS)
