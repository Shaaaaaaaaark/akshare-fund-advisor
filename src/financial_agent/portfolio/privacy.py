"""Convert private portfolio data into model-safe qualitative context."""

from __future__ import annotations

from .calculator import PortfolioAnalysis


def qualitative_portfolio_context(
    analysis: PortfolioAnalysis,
) -> dict[str, object]:
    positions: list[dict[str, str]] = []
    for item in analysis.positions:
        if item.target_weight_pct is None:
            relation = "目标仓位未设置"
        elif item.weight_pct > item.target_weight_pct:
            relation = "高于目标仓位"
        elif item.weight_pct < item.target_weight_pct:
            relation = "低于目标仓位"
        else:
            relation = "接近目标仓位"
        positions.append(
            {
                "fund_code_masked": f"{item.fund_code[:2]}****",
                "position_relation": relation,
                "return_state": (
                    "浮盈"
                    if item.unrealized_return_pct > 0
                    else "浮亏"
                    if item.unrealized_return_pct < 0
                    else "持平"
                ),
            }
        )
    return {
        "positions": positions,
        "warnings": analysis.warnings,
        "privacy_policy": "金额、份额、成本和精确比例已移除",
    }
