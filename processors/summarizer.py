"""
摘要生成器
使用本地 Ollama LLM 對文章內容生成繁體中文摘要
完全本地執行，不需要付費 API
"""

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from collectors.base import NewsItem
from config import settings

# 摘要 Prompt 模板（指示 LLM 用繁體中文，2~3 句話精簡摘要）
SUMMARIZE_PROMPT_TEMPLATE = """你是一位 AI/科技情報分析師。請用繁體中文，以 2~3 句話精簡摘要以下內容的重點。

標題：{title}
內容：{content}

要求：
- 使用繁體中文
- 只輸出摘要，不要有前言或說明
- 若內容不足，只用標題摘要也可以
- 2~3 句話，約 50~100 字

摘要："""


class Summarizer:
    """
    LLM 摘要生成器
    使用 Ollama 的 generate API，呼叫本地模型生成繁體中文摘要
    """

    def __init__(self):
        self.api_url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=False,
    )
    async def summarize(self, item: NewsItem) -> str:
        """
        生成文章摘要
        使用 retry 機制處理 Ollama 偶發性逾時

        回傳值：繁體中文摘要字串，若 LLM 不可用則回傳空字串
        """
        # 準備輸入文字（標題 + 內容，限制長度避免 token 過多）
        content = item.content[:800] if item.content else "（無內文）"

        prompt = SUMMARIZE_PROMPT_TEMPLATE.format(
            title=item.title,
            content=content,
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self.api_url,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,  # 不使用串流，等待完整回應
                        "options": {
                            "temperature": 0.3,   # 低溫度確保摘要穩定
                            "num_predict": 200,   # 限制輸出 token 數，摘要不需要太長
                        },
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                summary = result.get("response", "").strip()
                logger.debug(f"[摘要] {item.title[:40]}... → {summary[:60]}...")
                return summary

        except httpx.TimeoutException:
            logger.warning(f"[摘要] LLM 逾時：{item.title[:50]}")
            # 逾時時回傳原始標題作為摘要（降級處理）
            return f"（摘要生成逾時）{item.title}"
        except httpx.ConnectError:
            logger.error(f"[摘要] 無法連接 Ollama，請確認 Ollama 服務是否啟動")
            return f"（Ollama 未啟動）{item.title}"
        except Exception as e:
            logger.error(f"[摘要] 生成失敗：{e}")
            return item.title  # 降級：至少回傳標題

    async def check_ollama_available(self) -> bool:
        """
        檢查 Ollama 服務是否可用
        用於啟動時健康檢查
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
