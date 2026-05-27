"""
arXiv Collector
使用官方免費 arxiv Python library 抓取最新 AI/ML 論文
分類：cs.AI, cs.CL（自然語言處理）, cs.LG（機器學習）
"""

import asyncio
from datetime import datetime, timezone, timedelta
from functools import partial
from loguru import logger
import arxiv

from collectors.base import BaseCollector, NewsItem

# 要監控的 arXiv 分類
ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]

# 每個分類抓取的最大論文數
MAX_RESULTS_PER_CATEGORY = 20


class ArxivCollector(BaseCollector):
    """
    arXiv 論文採集器
    專注於 AI/ML 相關領域的最新論文（過去 24 小時）
    """

    def __init__(self):
        super().__init__(name="arXiv")
        # arxiv library 是同步的，使用 loop.run_in_executor 避免 blocking
        self.client = arxiv.Client(
            page_size=MAX_RESULTS_PER_CATEGORY,
            delay_seconds=3,  # 每次請求間隔，避免被限速
            num_retries=3,
        )

    async def collect(self) -> list[NewsItem]:
        """
        並發採集各分類的最新論文
        """
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(None, partial(self._collect_category, category))
            for category in ARXIV_CATEGORIES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 合併結果並去重（同一論文可能在多個分類）
        seen_arxiv_ids = set()
        items = []
        for category, result in zip(ARXIV_CATEGORIES, results):
            if isinstance(result, Exception):
                logger.error(f"[arXiv] {category} 採集失敗：{result}")
            else:
                for item in result:
                    arxiv_id = item.url.split("/")[-1]
                    if arxiv_id not in seen_arxiv_ids:
                        seen_arxiv_ids.add(arxiv_id)
                        items.append(item)

        logger.debug(f"[arXiv] 共採集 {len(items)} 篇論文（去重後）")
        return items

    def _collect_category(self, category: str) -> list[NewsItem]:
        """
        採集指定 arXiv 分類的最新論文（同步方法）
        使用 sortBy=SubmittedDate 確保取得最新論文
        """
        items = []
        try:
            search = arxiv.Search(
                query=f"cat:{category}",
                max_results=MAX_RESULTS_PER_CATEGORY,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )

            for paper in self.client.results(search):
                # 只取最近 48 小時內發布的論文
                if not self._is_recent(paper.published):
                    continue

                item = NewsItem(
                    source="arxiv",
                    title=paper.title,
                    content=paper.summary[:1500],  # 摘要通常足夠，限制長度
                    url=paper.entry_id,
                    author=", ".join([a.name for a in paper.authors[:5]]),  # 最多列 5 位作者
                    published_at=paper.published.isoformat(),
                    tags=[
                        "arxiv",
                        category,
                        *[cat.term for cat in paper.categories[:3]],
                    ],
                )
                items.append(item)

            logger.debug(f"[arXiv] {category} 採集 {len(items)} 篇近 48 小時論文")
        except Exception as e:
            logger.error(f"[arXiv] {category} 採集錯誤：{e}")
            raise

        return items

    def _is_recent(self, published_dt: datetime, hours: int = 48) -> bool:
        """
        判斷論文是否在指定小時數內發布
        預設 48 小時，確保不遺漏週末發布的論文
        """
        if published_dt.tzinfo is None:
            # 若無時區資訊，假設為 UTC
            published_dt = published_dt.replace(tzinfo=timezone.utc)

        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        return published_dt >= cutoff
