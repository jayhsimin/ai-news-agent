"""
Publisher Agent
負責最終的推播決策與執行
根據相關性分數決定是否推播，並控制推播頻率避免洗版
"""

import asyncio
from datetime import datetime
from loguru import logger

from agents.base import BaseAgent, AgentResult, AgentStatus
from collectors.base import NewsItem
from notifiers.telegram import TelegramNotifier
from config import settings


class PublisherAgent(BaseAgent):
    """
    推播 Agent
    接收 AnalyzerAgent 的輸出，決定哪些文章值得推播

    推播規則：
    1. relevance_score >= MIN_RELEVANCE_SCORE
    2. 同一次 pipeline 執行最多推播 10 篇（避免洗版）
    3. 優先推播分數最高的文章
    """

    # 每次 pipeline 執行最多推播篇數（避免一次性洗版）
    MAX_PUSH_PER_RUN = 10

    def __init__(self):
        super().__init__(name="PublisherAgent")
        self.notifier = TelegramNotifier()

    async def run(self, input_data: list[NewsItem] = None) -> AgentResult:
        """
        篩選值得推播的文章，依分數排序後逐一發送 Telegram 通知
        """
        if not input_data:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.SKIPPED,
                data=[],
                metadata={"reason": "無輸入資料"},
            )

        # ── 篩選值得推播的文章 ──
        push_candidates = [
            item for item in input_data
            if item.relevance_score is not None
            and item.relevance_score >= settings.MIN_RELEVANCE_SCORE
        ]

        # 按分數降序排列（最重要的先推）
        push_candidates.sort(key=lambda x: x.relevance_score or 0, reverse=True)

        # 限制最多推播篇數
        to_push = push_candidates[:self.MAX_PUSH_PER_RUN]

        logger.info(
            f"[PublisherAgent] 候選 {len(push_candidates)} 篇，"
            f"本次推播 {len(to_push)} 篇"
        )

        if not to_push:
            logger.info("[PublisherAgent] 無符合門檻的文章，本次不推播")
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.SUCCESS,
                data=[],
                metadata={
                    "total_analyzed": len(input_data),
                    "candidates": len(push_candidates),
                    "pushed": 0,
                },
            )

        # ── 逐一推播，加入間隔避免 Telegram rate limit ──
        pushed_items = []
        failed_count = 0

        for i, item in enumerate(to_push):
            try:
                success = await self.notifier.send(item)
                if success:
                    pushed_items.append(item)
                    logger.info(
                        f"[PublisherAgent] 推播 {i+1}/{len(to_push)}：{item.title[:50]}"
                    )
                else:
                    failed_count += 1

                # 每篇間隔 1.5 秒，避免 Telegram 限速（max 30 msg/sec per bot）
                if i < len(to_push) - 1:
                    await asyncio.sleep(1.5)

            except Exception as e:
                failed_count += 1
                logger.error(f"[PublisherAgent] 推播失敗：{e}")

        stats = {
            "total_analyzed": len(input_data),
            "candidates": len(push_candidates),
            "pushed": len(pushed_items),
            "failed": failed_count,
            "min_score_threshold": settings.MIN_RELEVANCE_SCORE,
        }

        logger.info(
            f"[PublisherAgent] 完成，成功推播 {len(pushed_items)} 篇，失敗 {failed_count} 篇"
        )

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            data=pushed_items,
            metadata=stats,
        )
