"""Evidence, Claim and report contracts.

The report surface is deliberately structured. Every rendered financial fact
keeps its evidence id so the API can expose a complete provenance chain.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class EvidenceType(StrEnum):
    TOOL_FACT = "TOOL_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    DOCUMENT_FACT = "DOCUMENT_FACT"
    USER_FACT = "USER_FACT"
    POLICY_RULE = "POLICY_RULE"
    MODEL_INTERPRETATION = "MODEL_INTERPRETATION"


class Freshness(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UNKNOWN = "unknown"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    id: str
    name: str | None = None


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    type: EvidenceType
    subject: EvidenceSubject
    field: str
    value: Any
    display_value: str | None = None
    unit: str | None = None
    as_of: date | datetime | None = None
    source_ref: str
    audit_ref: str | None = None
    freshness: Freshness = Freshness.UNKNOWN
    confidence: Confidence = Confidence.MEDIUM
    numeric_allowed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimType(StrEnum):
    FACT = "fact"
    DERIVED = "derived"
    INTERPRETATION = "interpretation"
    WARNING = "warning"


class ClaimRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    claim_type: ClaimType
    template_id: str
    arguments: dict[str, UUID]
    evidence_ids: list[UUID]
    allowed: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grade: Literal["A", "B", "C", "D", "E"]
    allowed_claim_types: set[ClaimType] = Field(default_factory=set)
    blocked_evidence_ids: list[UUID] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    policy_version: str = "2026-07-01"


class ReportFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: Any
    display_value: str
    unit: str | None = None
    as_of: date | datetime | None = None
    evidence_id: UUID


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    title: str
    url: str
    page: int | None = None
    version: str | None = None


class ResearchReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID = Field(default_factory=uuid4)
    task_id: UUID
    status: str
    title: str
    summary: str
    facts: list[ReportFact] = Field(default_factory=list)
    analysis: list[str] = Field(default_factory=list)
    buy_conditions: list[str] = Field(default_factory=list)
    sell_or_rebalance_conditions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    evidence_grade: Literal["A", "B", "C", "D", "E"]
    generated_at: datetime
    disclaimer: str = "仅供信息研究和风险参考，不构成投资建议或收益承诺。"
