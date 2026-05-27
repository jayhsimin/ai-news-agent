"""
Telegram 推播通知器
使用官方免費 Bot API 推播 AI 資訊到指定頻道或群組
格式清晰、支援 HTML 格式、自動截斷過長訊息
"""

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from collectors.base import NewsItem
from config import settings

# Telegram Bot API 基礎 URL
TELEGRAM_API_BASE = "https://api.telegram.org"

# 分類對應的 emoji（讓訊息更直觀）
CATEGORY_EMOJI = {
    "模型發布": "🚀",
    "研究論文": "📄",
    "工具與框架": "🛠️",
    "教學與資源": "📚",
    "產業動態": "💼",
    "基準測試": "📊",
    "安全與倫理": "🔒",
    "硬體與基礎設施": "💻",
    "其他": "📰",
}

# 來源對應的 emoji
SOURCE_EMOJI = {
    "reddit": "🟠",
    "hackernews": "🟡",
    "github": "⚫",
    "arxiv": "🔵",
}


class TelegramNotifier:
    """
    Telegram 推播器
    將處理後的 NewsItem 格式化並發送到 Telegram 頻道/群組
    """

    def __init__(self):
        if not settings.is_telegram_configured:
            logger.warning(
                "Telegram 未設定！請在 .env 填入 TELEGRAM_BOT_TOKEN 與 TELEGRAM_CHAT_ID\n"
                "建立 Bot：https://t.me/BotFather"
            )
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def send(self, item: NewsItem) -> bool:
        """
        發送單篇文章通知到 Telegram
        回傳值：True 表示發送成功
        """
        if not settings.is_telegram_configured:
            logger.warning("[Telegram] 未設定，跳過推播")
            return False

        message = self._format_message(item)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,  # 顯示連結預覽
                        "disable_notification": False,
                    },
                )

                if resp.status_code == 200:
                    logger.info(f"[Telegram] 推播成功：{item.title[:50]}")
                    return True
                else:
                    # 記錄錯誤詳情方便排查
                    error_data = resp.json()
                    logger.error(
                        f"[Telegram] 推播失敗 HTTP {resp.status_code}：{error_data}"
                    )
                    return False

        except Exception as e:
            logger.error(f"[Telegram] 推播例外：{e}")
            raise

    def _format_message(self, item: NewsItem) -> str:
        """
        格式化推播訊息
        使用 Telegram HTML 格式排版，清晰易讀
        """
        # 取得分類 emoji
        category = item.category or "其他"
        cat_emoji = CATEGORY_EMOJI.get(category, "📰")
        src_emoji = SOURCE_EMOJI.get(item.source, "🌐")

        # 相關性分數視覺化（星星數）
        score = item.relevance_score or 0
        stars = "⭐" * min(int(score / 2), 5)  # 最多 5 顆星

        # 組裝訊息
        lines = [
            f"{cat_emoji} <b>{self._escape_html(item.title)}</b>",
            "",
            f"📝 {self._escape_html(item.summary or '（無摘要）')}",
            "",
            f"{src_emoji} 來源：<b>{item.source.upper()}</b>  |  🏷 {category}",
            f"📊 重要性：{stars} {score:.1f}/10",
            "",
            f"🔗 <a href=\"{item.url}\">閱讀全文</a>",
        ]

        # 加入標籤（最多顯示 3 個）
        relevant_tags = [t for t in item.tags if t and not t.startswith("score:") and not t.startswith("comments:")]
        if relevant_tags:
            tag_str = " ".join(f"#{self._escape_html(t.replace(' ', '_'))}" for t in relevant_tags[:3])
            lines.append(f"\n{tag_str}")

        message = "\n".join(lines)

        # Telegram 單則訊息上限 4096 字元，超過則截斷
        if len(message) > 4000:
            message = message[:3997] + "..."

        return message

    @staticmethod
    def _escape_html(text: str) -> str:
        """
        轉義 HTML 特殊字元，避免 Telegram HTML parse 失敗
        """
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    async def send_system_message(self, text: str) -> bool:
        """
        發送系統通知訊息（例如：採集開始、錯誤警報等）
        """
        if not settings.is_telegram_configured:
            return False

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{TELEGRAM_API_BASE}/bot{self.bot_token}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": f"🤖 <b>AI News Agent</b>\n\n{text}",
                        "parse_mode": "HTML",
                        "disable_notification": True,  # 系統訊息靜音
                    },
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"[Telegram] 系統訊息發送失敗：{e}")
            return False
