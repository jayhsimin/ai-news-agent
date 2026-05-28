"""
Processors 模組
使用延遲 import 避免在 GHA 精簡環境中載入 torch / numpy 等重量級套件
"""


def __getattr__(name):
    if name == "Embedder":
        from processors.embedder import Embedder
        return Embedder
    if name == "Deduplicator":
        from processors.deduplicator import Deduplicator
        return Deduplicator
    if name == "Summarizer":
        from processors.summarizer import Summarizer
        return Summarizer
    if name == "Classifier":
        from processors.classifier import Classifier
        return Classifier
    raise AttributeError(f"module 'processors' has no attribute {name!r}")


__all__ = ["Embedder", "Deduplicator", "Summarizer", "Classifier"]
