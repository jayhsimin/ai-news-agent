"""
分類器 + 相關性評分器
使用本地 Ollama LLM 執行兩個任務：
1. 將文章分類到預定義的 AI 資訊類別
2. 評估文章的重要性/相關性分數（0~10）
並決定是否值得推播
"""

import json
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from collectors.base import NewsItem
from config import settings

# 預定義的分類（LLM 必須從這些分類中選一個）
AI_CATEGORIES = [
    "模型發布",       # 新模型、新版本發布
    "研究論文",       # arXiv 論文、研究成果
    "工具與框架",     # 開源工具、框架、程式庫
    "教學與資源",     # 教程、指南、最佳實踐
    "產業動態",       # 公司新聞、融資、商業動態
    "基準測試",       # 效能比較、排行榜更新
    "安全與倫理",     # AI 安全、政策法規
    "硬體與基礎設施", # GPU、TPU、資料中心
    "其他",           # 不屬於以上分類
]

# 分析 Prompt（單一呼叫同時完成分類 + 評分，節省 LLM 呼叫次數）
ANALYZE_PROMPT_TEMPLATE = """你是一位 AI/科技情報分析師，專注於判斷「商用 AI 產業新聞」的價值。請分析以下文章，用 JSON 格式回答。

標題：{title}
來源：{source}
內容摘要：{summary}

請回傳以下 JSON 格式（只回傳 JSON，不要有任何其他文字）：
{{
  "category": "分類名稱（只能從以下選一個：{categories}）",
  "relevance_score": 7,
  "should_push": true,
  "reason": "一句話說明評分原因"
}}

請特別考慮：
- 是否為 AI 產業新聞、企業動態或商用應用相關
- 是否對商業讀者、企業決策者、科技公司或投資人具有參考價值
- 是否代表 AI 技術在商業應用、產品化、量產或市場競爭上的重要變化

評分標準（relevance_score）：
- 0~3：非商用或不具產業價值的資訊
- 4~5：一般 AI 資訊，對商業讀者價值有限
- 6~7：重要商用 AI 產業新聞，值得關注
- 8~9：非常重要的商用 AI 產業動態，對企業或市場有明顯影響
- 10：改變商業生態的重大 AI 事件

should_push：relevance_score >= {min_score} 時為 true

JSON："""


class Classifier:
    """
    AI 資訊分類器與相關性評分器
    使用 Ollama LLM 執行，完全本地免費
    """

    def __init__(self):
        self.api_url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.categories_str = "、".join(AI_CATEGORIES)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=False,
    )
    async def analyze(self, item: NewsItem) -> dict:
        """
        對文章進行分類與評分
        回傳 dict 包含：category, relevance_score, should_push, reason

        LLM 失敗時回傳預設值（不阻斷 pipeline）
        """
        summary = item.summary or item.title
        prompt = ANALYZE_PROMPT_TEMPLATE.format(
            title=item.title,
            source=item.source,
            summary=summary[:500],
            categories=self.categories_str,
            min_score=settings.MIN_RELEVANCE_SCORE,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self.api_url,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,   # 極低溫度，確保輸出穩定的 JSON
                            "num_predict": 300,
                        },
                    },
                )
                resp.raise_for_status()

                raw_response = resp.json().get("response", "").strip()
                result = self._parse_response(raw_response)
                logger.debug(
                    f"[分類] {item.title[:40]} → "
                    f"類別:{result['category']} 分數:{result['relevance_score']}"
                )
                return result

        except httpx.TimeoutException:
            logger.warning(f"[分類] LLM 逾時：{item.title[:50]}")
        except httpx.ConnectError:
            logger.error("[分類] 無法連接 Ollama")
        except Exception as e:
            logger.error(f"[分類] 分析失敗：{e}")

        # 降級處理：LLM 不可用時回傳基於關鍵字的粗略分類
        return self._fallback_classify(item)

    def _parse_response(self, raw: str) -> dict:
        """
        解析 LLM 回傳的 JSON 字串
        處理 LLM 可能輸出的 markdown code block 等格式問題
        """
        # 清理可能的 markdown code block 標記
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```")

        try:
            data = json.loads(raw)
            return {
                "category": data.get("category", "其他"),
                "relevance_score": float(data.get("relevance_score", 5)),
                "should_push": bool(data.get("should_push", False)),
                "reason": data.get("reason", ""),
            }
        except json.JSONDecodeError:
            logger.warning(f"[分類] JSON 解析失敗，原始回應：{raw[:200]}")
            return self._default_result()

    def _fallback_classify(self, item: NewsItem) -> dict:
        """
        LLM 不可用時的關鍵字分類降級方案
        確保 pipeline 不會因 LLM 問題完全停擺
        """
        title_lower = item.title.lower()
        content_lower = (item.content or "").lower()
        combined = title_lower + " " + content_lower

        # 簡單關鍵字規則
        if any(k in combined for k in ["arxiv", "paper", "research", "we propose"]):
            category = "研究論文"
        elif any(k in combined for k in ["release", "v1.", "v2.", "launch", "announce"]):
            category = "模型發布"
        elif any(k in combined for k in ["github", "library", "framework", "tool", "open source"]):
            category = "工具與框架"
        else:
            category = "其他"

        # 分數預設 5（中等），由人工或後續確認
        return {
            "category": category,
            "relevance_score": 5.0,
            "should_push": False,  # 降級模式預設不推播，避免低品質內容
            "reason": "LLM 不可用，使用關鍵字分類（降級模式）",
        }

    def _default_result(self) -> dict:
        """預設回傳值"""
        return {
            "category": "其他",
            "relevance_score": 5.0,
            "should_push": False,
            "reason": "分析失敗",
        }
