"""
RSS/Atom Feed Collector
抓取 AI 官方實驗室部落格與技術媒體的 RSS/Atom feed
無需 API Key，所有來源均為免費公開 feed
"""

import asyncio
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from loguru import logger
import httpx
import feedparser

from collectors.base import BaseCollector, NewsItem

# 高品質 AI 資訊來源 RSS feeds
DEFAULT_AI_FEEDS = [
    {
        "name": "huggingface_blog",
        "display": "Hugging Face Blog",
        "url": "https://huggingface.co/blog/feed.xml",
        "tags": ["huggingface", "official", "models"],
        "filter": False,
    },
    {
        "name": "google_deepmind",
        "display": "Google DeepMind Blog",
        "url": "https://deepmind.google/blog/rss/",
        "tags": ["deepmind", "google", "official", "research"],
        "filter": False,
    },
    {
        "name": "google_ai_blog",
        "display": "Google AI Blog",
        "url": "https://blog.google/technology/ai/rss/",
        "tags": ["google", "official", "applications"],
        "filter": False,
    },
    {
        "name": "nvidia_developer",
        "display": "NVIDIA Developer Blog",
        "url": "https://developer.nvidia.com/blog/feed/",
        "tags": ["nvidia", "official", "hardware", "models"],
        "filter": True,   # nvidia blog covers non-AI topics too
    },
    {
        "name": "openai_blog",
        "display": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "tags": ["openai", "official", "models"],
        "filter": False,
    },
    {
        "name": "anthropic_news",
        "display": "Anthropic News",
        "url": "https://www.anthropic.com/rss.xml",
        "tags": ["anthropic", "official", "safety", "models"],
        "filter": False,
    },
    {
        "name": "mit_tech_review",
        "display": "MIT Technology Review",
        "url": "https://www.technologyreview.com/feed/",
        "tags": ["mit", "research", "innovation", "frontier"],
        "filter": True,
    },
    {
        "name": "the_batch",
        "display": "The Batch (DeepLearning.AI)",
        "url": "https://www.deeplearning.ai/the-batch/feed/",
        "tags": ["deeplearning-ai", "newsletter", "digest"],
        "filter": False,
    },
    {
        "name": "meta_ai_blog",
        "display": "Meta AI Blog",
        "url": "https://ai.meta.com/blog/feed/",
        "tags": ["meta", "official", "models", "research"],
        "filter": False,
    },
    {
        "name": "towards_data_science",
        "display": "Towards Data Science",
        "url": "https://towardsdatascience.com/feed",
        "tags": ["medium", "tds", "developer", "tutorials"],
        "filter": True,   # Medium 通用平台，需 AI 關鍵字過濾
    },
    {
        "name": "latent_space",
        "display": "Latent Space",
        "url": "https://www.latent.space/feed",
        "tags": ["latent-space", "newsletter", "developer", "frontier"],
        "filter": False,
    },
]

# 關鍵字過濾集合（用於非純 AI 媒體）
_AI_KEYWORDS = {
    "ai", "llm", "gpt", "claude", "gemini", "llama", "mistral",
    "machine learning", "deep learning", "neural", "transformer",
    "openai", "anthropic", "hugging face", "diffusion", "model",
    "agent", "rag", "benchmark", "reasoning", "multimodal",
    "embedding", "inference", "fine-tun", "quantiz", "moe",
    "mixture of experts", "language model", "foundation model",
    "robotics", "autonomous", "generative",
}


class _HTMLStripper(HTMLParser):
    """將 HTML 轉純文字"""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(text: str) -> str:
    s = _HTMLStripper()
    s.feed(text)
    return s.get_text()


def _parse_entry_date(entry) -> datetime:
    """嘗試從 feed entry 解析發布時間，fallback 為當前 UTC"""
    for attr in ("published", "updated", "created"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                pass

    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass

    return datetime.now(tz=timezone.utc)


class RSSFeedCollector(BaseCollector):
    """
    RSS/Atom Feed 採集器
    支援多個官方 AI 實驗室部落格與技術媒體，預設覆蓋：
      Hugging Face, Google DeepMind, Google AI, NVIDIA, OpenAI,
      Anthropic, MIT Technology Review, The Batch (DeepLearning.AI)
    """

    def __init__(
        self,
        feeds: list[dict] | None = None,
        hours: int = 48,
        max_items_per_feed: int = 10,
    ):
        super().__init__(name="RSSFeeds")
        self.feeds = feeds if feeds is not None else DEFAULT_AI_FEEDS
        self.hours = hours
        self.max_items_per_feed = max_items_per_feed

    async def collect(self) -> list[NewsItem]:
        """並發採集所有 RSS feed"""
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "ai-news-agent/1.0 (RSS reader; +https://github.com)"},
        ) as client:
            tasks = [self._collect_feed(client, feed) for feed in self.feeds]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[NewsItem] = []
        for feed, result in zip(self.feeds, results):
            if isinstance(result, Exception):
                logger.error(f"[RSSFeeds] {feed['display']} 採集失敗：{result}")
            else:
                items.extend(result)
                logger.debug(f"[RSSFeeds] {feed['display']}: {len(result)} 筆")

        logger.debug(f"[RSSFeeds] 總計 {len(items)} 筆（{len(self.feeds)} 個 feed）")
        return items

    async def _collect_feed(
        self, client: httpx.AsyncClient, feed: dict
    ) -> list[NewsItem]:
        resp = await client.get(feed["url"])
        resp.raise_for_status()

        # feedparser 是同步 CPU-bound，移到 executor 避免 blocking event loop
        loop = asyncio.get_event_loop()
        parsed = await loop.run_in_executor(None, feedparser.parse, resp.text)

        items: list[NewsItem] = []
        for entry in parsed.entries[: self.max_items_per_feed]:
            item = self._parse_entry(entry, feed)
            if item:
                items.append(item)
        return items

    def _parse_entry(self, entry, feed: dict) -> NewsItem | None:
        title = getattr(entry, "title", "").strip()
        url = getattr(entry, "link", "").strip()
        if not title or not url:
            return None

        # 取摘要或全文，優先 content > summary
        raw_content = ""
        if hasattr(entry, "content") and entry.content:
            raw_content = entry.content[0].get("value", "")
        elif hasattr(entry, "summary"):
            raw_content = entry.summary or ""
        content = _strip_html(raw_content)[:2000]

        # 針對需要過濾的來源，確認含 AI 關鍵字
        if feed.get("filter"):
            combined = (title + " " + content).lower()
            if not any(kw in combined for kw in _AI_KEYWORDS):
                return None

        published_at = _parse_entry_date(entry)

        # 時間窗口過濾
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=self.hours)
        if published_at < cutoff:
            return None

        author = ""
        if hasattr(entry, "author"):
            author = entry.author or ""
        elif hasattr(entry, "authors") and entry.authors:
            author = entry.authors[0].get("name", "")

        return NewsItem(
            source=feed["name"],
            title=title,
            content=content,
            url=url,
            author=author or "unknown",
            published_at=published_at.isoformat(),
            tags=feed.get("tags", []) + ["rss"],
        )
