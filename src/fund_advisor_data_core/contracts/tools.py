"""Tool identifiers shared by Data API, MCP, and Agent callers."""

from __future__ import annotations

from enum import StrEnum


class ToolName(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_STATUS = "fund_status"
    FUND_ANALYZE = "fund_analyze"
    ETF_DASHBOARD = "etf_dashboard"
    FUND_PROFILE = "fund_profile"
    FUND_RATING = "fund_rating"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    FUND_COMPARE = "fund_compare"
    INTERFACE_AUDIT = "interface_audit"

