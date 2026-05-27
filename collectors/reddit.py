"""
Reddit Collector
使用官方免費 API（asyncpraw），抓取指定 subreddit 的熱門貼文
不需付費，每分鐘最多 100 次請求（已足夠）
"""

import asyncio
from datetime import datetime, timezone
from loguru import logger

from collectors.base import BaseCollector, NewsItem
from config import settings


class RedditCollector(BaseCollector):
    """
    Reddit 資料採集器
    監控 r/LocalLLaMA, r/MachineLearning, r/singularity, r/artificial
    """

    def __init__(self):
        super().__init__(name="Reddit")
        # 延遲初始化 asyncpraw，避免啟動時連線
        self._reddit = None

    def _get_reddit_client(self):
        """
        初始化 asyncpraw 客戶端
        使用 read_only 模式，不需要使用者登入
        """
        import asyncpraw

        if not settings.is_reddit_configured:
            raise ValueError(
                "Reddit API 未設定！請在 .env 填入 REDDIT_CLIENT_ID 與 REDDIT_CLIENT_SECRET\n"
                "申請地址：https://www.reddit.com/prefs/apps（選 script 類型）"
            )

        return asyncpraw.Reddit(
            client_id=settings.REDDIT_CLIENT_ID,
            client_secret=settings.REDDIT_CLIENT_SECRET,
            user_agent=settings.REDDIT_USER_AGENT,
        )

    async def collect(self) -> list[NewsItem]:
        """
        採集所有設定的 subreddit 貼文
        並發執行，加快採集速度
        """
        reddit = self._get_reddit_client()
        results = []

        try:
            # 並發採集所有 subreddit
            tasks = [
                self._collect_subreddit(reddit, subreddit)
                for subreddit in settings.reddit_subreddits_list
            ]
            collected = await asyncio.gather(*tasks, return_exceptions=True)

            for subreddit, items in zip(settings.reddit_subreddits_list, collected):
                if isinstance(items, Exception):
                    logger.error(f"[Reddit] r/{subreddit} 採集失敗：{items}")
                else:
                    results.extend(items)
        finally:
            # 確保關閉連線，避免 resource leak
            await reddit.close()

        return results

    async def _collect_subreddit(self, reddit, subreddit_name: str) -> list[NewsItem]:
        """
        採集單一 subreddit 的 hot/new 貼文
        """
        items = []
        try:
            subreddit = await reddit.subreddit(subreddit_name)
            # 抓取熱門貼文
            async for post in subreddit.hot(limit=settings.REDDIT_POST_LIMIT):
                # 過濾已刪除或無內容的貼文
                if post.is_self and not post.selftext:
                    continue
                if post.removed_by_category:
                    continue

                # 取得貼文內容（self post 有 selftext，link post 無）
                content = post.selftext if post.is_self else ""

                item = NewsItem(
                    source="reddit",
                    title=post.title,
                    content=content[:2000],  # 限制內容長度，避免過長
                    url=f"https://reddit.com{post.permalink}",
                    author=str(post.author) if post.author else "deleted",
                    published_at=datetime.fromtimestamp(
                        post.created_utc, tz=timezone.utc
                    ).isoformat(),
                    tags=[
                        f"r/{subreddit_name}",
                        "reddit",
                        post.link_flair_text or "",
                    ],
                )
                items.append(item)

            logger.debug(f"[Reddit] r/{subreddit_name} 採集 {len(items)} 筆")
        except Exception as e:
            logger.error(f"[Reddit] r/{subreddit_name} 錯誤：{e}")
            raise

        return items
