"""Agent domain models shared by orchestration, API and persistence."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_ANALYSIS = "fund_analysis"
    FUND_STATUS = "fund_status"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    FUND_COMPARE = "fund_compare"
    DCA_REFERENCE = "dca_reference"
    SELL_OR_REBALANCE = "sell_or_rebalance"
    DOCUMENT_QA = "document_qa"
    WEB_RESEARCH = "web_research"
    UNSUPPORTED = "unsupported"


class TaskStatus(StrEnum):
    RECEIVED = "received"
    RUNNING = "running"
    NEED_CLARIFICATION = "need_clarification"
    PARTIAL_RESULT = "partial_result"
    CANNOT_CONFIRM = "cannot_confirm"
    POLICY_BLOCKED = "policy_blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class EntityCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    query: str
    code: str | None = None
    name: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    entities: list[EntityCandidate] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)


class ToolPlanItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    arguments: dict[str, Any]
    reason: str


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    question: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class AgentFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    code: str
    message: str
    retryable: bool = False
    source: str
    details: dict[str, Any] = Field(default_factory=dict)
