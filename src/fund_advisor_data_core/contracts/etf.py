"""Typed contracts for recent ETF exchange supplement data."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ETFShareRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    total_shares: float = Field(ge=0)
    total_shares_yi_units: float = Field(ge=0)
    previous_date: date | None
    total_shares_change: float | None
    total_shares_change_yi_units: float | None


class ETFFinancingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    financing_balance_cny: float = Field(ge=0)
    financing_balance_yi_cny: float = Field(ge=0)
    previous_date: date | None
    financing_balance_change_cny: float | None
    financing_balance_change_yi_cny: float | None


class ETFConstituentFinancingRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    financing_balance_cny: float = Field(ge=0)
    financing_balance_yi_cny: float = Field(ge=0)
    previous_date: date | None
    financing_balance_change_cny: float | None
    financing_balance_change_yi_cny: float | None
    constituent_count: int = Field(gt=0)
    reported_component_count: int = Field(ge=0)
    coverage_pct: float = Field(ge=0, le=100)


class ETFShareSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "partial", "unavailable"]
    source_observations: int = Field(ge=0, le=7)
    actual_start_date: date | None
    latest_date: date | None
    value_field: Literal["total_shares"]
    change_field: Literal["total_shares_change"]
    unit: Literal["份"]
    scaled_unit: Literal["亿份"]
    latest: ETFShareRow | None
    rows: list[ETFShareRow]
    chart_series: list[tuple[date, float]]
    derived_formulas: dict[str, str]


class ETFFinancingSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "partial", "unavailable"]
    source_observations: int = Field(ge=0, le=7)
    actual_start_date: date | None
    latest_date: date | None
    value_field: Literal["financing_balance_cny"]
    change_field: Literal["financing_balance_change_cny"]
    unit: Literal["元"]
    scaled_unit: Literal["亿元"]
    latest: ETFFinancingRow | None
    rows: list[ETFFinancingRow]
    chart_series: list[tuple[date, float]]
    derived_formulas: dict[str, str]


class ETFConstituentFinancingSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["available", "partial", "unavailable"]
    tracking_index_name: str | None
    tracking_index_code: str | None
    constituent_as_of: date | None
    constituent_count: int = Field(ge=0)
    source_observations: int = Field(ge=0, le=7)
    actual_start_date: date | None
    latest_date: date | None
    unit: Literal["元"]
    scaled_unit: Literal["亿元"]
    latest: ETFConstituentFinancingRow | None
    rows: list[ETFConstituentFinancingRow]
    chart_series: list[tuple[date, float]]
    scope_note: str
    derived_formulas: dict[str, str]


class ETFRecentRangeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: Literal["one_week"]
    actual_start_date: date
    latest_date: date
    share_change_yi_units: float | None
    financing_net_change_yi_cny: float | None
    component_financing_net_change_yi_cny: float | None


class ETFSupplementIntegrity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_generated_market_data: Literal[False]
    interpolation: Literal["none"]
    forward_fill: Literal["none"]
    coverage: Literal["最近最多 7 个已审计交易日"]


class ETFSupplementData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund_code: str = Field(pattern=r"^\d{6}$")
    requested_trading_dates: list[date] = Field(max_length=7)
    share: ETFShareSeries
    financing: ETFFinancingSeries
    component_financing: ETFConstituentFinancingSeries
    range_summaries: list[ETFRecentRangeSummary]
    unavailable_metrics: list[str]
    data_integrity: ETFSupplementIntegrity
