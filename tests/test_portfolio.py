from datetime import datetime, timezone
from decimal import Decimal

from financial_agent.portfolio import (
    Portfolio,
    Position,
    analyze_portfolio,
    qualitative_portfolio_context,
)


def test_portfolio_math_is_decimal_and_private_context_is_redacted() -> None:
    portfolio = Portfolio(
        positions=[
            Position(
                fund_code="510300",
                channel="exchange",
                units=Decimal("100"),
                average_cost=Decimal("4.00"),
                currency="CNY",
                target_weight_pct=Decimal("40"),
                updated_at=datetime.now(timezone.utc),
            ),
            Position(
                fund_code="510500",
                channel="exchange",
                units=Decimal("50"),
                average_cost=Decimal("5.00"),
                currency="CNY",
                target_weight_pct=Decimal("60"),
                updated_at=datetime.now(timezone.utc),
            ),
        ]
    )

    result = analyze_portfolio(
        portfolio,
        {"510300": Decimal("5.00"), "510500": Decimal("5.00")},
    )
    private = qualitative_portfolio_context(result)

    assert result.total_market_value == Decimal("750.00")
    assert result.positions[0].weight_pct == Decimal("66.67")
    assert result.positions[0].unrealized_return_pct == Decimal("25.00")
    assert "market_value" not in str(private)
    assert private["positions"][0]["fund_code_masked"] == "51****"


def test_missing_nav_prevents_silent_full_portfolio_calculation() -> None:
    portfolio = Portfolio(
        positions=[
            Position(
                fund_code="510300",
                channel="exchange",
                units=Decimal("100"),
                average_cost=Decimal("4.00"),
                currency="CNY",
                updated_at=datetime.now(timezone.utc),
            )
        ]
    )
    result = analyze_portfolio(portfolio, {})
    assert result.total_market_value == 0
    assert result.warnings
