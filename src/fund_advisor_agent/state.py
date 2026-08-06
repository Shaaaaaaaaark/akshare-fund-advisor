"""Pydantic contracts for the fixed LangGraph workflow."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_ANALYSIS = "fund_analysis"
    FUND_STATUS = "fund_status"
    FUND_COMPARE = "fund_compare"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    WEB_RESEARCH = "web_research"
    DOCUMENT_READ = "document_read"
    UNSUPPORTED = "unsupported"


class AgentStatus(StrEnum):
    RUNNING = "running"
    NEED_CLARIFICATION = "need_clarification"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    CANNOT_CONFIRM = "cannot_confirm"
    STALE_DATA = "stale_data"
    PARTIAL_RESULT = "partial_result"
    COMPLETED = "completed"
    FAILED = "failed"


class RegisteredTool(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_STATUS = "fund_status"
    FUND_ANALYZE = "fund_analyze"
    FUND_PROFILE = "fund_profile"
    FUND_RATING = "fund_rating"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    FUND_COMPARE = "fund_compare"
    INTERFACE_AUDIT = "interface_audit"
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    DOCUMENT_READ = "document_read"


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    entities: list[str] = Field(default_factory=list, max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)


class ToolCallSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: RegisteredTool
    arguments: dict[str, Any] = Field(default_factory=dict)
    source: Literal["fund", "web"]
    required: bool = True


class ToolExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: RegisteredTool
    arguments: dict[str, Any] = Field(default_factory=dict)
    source: Literal["fund", "web"]
    required: bool = True
    envelope: dict[str, Any]


class FactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str
    tool: RegisteredTool
    field_path: str
    label: str
    value: Any
    unit: str | None = None
    as_of: str | None = None
    audit_ref: str | None = None
    source_kind: Literal["market", "entity", "background"] = "market"


class Relationship(StrEnum):
    CO_OCCURRENCE = "co_occurrence"
    CONTRAST = "contrast"
    CONSISTENCY = "consistency"
    DATA_LIMIT = "data_limit"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AssociationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_refs: list[str] = Field(min_length=2)
    relationship: Relationship
    explanation: str = Field(min_length=1, max_length=500)
    causal_claim: Literal[False] = False
    confidence: Confidence


class AssociationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    associations: list[AssociationDraft] = Field(default_factory=list)


class AgentError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    intent: Intent | None = None
    entities: list[str] = Field(default_factory=list)
    tool_plan: list[ToolCallSpec] = Field(default_factory=list)
    tool_results: list[ToolExecution] = Field(default_factory=list)
    facts: list[FactRef] = Field(default_factory=list)
    associations: list[AssociationDraft] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.RUNNING
    final_answer: str | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AgentStatus
    facts: list[FactRef] = Field(default_factory=list)
    associations: list[AssociationDraft] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[AgentError] = Field(default_factory=list)
    answer: str
