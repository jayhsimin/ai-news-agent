"""
Agents 模組
匯出所有 Agent 類別，支援未來擴充成 multi-agent system
"""

from agents.base import BaseAgent, AgentResult, AgentStatus
from agents.collector_agent import CollectorAgent
from agents.analyzer_agent import AnalyzerAgent
from agents.publisher_agent import PublisherAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "AgentStatus",
    "CollectorAgent",
    "AnalyzerAgent",
    "PublisherAgent",
]
