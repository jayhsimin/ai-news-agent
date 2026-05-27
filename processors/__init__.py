"""
Processors 模組
匯出所有文章處理元件
"""

from processors.embedder import Embedder
from processors.deduplicator import Deduplicator
from processors.summarizer import Summarizer
from processors.classifier import Classifier

__all__ = [
    "Embedder",
    "Deduplicator",
    "Summarizer",
    "Classifier",
]
