"""Deterministic suitability checks for amount-specific guidance."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from financial_agent.domain import Intent
from financial_agent.portfolio import RiskProfile


class SuitabilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    general_research_allowed: bool = True
    specific_amount_allowed: bool = False
    missing_information: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def check_suitability(
    intent: Intent,
    user_context: dict[str, Any],
    now: datetime,
) -> SuitabilityDecision:
    if intent not in {Intent.DCA_REFERENCE, Intent.SELL_OR_REBALANCE}:
        return SuitabilityDecision()

    raw_profile = user_context.get("risk_profile")
    raw_portfolio = user_context.get("portfolio")
    missing: list[str] = []
    warnings: list[str] = []
    if raw_profile is None:
        missing.append("风险画像")
    if raw_portfolio is None:
        missing.append("当前持仓与目标仓位")
    if missing:
        return SuitabilityDecision(
            missing_information=missing,
            warnings=["用户信息不完整，本次不输出具体金额。"],
        )

    try:
        profile = RiskProfile.model_validate(raw_profile)
    except Exception:
        return SuitabilityDecision(
            missing_information=["有效的风险画像"],
            warnings=["风险画像格式无效，本次不输出具体金额。"],
        )
    if profile.expires_at <= now:
        return SuitabilityDecision(
            missing_information=["未过期的风险画像"],
            warnings=["风险画像已过期，本次不输出具体金额。"],
        )
    if not profile.emergency_fund_ready:
        warnings.append("应急资金尚未确认充足。")
    if profile.horizon_months < 36:
        warnings.append("投资期限较短，不输出长期权益类投入金额。")
    allowed = (
        profile.emergency_fund_ready and profile.stable_cash_flow and profile.horizon_months >= 36
    )
    return SuitabilityDecision(
        specific_amount_allowed=allowed,
        warnings=warnings,
    )
