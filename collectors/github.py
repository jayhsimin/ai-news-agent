"""
GitHub Trending Collector
爬取 GitHub Trending 頁面，抓取 AI/ML 相關的熱門 Repository
使用 BeautifulSoup 解析 HTML，完全免費，無需 API Key
"""

import asyncio
from datetime import datetime, timezone
from loguru import logger
import httpx
from bs4 import BeautifulSoup

from collectors.base import BaseCollector, NewsItem

# GitHub Trending 頁面 URL
GITHUB_TRENDING_URLS = [
    "https://github.com/trending?since=daily",
    "https://github.com/trending/python?since=daily",
]

# AI/ML 相關關鍵字，用於過濾 repository
AI_KEYWORDS = {
    "ai", "llm", "gpt", "claude", "llama", "mistral", "gemini",
    "machine-learning", "deep-learning", "neural-network", "transformer",
    "diffusion", "stable-diffusion", "huggingface", "pytorch", "tensorflow",
    "rag", "vector", "embedding", "agent", "chatbot", "nlp", "cv",
    "langchain", "openai", "anthropic", "ollama", "inference", "finetune",
    "lora", "quantization", "mlops", "benchmark", "multimodal", "vision",
}


class GitHubCollector(BaseCollector):
    """
    GitHub Trending 資料採集器
    解析 GitHub 趨勢頁面取得每日熱門 AI 相關 Repository
    """

    def __init__(self):
        super().__init__(name="GitHub")
        # 模擬瀏覽器 User-Agent，避免被 GitHub 封鎖
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    async def collect(self) -> list[NewsItem]:
        """
        採集 GitHub Trending 中的 AI 相關 Repository
        """
        async with httpx.AsyncClient(timeout=30, headers=self.headers) as client:
            tasks = [self._scrape_trending(client, url) for url in GITHUB_TRENDING_URLS]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合併結果並去重（同一 repo 可能出現在多個 trending 頁面）
        seen_urls = set()
        items = []
        for result in results:
            if isinstance(result, list):
                for item in result:
                    if item.url not in seen_urls:
                        seen_urls.add(item.url)
                        items.append(item)
            elif isinstance(result, Exception):
                logger.error(f"[GitHub] 爬蟲失敗：{result}")

        logger.debug(f"[GitHub] 共採集 {len(items)} 筆 AI 相關 Repository")
        return items

    async def _scrape_trending(self, client: httpx.AsyncClient, url: str) -> list[NewsItem]:
        """
        爬取指定 GitHub Trending URL
        """
        items = []
        try:
            resp = await client.get(url)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")
            # GitHub Trending 的 repo 列表
            repo_articles = soup.find_all("article", class_="Box-row")

            for article in repo_articles:
                item = self._parse_repo_article(article)
                if item and self._is_ai_related(item):
                    items.append(item)

        except httpx.HTTPStatusError as e:
            logger.error(f"[GitHub] HTTP 錯誤 {e.response.status_code}：{url}")
            raise
        except Exception as e:
            logger.error(f"[GitHub] 爬取失敗 {url}：{e}")
            raise

        return items

    def _parse_repo_article(self, article) -> NewsItem | None:
        """
        解析單個 Repository 的 HTML 元素
        """
        try:
            # 取得 repo 名稱（格式：owner/repo）
            h2 = article.find("h2")
            if not h2:
                return None

            # 清理空白與換行
            repo_path = h2.get_text(separator="/", strip=True)
            # 取最後兩個 / 分隔的部分（owner + repo）
            parts = [p.strip() for p in repo_path.split("/") if p.strip()]
            if len(parts) < 2:
                return None
            owner, repo_name = parts[-2], parts[-1]

            repo_url = f"https://github.com/{owner}/{repo_name}"
            title = f"{owner}/{repo_name}"

            # 取得描述
            desc_elem = article.find("p", class_="col-9")
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            # 取得程式語言
            lang_elem = article.find("span", itemprop="programmingLanguage")
            language = lang_elem.get_text(strip=True) if lang_elem else ""

            # 取得今日 stars
            stars_today = ""
            stars_elem = article.find("span", class_="d-inline-block float-sm-right")
            if stars_elem:
                stars_today = stars_elem.get_text(strip=True)

            return NewsItem(
                source="github",
                title=title,
                content=description,
                url=repo_url,
                author=owner,
                published_at=datetime.now(tz=timezone.utc).isoformat(),
                tags=[
                    "github",
                    "trending",
                    f"lang:{language}" if language else "lang:unknown",
                    stars_today,
                ],
            )
        except Exception as e:
            logger.debug(f"[GitHub] 解析 repo 失敗：{e}")
            return None

    def _is_ai_related(self, item: NewsItem) -> bool:
        """
        判斷 Repository 是否與 AI/ML 相關
        檢查標題、描述、和標籤
        """
        combined = (item.title + " " + item.content).lower()
        # 以 - 和 _ 替換為空格，讓關鍵字匹配更準確
        combined = combined.replace("-", " ").replace("_", " ")
        return any(keyword in combined for keyword in AI_KEYWORDS)
