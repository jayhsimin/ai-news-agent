"""
Agent 基礎模組
定義 BaseAgent 介面，為未來擴充成 multi-agent system 預留架構
每個 Agent 可獨立執行、可串接、可並發
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from loguru import logger


class AgentStatus(str, Enum):
    """Agent 執行狀態"""
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class AgentResult:
    """
    Agent 執行結果的標準格式
    所有 Agent 的 run() 方法必須回傳此格式，確保 orchestrator 可統一處理
    """
    agent_name: str
    status: AgentStatus
    data: Any = None                          # 執行結果資料
    error: Optional[str] = None              # 錯誤訊息
    metadata: dict = field(default_factory=dict)  # 附加資訊（統計、計時等）
    executed_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class BaseAgent(ABC):
    """
    Agent 抽象基底類別

    設計原則：
    - 每個 Agent 負責單一職責（SRP）
    - 透過 AgentResult 傳遞結果，不直接修改全域狀態
    - 支援 async 執行，可並發協作
    - 內建執行計時與狀態記錄

    未來擴充方向：
    - 可加入 message queue（Redis Pub/Sub）讓 Agent 間互相通訊
    - 可加入 Agent Registry 進行動態發現
    - 可加入 retry 策略、circuit breaker
    """

    def __init__(self, name: str):
        self.name = name
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def run(self, input_data: Any = None) -> AgentResult:
        """
        Agent 主要執行邏輯
        子類別必須實作此方法
        input_data：上一個 Agent 傳入的資料（串接模式）
        """
        raise NotImplementedError

    async def safe_run(self, input_data: Any = None) -> AgentResult:
        """
        帶有例外保護的執行方法
        任何 Agent 失敗時，不影響整體 pipeline
        """
        self.status = AgentStatus.RUNNING
        start = datetime.utcnow()

        try:
            result = await self.run(input_data)
            self.status = result.status

            # 記錄執行耗時
            elapsed = (datetime.utcnow() - start).total_seconds()
            result.metadata["elapsed_seconds"] = elapsed

            logger.info(
                f"[{self.name}] 執行完成，狀態：{result.status.value}，"
                f"耗時：{elapsed:.1f}s"
            )
            return result

        except Exception as e:
            self.status = AgentStatus.FAILED
            elapsed = (datetime.utcnow() - start).total_seconds()
            logger.error(f"[{self.name}] 執行失敗（{elapsed:.1f}s）：{e}")

            return AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(e),
                metadata={"elapsed_seconds": elapsed},
            )
