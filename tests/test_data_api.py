from datetime import datetime, timezone

from fastapi.testclient import TestClient

from fund_advisor_data_api.api import create_app
from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_mcp.fund.adapter import FundAdvisorToolAdapter


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

    def fund_analyze(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("fund_analyze", kwargs))
        return _envelope(
            ToolName.FUND_ANALYZE,
            {
                "fund": {"code": kwargs["fund"], "name": "示例主动基金"},
                "lookback_years": kwargs["years"],
            },
        )

    def fund_profile(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("fund_profile", kwargs))
        return _envelope(
            ToolName.FUND_PROFILE,
            {
                "fund": {"code": kwargs["fund"], "name": "示例主动基金"},
                "basic_info": {"基金全称": "示例主动基金"},
            },
        )

    def fund_rating(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("fund_rating", kwargs))
        return _envelope(
            ToolName.FUND_RATING,
            {
                "fund": {"code": kwargs["fund"], "name": "示例主动基金"},
                "rating": {"招商证券": 5},
            },
        )

    def fund_status(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("fund_status", kwargs))
        return _envelope(
            ToolName.FUND_STATUS,
            {
                "fund": {"code": kwargs["fund"], "name": "示例主动基金"},
                "purchase_status": "开放申购",
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

    def stock_valuation(self, **kwargs: object) -> ToolEnvelope:
        self.calls.append(("stock_valuation", kwargs))
        return _envelope(
            ToolName.STOCK_VALUATION,
            {
                "stock": {
                    "code": kwargs["stock"],
                    "name": "示例股票",
                },
                "lookback": {"latest_date": "2026-08-17"},
                "summary": {"stock_price": {"current": 100.00001}},
            },
        )


class StubFundSearchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> ToolEnvelope:
        self.calls.append((query, limit))
        return _envelope(
            ToolName.FUND_SEARCH,
            {
                "ok": True,
                "action": "search",
                "query": query,
                "count": 1,
                "has_more": False,
                "results": [{"code": "510300", "name": "沪深300ETF"}],
                "guidance": None,
            },
        )


class StubFundStatusService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self, query: str) -> ToolEnvelope:
        self.calls.append(query)
        return _envelope(
            ToolName.FUND_STATUS,
            {
                "ok": True,
                "action": "status",
                "fund": {"code": query, "name": "示例基金"},
                "availability": {
                    "confirmed": True,
                    "mode": "off_exchange",
                    "off_exchange": {"subscription_status": "开放申购"},
                },
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
    analysis = client.get(
        "/v1/funds/000001/analysis",
        params={"years": 3},
    )
    profile = client.get("/v1/funds/000001/profile")
    rating = client.get("/v1/funds/000001/rating")
    status = client.get("/v1/funds/000001/status")
    etf = client.get(
        "/v1/etfs/510300",
        params={"years": 3, "max_points": 600},
    )
    index = client.get(
        "/v1/indices/沪深300",
        params={"years": 10, "max_points": 600},
    )
    stock = client.get(
        "/v1/stocks/600519",
        params={"years": 5, "max_points": 300},
    )

    assert health.json() == {"status": "ok"}
    assert search.json()["tool"] == "fund_search"
    assert analysis.json()["data"]["lookback_years"] == 3
    assert profile.json()["tool"] == "fund_profile"
    assert rating.json()["data_audit"][0]["frame_sha256"] == "audit-hash"
    assert status.json()["data"]["purchase_status"] == "开放申购"
    assert etf.json()["data"]["summary"]["latest_close"] == 4.801
    assert index.json()["data_audit"][0]["frame_sha256"] == "audit-hash"
    assert stock.json()["data"]["summary"]["stock_price"]["current"] == 100.00001
    assert adapter.calls == [
        ("fund_search", {"query": "沪深300", "limit": 5}),
        ("fund_analyze", {"fund": "000001", "years": 3}),
        ("fund_profile", {"fund": "000001"}),
        ("fund_rating", {"fund": "000001"}),
        ("fund_status", {"fund": "000001"}),
        (
            "etf_dashboard",
            {"fund": "510300", "years": 3, "max_points": 600},
        ),
        (
            "index_valuation",
            {"index": "沪深300", "years": 10, "max_points": 600},
        ),
        (
            "stock_valuation",
            {"stock": "600519", "years": 5, "max_points": 300},
        ),
    ]


def test_data_api_fund_search_uses_data_core_service(test_config) -> None:
    search_service = StubFundSearchService()

    def fail_factory():
        raise AssertionError("fund_search should not instantiate the legacy Skill")

    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=fail_factory,
        fund_search_service=search_service,
    )
    client = TestClient(create_app(adapter=adapter))

    response = client.get("/v1/funds/search", params={"query": "沪深300", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "fund_search"
    assert payload["data"]["results"][0]["code"] == "510300"
    assert search_service.calls == [("沪深300", 5)]


def test_data_api_fund_status_uses_data_core_service(test_config) -> None:
    status_service = StubFundStatusService()

    def fail_factory():
        raise AssertionError("fund_status should not instantiate the legacy Skill")

    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=fail_factory,
        fund_status_service=status_service,
    )
    client = TestClient(create_app(adapter=adapter))

    response = client.get("/v1/funds/000001/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "fund_status"
    assert payload["data"]["availability"]["confirmed"] is True
    assert status_service.calls == ["000001"]


def test_data_api_rejects_invalid_fund_analysis_years() -> None:
    adapter = StubDataAdapter()
    client = TestClient(create_app(adapter=adapter))  # type: ignore[arg-type]

    response = client.get(
        "/v1/funds/000001/analysis",
        params={"years": 10},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "years must be one of: 1, 3, 5"
    assert adapter.calls == []


def test_data_api_preserves_tool_failure_as_http_200_envelope() -> None:
    class FailureAdapter(StubDataAdapter):
        def fund_rating(self, **kwargs: object) -> ToolEnvelope:
            self.calls.append(("fund_rating", kwargs))
            return ToolEnvelope(
                tool=ToolName.FUND_RATING,
                ok=False,
                queried_at=datetime.now(timezone.utc),
                data_policy={"ai_may_generate_market_data": False},
                error=ToolError(
                    code="DATA_SOURCE_ERROR",
                    message="基金评级接口当前无法确认",
                    retryable=True,
                ),
            )

    adapter = FailureAdapter()
    client = TestClient(create_app(adapter=adapter))  # type: ignore[arg-type]

    response = client.get("/v1/funds/000001/rating")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "DATA_SOURCE_ERROR"


def test_data_api_rejects_invalid_stock_years() -> None:
    adapter = StubDataAdapter()
    client = TestClient(create_app(adapter=adapter))  # type: ignore[arg-type]

    response = client.get(
        "/v1/stocks/600519",
        params={"years": 20, "max_points": 600},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "years must be one of: 1, 3, 5, 10"
    assert adapter.calls == []
