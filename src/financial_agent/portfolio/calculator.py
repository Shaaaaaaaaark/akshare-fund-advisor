"""Deterministic portfolio calculations; no LLM dependency."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from .models import Portfolio

_MONEY_QUANT = Decimal("0.01")
_PERCENT_QUANT = Decimal("0.01")


class PositionAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fund_code: str
    market_value: Decimal
    weight_pct: Decimal
    unrealized_return_pct: Decimal
    target_weight_pct: Decimal | None
    rebalance_amount: Decimal | None


class PortfolioAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_market_value: Decimal
    positions: list[PositionAnalysis] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def analyze_portfolio(
    portfolio: Portfolio,
    current_nav: dict[str, Decimal],
) -> PortfolioAnalysis:
    values: dict[str, Decimal] = {}
    warnings: list[str] = []
    for position in portfolio.positions:
        nav = current_nav.get(position.fund_code)
        if nav is None:
            warnings.append(f"{position.fund_code} 缺少当前净值，未计算完整组合。")
            continue
        if position.currency != "CNY":
            warnings.append(f"{position.fund_code} 币种不是 CNY，缺少汇率时不合并。")
            continue
        values[position.fund_code] = position.units * nav

    total = sum(values.values(), Decimal("0"))
    if total <= 0:
        return PortfolioAnalysis(
            total_market_value=Decimal("0"),
            warnings=[*warnings, "没有可计算的正市值持仓。"],
        )

    analyses: list[PositionAnalysis] = []
    for position in portfolio.positions:
        market_value = values.get(position.fund_code)
        nav = current_nav.get(position.fund_code)
        if market_value is None or nav is None:
            continue
        weight = market_value / total * Decimal("100")
        return_pct = (nav - position.average_cost) / position.average_cost * Decimal("100")
        target_amount = (
            total * position.target_weight_pct / Decimal("100")
            if position.target_weight_pct is not None
            else None
        )
        analyses.append(
            PositionAnalysis(
                fund_code=position.fund_code,
                market_value=_money(market_value),
                weight_pct=_percent(weight),
                unrealized_return_pct=_percent(return_pct),
                target_weight_pct=position.target_weight_pct,
                rebalance_amount=(
                    _money(target_amount - market_value) if target_amount is not None else None
                ),
            )
        )
    return PortfolioAnalysis(
        total_market_value=_money(total),
        positions=analyses,
        warnings=warnings,
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _percent(value: Decimal) -> Decimal:
    return value.quantize(_PERCENT_QUANT, rounding=ROUND_HALF_UP)
