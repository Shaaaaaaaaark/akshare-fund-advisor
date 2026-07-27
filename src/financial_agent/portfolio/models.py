"""User risk profile and private portfolio contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(StrEnum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    GROWTH = "growth"
    AGGRESSIVE = "aggressive"


class RiskProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: RiskLevel
    horizon_months: int = Field(ge=1)
    max_drawdown_tolerance_pct: Decimal = Field(ge=0, le=100)
    emergency_fund_ready: bool
    stable_cash_flow: bool
    target_allocation: dict[str, Decimal] = Field(default_factory=dict)
    assessed_at: datetime
    expires_at: datetime


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund_code: str = Field(pattern=r"^\d{6}$")
    share_class: str | None = None
    channel: str
    units: Decimal = Field(ge=0)
    average_cost: Decimal = Field(gt=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    target_weight_pct: Decimal | None = Field(default=None, ge=0, le=100)
    updated_at: datetime


class Portfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    positions: list[Position] = Field(default_factory=list, max_length=200)
