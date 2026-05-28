"""
Groq LLM 分析器
使用 Groq 免費 API 同時完成摘要 + 分類 + 評分（單次呼叫）
免費方案：14,400 req/day，30 req/min（llama-3.1-8b-instant）
"""

import json
import os
import asyncio
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
import httpx

from collectors.base import NewsItem

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# 預設模型：快速且免費額度高（14,400 req/day）
# 可透過環境變數 GROQ_MODEL 覆蓋，例如改用 llama-3.3-70b-versatile
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

AI_CATEGORIES = [
    "模型發布", "研究論文", "工具與框架", "教學與資源",
    "產業動態", "基準測試", "安全與倫理", "硬體與基礎設施", "其他",
]

_ANALYZE_PROMPT = """你是一位 AI/科技情報分析師。請分析以下文章，用繁體中文完成三項任務，以 JSON 格式回傳。

標題：{title}
來源：{source}
內容：{content}

請回傳以下 JSON（只輸出 JSON，不含任何其他文字或 markdown）：
{{
  "summary": "2~3 句繁體中文摘要，說明文章核心技術內容",
  "category": "從以下選一個：{categories}",
  "relevance_score": 7,
  "reason": "一句話說明評分原因"
}}

評分標準（relevance_score 0~10）：
- 0~3：不具 AI 產業價值
- 4~5：一般 AI 資訊
- 6~7：重要商用 AI 新聞，值得關注
- 8~9：對企業或市場有明顯影響
- 10：改變產業生態的重大事件

JSON："""


class GroqAnalyzer:
    """
    Groq 雲端 LLM 分析器
    單次 API 呼叫完成摘要 + 分類 + 評分，節省 API 配額
    Rate limit 觸發時最多重試 3 次（共嘗試 4 次），並記錄觸發次數供外部通知使用
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY 未設定，請至 https://console.groq.com 申請免費 API Key")
        self.model = os.environ.get("GROQ_MODEL", DEFAULT_GROQ_MODEL)
        self._categories_str = "、".join(AI_CATEGORIES)
        # 記錄本次執行中 rate limit 觸發次數，供 pipeline 決定是否發 Telegram 通知
        self.rate_limit_count: int = 0

    @retry(
        stop=stop_after_attempt(4),   # 初次 + 最多重試 3 次
        wait=wait_exponential(multiplier=1, min=3, max=20),
    )
    async def analyze(self, item: NewsItem) -> dict:
        """
        呼叫 Groq API 分析單篇文章
        回傳：summary, category, relevance_score, reason
        """
        content = item.content[:600] if item.content else "（無內文）"
        prompt = _ANALYZE_PROMPT.format(
            title=item.title,
            source=item.source,
            content=content,
            categories=self._categories_str,
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    GROQ_API_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 300,
                    },
                )

                if resp.status_code == 429:
                    self.rate_limit_count += 1
                    logger.warning(
                        f"[Groq] Rate limit 觸發（第 {self.rate_limit_count} 次），等待 15 秒後重試"
                    )
                    await asyncio.sleep(15)
                    raise httpx.HTTPStatusError("429", request=resp.request, response=resp)

                resp.raise_for_status()
                raw = resp.json()["choices"][0]["message"]["content"].strip()
                result = self._parse(raw, item)
                logger.debug(
                    f"[Groq] {item.title[:40]} → "
                    f"{result['category']} / {result['relevance_score']}"
                )
                return result

        except httpx.HTTPStatusError as e:
            if "429" in str(e):
                raise  # 讓 retry 機制處理
            logger.error(f"[Groq] HTTP 錯誤：{e}")
            return self._fallback(item)
        except Exception as e:
            logger.error(f"[Groq] 分析失敗：{e}")
            return self._fallback(item)

    def _parse(self, raw: str, item: NewsItem) -> dict:
        """解析 LLM 回傳的 JSON，處理常見格式問題"""
        # 清理 markdown code block
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.lower().startswith("json"):
                raw = raw[4:]
        raw = raw.strip().strip("`").strip()

        try:
            data = json.loads(raw)
            return {
                "summary": str(data.get("summary", item.title)),
                "category": str(data.get("category", "其他")),
                "relevance_score": float(data.get("relevance_score", 5)),
                "reason": str(data.get("reason", "")),
            }
        except json.JSONDecodeError:
            logger.warning(f"[Groq] JSON 解析失敗，原始：{raw[:100]}")
            return self._fallback(item)

    def _fallback(self, item: NewsItem) -> dict:
        """API 不可用時的關鍵字降級方案"""
        combined = (item.title + " " + (item.content or "")).lower()
        if any(k in combined for k in ["arxiv", "paper", "research", "we propose"]):
            cat = "研究論文"
        elif any(k in combined for k in ["release", "launch", "announce", "v1.", "v2."]):
            cat = "模型發布"
        elif any(k in combined for k in ["github", "library", "framework", "tool"]):
            cat = "工具與框架"
        else:
            cat = "其他"
        return {
            "summary": item.title,
            "category": cat,
            "relevance_score": 5.0,
            "reason": "Groq API 不可用，使用關鍵字降級",
        }
