"""
Analyzer Agent
負責對每篇文章執行完整的分析 pipeline：
embed → deduplicate → summarize → classify → score
"""

import asyncio
from loguru import logger

from agents.base import BaseAgent, AgentResult, AgentStatus
from collectors.base import NewsItem
from processors.embedder import Embedder
from processors.deduplicator import Deduplicator
from processors.summarizer import Summarizer
from processors.classifier import Classifier


class AnalyzerAgent(BaseAgent):
    """
    分析 Agent
    接收 CollectorAgent 的輸出，對每篇文章執行完整分析

    分析流程：
    1. Embedding（向量化）
    2. Deduplication（去重）
    3. Summarization（摘要）
    4. Classification + Scoring（分類 + 評分）

    只有通過去重且評分達標的文章才會傳給 PublisherAgent
    """

    def __init__(self):
        super().__init__(name="AnalyzerAgent")
        self.embedder = Embedder()
        self.deduplicator = Deduplicator()
        self.summarizer = Summarizer()
        self.classifier = Classifier()

    async def run(self, input_data: list[NewsItem] = None) -> AgentResult:
        """
        對輸入的文章清單逐一執行分析 pipeline
        """
        if not input_data:
            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.SKIPPED,
                data=[],
                metadata={"reason": "無輸入資料"},
            )

        logger.info(f"[AnalyzerAgent] 開始分析 {len(input_data)} 篇文章")

        analyzed_items = []
        stats = {
            "total": len(input_data),
            "duplicates": 0,
            "analyzed": 0,
            "push_worthy": 0,
        }

        for i, item in enumerate(input_data):
            try:
                result = await self._analyze_single(item)
                if result is not None:
                    analyzed_items.append(result)
                    stats["analyzed"] += 1
                    if result.relevance_score and result.relevance_score >= 6.0:
                        stats["push_worthy"] += 1
                else:
                    stats["duplicates"] += 1

                # 每 10 篇輸出一次進度
                if (i + 1) % 10 == 0:
                    logger.info(f"[AnalyzerAgent] 進度：{i+1}/{len(input_data)}")

            except Exception as e:
                logger.error(f"[AnalyzerAgent] 分析第 {i+1} 篇失敗：{e}")

        logger.info(
            f"[AnalyzerAgent] 分析完成 "
            f"總計:{stats['total']} 去重:{stats['duplicates']} "
            f"分析:{stats['analyzed']} 值得推播:{stats['push_worthy']}"
        )

        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            data=analyzed_items,
            metadata=stats,
        )

    async def _analyze_single(self, item: NewsItem) -> NewsItem | None:
        """
        對單篇文章執行完整分析流程
        回傳 None 表示文章為重複內容，應跳過
        """
        # ── 步驟 1：向量化 ──
        full_text = item.get_full_text()
        embedding = self.embedder.embed(full_text)

        # ── 步驟 2：去重 ──
        if self.deduplicator.is_duplicate(item, embedding):
            item.is_duplicate = True
            return None  # 重複，跳過後續處理

        # ── 步驟 3：摘要（LLM）──
        # 使用 asyncio.gather 同時執行摘要，提升效率
        item.summary = await self.summarizer.summarize(item)

        # ── 步驟 4：分類 + 評分（LLM）──
        analysis = await self.classifier.analyze(item)
        item.category = analysis["category"]
        item.relevance_score = analysis["relevance_score"]

        # ── 步驟 5：存入 Qdrant（用於後續去重）──
        vector_id = self.deduplicator.save_item(item, embedding)
        item.embedding_id = vector_id

        return item
