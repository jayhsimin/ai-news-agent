"""
通用工具函數
"""

import hashlib
from datetime import datetime, timezone


def generate_id(text: str) -> str:
    """根據文字生成 MD5 hash ID"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def truncate(text: str, max_length: int = 200) -> str:
    """截斷過長文字並加入省略號"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def utcnow_iso() -> str:
    """回傳當前 UTC 時間的 ISO 8601 字串"""
    return datetime.now(tz=timezone.utc).isoformat()


def safe_float(value, default: float = 0.0) -> float:
    """安全地將任意值轉換為 float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
