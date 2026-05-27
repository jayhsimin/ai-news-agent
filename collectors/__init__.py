"""
Collectors 模組
匯出所有資料來源採集器
"""

from collectors.base import BaseCollector, NewsItem
from collectors.reddit import RedditCollector
from collectors.hackernews import HackerNewsCollector
from collectors.github import GitHubCollector
from collectors.arxiv_collector import ArxivCollector

__all__ = [
    "BaseCollector",
    "NewsItem",
    "RedditCollector",
    "HackerNewsCollector",
    "GitHubCollector",
    "ArxivCollector",
]
