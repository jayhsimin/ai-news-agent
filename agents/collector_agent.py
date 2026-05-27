"""
Collector Agent
負責協調所有資料來源的採集工作
並發執行所有 collector，聚合結果後傳給下游 Agent
"""

import asyncio
from loguru import logger

from agents.base import BaseAgent, AgentResult, AgentStatus
from collectors import (
    RedditCollector,
    HackerNewsCollector,
    GitHubCollector,
    ArxivCollector,
    NewsItem,
)
from config import settings


class CollectorAgent(BaseAgent):
    """
    資料採集 Agent
    並發執行所有 collector，回傳合併後的 NewsItem 清單
    任何單一 collector 失敗不影響其他 collector
    """

    def __init__(self):
        super().__init__(name="CollectorAgent")
        # 初始化所有 collector
        self.collectors = []

        # GitHub 和 HackerNews 無需 API Key，永遠加入
        self.collectors.append(HackerNewsCollector())
        self.collectors.append(GitHubCollector())
        self.collectors.append(ArxivCollector())

        # Reddit 需要 API Key，僅在設定完整時加入
        if settings.is_reddit_configured:
            self.collectors.append(RedditCollector())
        else:
            logger.warning(
                "[CollectorAgent] Reddit API 未設定，跳過 Reddit 採集。\n"
                "請在 .env 填入 REDDIT_CLIENT_ID 和 REDDIT_CLIENT_SECRET"
            )

    async def run(self, input_data=None) -> AgentResult:
        """
        並發執行所有 collector，合併結果
        """
        logger.info(f"[CollectorAgent] 開始採集，共 {len(self.collectors)} 個來源")

        # 並發執行所有 collector（各自有 safe_collect 保護）
        tasks = [collector.safe_collect() for collector in self.collectors]
        results = await asyncio.gather(*tasks)

        # 合併所有採集結果
        all_items: list[NewsItem] = []
        stats = {}
        for collector, items in zip(self.collectors, results):
            count = len(items)
            stats[collector.name] = count
            all_items.extend(items)
            logger.info(f"  ↳ {collector.name}: {count} 筆")

        logger.info(f"[CollectorAgent] 採集完成，總計 {len(all_items)} 筆")

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            data=all_items,
            metadata={
                "total_collected": len(all_items),
                "source_stats": stats,
            },
        )
