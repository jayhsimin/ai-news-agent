#!/usr/bin/env python3
"""
GitHub Actions Pipeline
獨立執行腳本：採集 → 去重 → Groq 分析 → Telegram 推播
不依賴 Celery / Redis / Qdrant / Ollama / Docker
所有設定由 GitHub Actions Secrets 以環境變數傳入
"""

import asyncio
import os
import sys
from datetime import datetime
from loguru import logger

# 精簡 log 格式，適合 GitHub Actions 輸出
logger.remove()
logger.add(sys.stdout, format="{time:HH:mm:ss} | {level:<7} | {message}", level="INFO")


async def main() -> None:
    # ── 必要環境變數驗證 ────────────────────────────────────
    required_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GROQ_API_KEY"]
    missing = [k for k in required_vars if not os.environ.get(k)]
    if missing:
        logger.error(f"缺少必要環境變數：{missing}")
        logger.error("請在 GitHub repo → Settings → Secrets and variables → Actions 中設定")
        sys.exit(1)

    run_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    logger.info(f"{'='*50}")
    logger.info(f"AI News Agent Pipeline 開始  [{run_time}]")
    logger.info(f"{'='*50}")

    # ── 階段 1：採集 ────────────────────────────────────────
    logger.info("【1/4】採集資料來源...")

    from collectors import HackerNewsCollector, GitHubCollector, ArxivCollector, RSSFeedCollector
    from config import settings

    collectors = [
        HackerNewsCollector(),
        GitHubCollector(),
        ArxivCollector(),
        RSSFeedCollector(),
    ]

    # Reddit 為選填，有設定才啟用
    if settings.is_reddit_configured:
        from collectors.reddit import RedditCollector
        collectors.append(RedditCollector())
        logger.info("  Reddit 已啟用")

    tasks = [c.safe_collect() for c in collectors]
    results = await asyncio.gather(*tasks)

    all_items = []
    for collector, items in zip(collectors, results):
        logger.info(f"  {collector.name:<15} {len(items):>3} 筆")
        all_items.extend(items)

    logger.info(f"  → 採集總計：{len(all_items)} 筆")

    if not all_items:
        logger.warning("所有來源採集結果為空，pipeline 結束")
        return

    # ── 階段 2：去重 ────────────────────────────────────────
    logger.info("【2/4】URL 去重...")

    from processors.json_deduplicator import JsonDeduplicator

    cache_file = os.environ.get("SEEN_URLS_PATH", "seen_urls.json")
    dedup = JsonDeduplicator(cache_path=cache_file)

    new_items = [item for item in all_items if not dedup.is_duplicate(item)]
    skipped = len(all_items) - len(new_items)
    logger.info(f"  → 新文章：{len(new_items)} 筆（過濾重複：{skipped} 筆）")

    if not new_items:
        logger.info("無新文章，儲存快取後結束")
        dedup.save()
        return

    # ── 階段 3：Groq 分析（摘要 + 分類 + 評分）──────────────
    logger.info(f"【3/4】Groq 分析 {len(new_items)} 篇文章...")

    from processors.groq_analyzer import GroqAnalyzer

    analyzer = GroqAnalyzer(api_key=os.environ["GROQ_API_KEY"])
    analyzed_items = []

    for i, item in enumerate(new_items):
        try:
            result = await analyzer.analyze(item)
            item.summary = result["summary"]
            item.category = result["category"]
            item.relevance_score = result["relevance_score"]
        except Exception as e:
            logger.error(f"  [{i+1}] 分析失敗（{item.title[:40]}）：{e}")
            item.summary = item.title
            item.category = "其他"
            item.relevance_score = 5.0

        analyzed_items.append(item)
        dedup.mark_seen(item)  # 無論分析成否，都標記已見

        if (i + 1) % 10 == 0:
            logger.info(f"  進度：{i+1}/{len(new_items)}")

        # Groq 免費方案 30 req/min → 每篇間隔 2 秒，確保不超速
        if i < len(new_items) - 1:
            await asyncio.sleep(2)

    # 儲存去重快取（無論後續推播成功與否都要儲存）
    dedup.save()

    # ── 階段 4：推播到 Telegram ─────────────────────────────
    logger.info("【4/4】Telegram 推播...")

    min_score = float(os.environ.get("MIN_RELEVANCE_SCORE", settings.MIN_RELEVANCE_SCORE))

    push_candidates = [
        item for item in analyzed_items
        if (item.relevance_score or 0) >= min_score
    ]
    push_candidates.sort(key=lambda x: x.relevance_score or 0, reverse=True)
    to_push = push_candidates[:10]  # 每次最多 10 篇，避免洗版

    logger.info(f"  達標（>= {min_score}）：{len(push_candidates)} 篇，本次推播：{len(to_push)} 篇")

    if not to_push:
        logger.info("  無符合門檻的文章，本次不推播")
        logger.info(f"{'='*50}")
        logger.info("Pipeline 完成：推播 0 篇")
        return

    from notifiers.telegram import TelegramNotifier

    notifier = TelegramNotifier()
    pushed = 0

    for i, item in enumerate(to_push):
        try:
            success = await notifier.send(item)
            if success:
                pushed += 1
                logger.info(f"  [{i+1}/{len(to_push)}] ✓ {item.title[:55]}")
        except Exception as e:
            logger.error(f"  [{i+1}/{len(to_push)}] ✗ 推播失敗：{e}")

        # Telegram rate limit：30 msg/sec per bot
        if i < len(to_push) - 1:
            await asyncio.sleep(1.5)

    logger.info(f"{'='*50}")
    logger.info(f"Pipeline 完成：採集 {len(all_items)} → 新增 {len(new_items)} → 推播 {pushed} 篇")


if __name__ == "__main__":
    asyncio.run(main())
