"""Standalone REST API for audited dashboard data."""

from __future__ import annotations

import argparse

from fastapi import FastAPI, HTTPException, Query

from fund_advisor_mcp.fund.adapter import FundAdvisorToolAdapter
from fund_advisor_mcp.fund.schemas import ToolEnvelope


def create_app(*, adapter: FundAdvisorToolAdapter | None = None) -> FastAPI:
    data_adapter = adapter or FundAdvisorToolAdapter()
    application = FastAPI(
        title="Fund Advisor Data API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/v1/funds/search", response_model=ToolEnvelope)
    def fund_search(
        query: str = Query(min_length=1, max_length=100),
        limit: int = Query(default=10, ge=1, le=20),
    ) -> ToolEnvelope:
        return data_adapter.fund_search(query=query, limit=limit)

    @application.get("/v1/etfs/{fund}", response_model=ToolEnvelope)
    def etf_dashboard(
        fund: str,
        years: int = Query(default=3),
        max_points: int = Query(default=600, ge=50, le=3000),
    ) -> ToolEnvelope:
        _require_years(years, {1, 3, 5})
        return data_adapter.etf_dashboard(
            fund=fund,
            years=years,
            max_points=max_points,
        )

    @application.get("/v1/indices/{index}", response_model=ToolEnvelope)
    def index_valuation(
        index: str,
        years: int = Query(default=10),
        max_points: int = Query(default=600, ge=50, le=3000),
    ) -> ToolEnvelope:
        _require_years(years, {3, 5, 10, 20})
        return data_adapter.index_valuation(
            index=index,
            years=years,
            max_points=max_points,
        )

    return application


def _require_years(value: int, allowed: set[int]) -> None:
    if value not in allowed:
        choices = ", ".join(str(item) for item in sorted(allowed))
        raise HTTPException(
            status_code=422,
            detail=f"years must be one of: {choices}",
        )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Fund Advisor Data API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(
        "fund_advisor_data_api.api:create_app",
        host=args.host,
        port=args.port,
        factory=True,
    )
if __name__ == "__main__":
    main()
