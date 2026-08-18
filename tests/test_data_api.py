from datetime import datetime, timezone

from fastapi.testclient import TestClient

from fund_advisor_data_api.api import create_app
from fund_advisor_mcp.fund.schemas import ToolEnvelope, ToolName


class StubDataAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def fund_search(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("fund_search", kwargs))
        return _envelope(
            ToolName.FUND_SEARCH,
            {
                "results": [
                    {
                        "code": "510300",
                        "name": "沪深300ETF华泰柏瑞",
                        "type": "指数型-股票",
                    }
                ]
            },
        )

    def etf_dashboard(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("etf_dashboard", kwargs))
        return _envelope(
            ToolName.ETF_DASHBOARD,
            {
                "identity": {"code": kwargs["fund"], "name": "示例ETF"},
                "summary": {"latest_date": "2026-08-17", "latest_close": 4.801},
            },
        )

    def index_valuation(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("index_valuation", kwargs))
        return _envelope(
            ToolName.INDEX_VALUATION,
            {
                "summary": {"pe_ttm": {"current": 13.62}},
                "charts": {"pe_ttm": {"latest_date": "2026-08-17"}},
            },
        )


def _envelope(tool: ToolName, data: dict[str, object]) -> ToolEnvelope:
    return ToolEnvelope(
        tool=tool,
        ok=True,
        data=data,
        queried_at=datetime.now(timezone.utc),
        data_audit=[
            {
                "interface": "stub",
                "validation": "passed",
                "frame_sha256": "audit-hash",
            }
        ],
        data_policy={"ai_may_generate_market_data": False},
    )


def test_data_api_exposes_dashboard_rest_without_mcp_protocol() -> None:
    adapter = StubDataAdapter()
    client = TestClient(create_app(adapter=adapter))  # type: ignore[arg-type]

    health = client.get("/health")
    search = client.get("/v1/funds/search", params={"query": "沪深300", "limit": 5})
    etf = client.get(
        "/v1/etfs/510300",
        params={"years": 3, "max_points": 600},
    )
    index = client.get(
        "/v1/indices/沪深300",
        params={"years": 10, "max_points": 600},
    )

    assert health.json() == {"status": "ok"}
    assert search.json()["tool"] == "fund_search"
    assert etf.json()["data"]["summary"]["latest_close"] == 4.801
    assert index.json()["data_audit"][0]["frame_sha256"] == "audit-hash"
    assert adapter.calls == [
        ("fund_search", {"query": "沪深300", "limit": 5}),
        (
            "etf_dashboard",
            {"fund": "510300", "years": 3, "max_points": 600},
        ),
        (
            "index_valuation",
            {"index": "沪深300", "years": 10, "max_points": 600},
        ),
    ]
