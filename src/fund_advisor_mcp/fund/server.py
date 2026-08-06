"""MCP stdio server exposing the nine audited Fund Advisor tools."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from fund_advisor_mcp.config import get_config

from .adapter import FundAdvisorToolAdapter

settings = get_config()
mcp = FastMCP(
    "fund-advisor",
    instructions=(
        "Chinese fund and index research tools. Market numbers returned by these "
        "tools must be preserved with their data_audit fields."
    ),
    host=settings.mcp.host,
    port=settings.mcp.port,
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@lru_cache(maxsize=1)
def get_adapter() -> FundAdvisorToolAdapter:
    return FundAdvisorToolAdapter()


def _dump(result: Any) -> dict[str, Any]:
    return result.model_dump(mode="json")


@mcp.tool()
def fund_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Search Chinese public funds without choosing an ambiguous share class."""
    return _dump(get_adapter().fund_search(query=query, limit=limit))


@mcp.tool()
def fund_status(fund: str) -> dict[str, Any]:
    """Return subscription/redemption or exchange-session status."""
    return _dump(get_adapter().fund_status(fund=fund))


@mcp.tool()
def fund_analyze(fund: str, years: int = 3) -> dict[str, Any]:
    """Analyze a uniquely identified fund using audited AKShare facts."""
    return _dump(get_adapter().fund_analyze(fund=fund, years=years))


@mcp.tool()
def index_valuation(
    index: str,
    years: int = 10,
    max_points: int = 600,
) -> dict[str, Any]:
    """Return independently calculated PE TTM and PB history."""
    return _dump(
        get_adapter().index_valuation(
            index=index,
            years=years,
            max_points=max_points,
        )
    )


@mcp.tool()
def stock_valuation(
    stock: str,
    years: int = 10,
    max_points: int = 600,
) -> dict[str, Any]:
    """Return audited stock PE TTM, PB and adjusted price history."""
    return _dump(
        get_adapter().stock_valuation(
            stock=stock,
            years=years,
            max_points=max_points,
        )
    )


@mcp.tool()
def fund_compare(funds: list[str], years: int = 3) -> dict[str, Any]:
    """Compare two to five funds while preserving their metric bases."""
    return _dump(get_adapter().fund_compare(funds=funds, years=years))


@mcp.tool()
def fund_profile(fund: str) -> dict[str, Any]:
    """Return audited fund profile: basics, fee rules and asset allocation."""
    return _dump(get_adapter().fund_profile(fund=fund))


@mcp.tool()
def fund_rating(fund: str) -> dict[str, Any]:
    """Return third-party fund ratings and category by exact code match."""
    return _dump(get_adapter().fund_rating(fund=fund))


@mcp.tool()
def interface_audit(
    fund: str = "000001",
    etf: str = "510300",
    lof: str = "166009",
    index: str = "沪深300",
) -> dict[str, Any]:
    """Run live AKShare interface and schema audits."""
    return _dump(
        get_adapter().interface_audit(
            fund=fund,
            etf=etf,
            lof=lof,
            index=index,
        )
    )


def main() -> None:
    transport = "streamable-http" if settings.mcp.transport == "http" else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
