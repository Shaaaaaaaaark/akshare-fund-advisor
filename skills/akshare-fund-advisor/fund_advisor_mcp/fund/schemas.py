"""Strongly typed contracts for the Fund Advisor MCP boundary."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ToolName(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_STATUS = "fund_status"
    FUND_ANALYZE = "fund_analyze"
    FUND_PROFILE = "fund_profile"
    FUND_RATING = "fund_rating"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    FUND_COMPARE = "fund_compare"
    INTERFACE_AUDIT = "interface_audit"


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID = Field(default_factory=uuid4)
    tool: ToolName
    ok: bool
    data: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    data_audit: list[dict[str, Any]] = Field(default_factory=list)
    data_warnings: list[dict[str, Any] | str] = Field(default_factory=list)
    data_policy: dict[str, Any] = Field(default_factory=dict)
    queried_at: datetime
    error: ToolError | None = None


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=20)


class FundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund: str = Field(min_length=1, max_length=100)


class AnalyzeInput(FundInput):
    years: Literal[1, 3, 5] = 3


class ValuationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: str = Field(min_length=1, max_length=100)
    years: Literal[3, 5, 10, 20] = 10
    max_points: int = Field(default=600, ge=50, le=3000)


class StockValuationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stock: str = Field(min_length=1, max_length=100)
    years: Literal[1, 3, 5, 10] = 10
    max_points: int = Field(default=600, ge=50, le=3000)


class CompareInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funds: list[str] = Field(min_length=2, max_length=5)
    years: Literal[1, 3, 5] = 3


class AuditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund: str = "000001"
    etf: str = "510300"
    lof: str = "166009"
    index: str = "沪深300"
