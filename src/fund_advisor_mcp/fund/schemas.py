"""Strongly typed request schemas for the Fund Advisor MCP boundary."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fund_advisor_data_core.contracts import ToolEnvelope as ToolEnvelope
from fund_advisor_data_core.contracts import ToolError as ToolError
from fund_advisor_data_core.contracts import ToolName as ToolName


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=10, ge=1, le=20)


class FundInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund: str = Field(min_length=1, max_length=100)


class AnalyzeInput(FundInput):
    years: Literal[1, 3, 5] = 3


class ETFDashboardInput(AnalyzeInput):
    max_points: int = Field(default=600, ge=50, le=3000)


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


class QDIIBoardInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
