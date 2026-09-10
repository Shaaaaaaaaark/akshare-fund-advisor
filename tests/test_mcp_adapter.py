from datetime import datetime
from threading import Event, Lock
from zoneinfo import ZoneInfo

import pytest

from fund_advisor_data_core.services import ETFSupplementResult
from fund_advisor_mcp.fund.adapter import (
    FundAdvisorToolAdapter,
    ToolExecutionTimeout,
)
from fund_advisor_mcp.fund.schemas import ToolEnvelope, ToolName

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeFundSearchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int) -> ToolEnvelope:
        self.calls.append((query, limit))
        return ToolEnvelope(
            tool=ToolName.FUND_SEARCH,
            ok=True,
            data={
                "ok": True,
                "action": "search",
                "query": query,
                "count": 1,
                "has_more": False,
                "results": [{"code": "000001", "name": "示例基金"}],
                "guidance": None,
            },
            queried_at=datetime.now(SHANGHAI),
            sources=[{"provider": "AKShare", "interface": "fund_name_em"}],
            data_audit=[
                {
                    "interface": "fund_name_em",
                    "validation": "passed",
                    "frame_sha256": "data-core-hash",
                }
            ],
            data_policy={"ai_may_generate_market_data": False},
        )


class FakeFundStatusService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def status(self, query: str) -> ToolEnvelope:
        self.calls.append(query)
        return ToolEnvelope(
            tool=ToolName.FUND_STATUS,
            ok=True,
            data={
                "ok": True,
                "action": "status",
                "fund": {"code": "000001", "name": "示例基金"},
                "availability": {
                    "confirmed": True,
                    "mode": "off_exchange",
                    "off_exchange": {"subscription_status": "开放申购"},
                },
            },
            queried_at=datetime.now(SHANGHAI),
            sources=[{"provider": "AKShare", "interface": "fund_purchase_em"}],
            data_audit=[
                {
                    "interface": "fund_purchase_em",
                    "validation": "passed",
                    "frame_sha256": "status-core-hash",
                }
            ],
            data_policy={"ai_may_generate_market_data": False},
        )


class FakeMarketPulseService:
    def __init__(self) -> None:
        self.calls = 0

    def pulse(self) -> ToolEnvelope:
        self.calls += 1
        return ToolEnvelope(
            tool=ToolName.MARKET_PULSE,
            ok=True,
            data={
                "market": "A股",
                "snapshot_at": "2026-09-10T09:35:00+08:00",
                "sectors": [{"rank": 1, "name": "银行", "change_pct": 1.38}],
                "poll_topics": [],
            },
            queried_at=datetime.now(SHANGHAI),
            sources=[
                {
                    "provider": "AKShare",
                    "interface": "stock_board_industry_summary_ths",
                }
            ],
            data_audit=[
                {
                    "interface": "stock_board_industry_summary_ths",
                    "validation": "passed",
                    "frame_sha256": "market-pulse-hash",
                }
            ],
            data_policy={"ai_may_generate_market_data": False},
        )


class FakeAdvisor:
    def __init__(self):
        self.sources = [{"provider": "AKShare", "interface": "fund_name_em"}]
        self.data_audit = [
            {
                "interface": "fund_name_em",
                "validation": "passed",
                "frame_sha256": "source-hash",
            }
        ]
        self.data_warnings = []

    def search(self, query, _limit):
        _ = _limit
        return {
            "ok": True,
            "action": "search",
            "query": query,
            "count": 1,
            "results": [{"code": "000001", "name": "示例基金"}],
        }

    def etf_dashboard(self, fund, years, max_points):
        return {
            "ok": True,
            "action": "etf_dashboard",
            "identity": {"code": fund, "name": "示例ETF"},
            "tracking_index": {
                "name": "沪深300",
                "index_code": "000300",
            },
            "lookback": {
                "requested_years": years,
                "chart_max_points": max_points,
            },
            "summary": {"latest_close": 4.801},
            "recent_rows": [
                {"date": "2026-08-26"},
                {"date": "2026-08-27"},
            ],
            "missing_or_not_reliably_available": ["ETF 历史总份额"],
            "data_integrity": {"source_interface": "fund_etf_hist_em"},
        }

    def common_output(self):
        return {
            "queried_at": datetime.now(SHANGHAI),
            "sources": self.sources,
            "data_audit": self.data_audit,
            "data_warnings": self.data_warnings,
            "data_policy": {"ai_may_generate_market_data": False},
        }


class FakeETFSupplementService:
    def recent(self, code, trading_dates, *, tracking_index=None):
        assert code == "510300"
        assert trading_dates == ["2026-08-26", "2026-08-27"]
        assert tracking_index == {
            "name": "沪深300",
            "index_code": "000300",
        }
        return ETFSupplementResult(
            data={
                "share": {
                    "rows": [
                        {
                            "date": "2026-08-27",
                            "total_shares_yi_units": 120.5,
                        }
                    ]
                },
                "financing": {
                    "rows": [
                        {
                            "date": "2026-08-27",
                            "financing_balance_yi_cny": 3.5,
                        }
                    ]
                },
                "component_financing": {
                    "rows": [
                        {
                            "date": "2026-08-27",
                            "financing_balance_yi_cny": 9800.0,
                            "financing_balance_change_yi_cny": 12.5,
                            "reported_component_count": 300,
                            "coverage_pct": 100.0,
                        }
                    ]
                },
                "unavailable_metrics": ["净申购赎回金额"],
            },
            sources=[
                {
                    "provider": "AKShare",
                    "interface": "fund_etf_scale_sse",
                }
            ],
            data_audit=[
                {
                    "interface": "fund_etf_scale_sse",
                    "validation": "passed",
                    "frame_sha256": "supplement-hash",
                }
            ],
            data_warnings=[],
        )


class FakeCrossValidationAdvisor:
    def stock_valuation(self, query, years, max_points):
        return {
            "ok": True,
            "action": "stock_valuation",
            "stock": {"code": query},
            "years": years,
            "max_points": max_points,
            "summary": {"stock_price": {"current": 100.0}},
        }

    def common_output(self):
        return {
            "queried_at": datetime.now(SHANGHAI),
            "sources": [
                {"provider": "AKShare", "interface": "stock_zh_a_daily"},
                {
                    "provider": "Baostock",
                    "interface": "baostock.query_history_k_data_plus",
                },
            ],
            "data_audit": [
                {
                    "interface": "stock_zh_a_daily",
                    "validation": "passed",
                    "frame_sha256": "primary-hash",
                    "role": "cross_validation_primary",
                },
                {
                    "interface": "baostock.query_history_k_data_plus",
                    "validation": "passed",
                    "frame_sha256": "check-hash",
                    "role": "cross_validation_source",
                },
                {
                    "interface": "source_compare_daily_close",
                    "validation": "passed",
                    "frame_sha256": "comparison-hash",
                    "role": "cross_validation_comparison",
                },
            ],
            "data_warnings": [
                {
                    "code": "SOURCE_DISAGREE",
                    "field": "close",
                    "effect": "主源事实不变。",
                }
            ],
            "data_policy": {"ai_may_generate_market_data": False},
        }


def test_adapter_uses_data_core_fund_search_and_preserves_audit(test_config) -> None:
    search_service = FakeFundSearchService()

    def fail_factory():
        raise AssertionError("fund_search should not instantiate the legacy Skill")

    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=fail_factory,
        fund_search_service=search_service,
    )

    envelope = adapter.fund_search(query="示例", limit=5)

    assert envelope.ok
    data = envelope.data
    assert data is not None
    assert data["results"][0]["code"] == "000001"
    assert envelope.data_audit[0]["frame_sha256"] == "data-core-hash"
    assert envelope.data_policy["ai_may_generate_market_data"] is False
    assert search_service.calls == [("示例", 5)]


def test_adapter_reuses_complete_cached_envelope(test_config) -> None:
    search_service = FakeFundSearchService()

    adapter = FundAdvisorToolAdapter(
        test_config,
        fund_search_service=search_service,
    )
    first = adapter.fund_search(query="示例", limit=5)
    second = adapter.fund_search(query="示例", limit=5)

    assert search_service.calls == [("示例", 5)]
    assert first.request_id == second.request_id
    assert second.data_audit == first.data_audit


def test_adapter_uses_data_core_fund_status_and_preserves_audit(test_config) -> None:
    status_service = FakeFundStatusService()

    def fail_factory():
        raise AssertionError("fund_status should not instantiate the legacy Skill")

    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=fail_factory,
        fund_status_service=status_service,
    )

    envelope = adapter.fund_status(fund="000001")

    assert envelope.ok
    data = envelope.data
    assert data is not None
    assert data["availability"]["confirmed"] is True
    assert envelope.data_audit[0]["frame_sha256"] == "status-core-hash"
    assert status_service.calls == ["000001"]


def test_adapter_uses_data_core_market_pulse_and_caches_snapshot(test_config) -> None:
    service = FakeMarketPulseService()
    adapter = FundAdvisorToolAdapter(
        test_config,
        market_pulse_service=service,
    )

    first = adapter.market_pulse()
    second = adapter.market_pulse()

    assert first.ok
    assert second.request_id == first.request_id
    assert second.data_audit[0]["frame_sha256"] == "market-pulse-hash"
    assert service.calls == 1


def test_adapter_exposes_etf_dashboard_with_audit(test_config) -> None:
    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=FakeAdvisor,
        etf_supplement_service=FakeETFSupplementService(),
    )

    envelope = adapter.etf_dashboard(
        fund="510300",
        years=3,
        max_points=600,
    )

    assert envelope.ok
    assert envelope.tool.value == "etf_dashboard"
    data = envelope.data
    assert data is not None
    assert data["summary"]["latest_close"] == 4.801
    assert data["lookback"]["chart_max_points"] == 600
    assert data["recent_rows"][-1]["total_shares_yi_units"] == 120.5
    assert data["recent_rows"][-1]["financing_balance_yi_cny"] == 3.5
    assert (
        data["recent_rows"][-1]["component_financing_balance_yi_cny"]
        == 9800.0
    )
    assert (
        data["recent_rows"][-1][
            "component_financing_balance_change_yi_cny"
        ]
        == 12.5
    )
    assert data["missing_or_not_reliably_available"] == ["净申购赎回金额"]
    assert envelope.data_audit[0]["frame_sha256"] == "source-hash"
    assert envelope.data_audit[1]["frame_sha256"] == "supplement-hash"


def test_adapter_preserves_cross_validation_audit_and_warning(test_config) -> None:
    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=FakeCrossValidationAdvisor,
    )

    envelope = adapter.stock_valuation(
        stock="600519",
        years=3,
        max_points=50,
    )

    assert envelope.ok
    data = envelope.data
    assert data is not None
    assert data["summary"]["stock_price"]["current"] == 100.0
    assert [item["role"] for item in envelope.data_audit] == [
        "cross_validation_primary",
        "cross_validation_source",
        "cross_validation_comparison",
    ]
    warning = envelope.data_warnings[0]
    assert isinstance(warning, dict)
    assert warning["code"] == "SOURCE_DISAGREE"


def test_adapter_timeout_keeps_worker_count_bounded(test_config) -> None:
    concurrency = 2
    mcp_config = test_config.mcp.model_copy(
        update={
            "concurrency": concurrency,
            "timeout_seconds": 0.05,
        }
    )
    config = test_config.model_copy(update={"mcp": mcp_config})
    adapter = FundAdvisorToolAdapter(config, advisor_factory=FakeAdvisor)
    release = Event()
    started_lock = Lock()
    started = 0

    def blocked_call(_unused_advisor):
        nonlocal started
        _ = _unused_advisor
        with started_lock:
            started += 1
        release.wait(timeout=2)
        return {"ok": True}

    try:
        for _ in range(5):
            with pytest.raises(ToolExecutionTimeout):
                adapter._invoke_with_timeout(blocked_call, FakeAdvisor())

        assert started == concurrency
        assert len(adapter._executor._threads) <= concurrency
    finally:
        release.set()
        adapter._executor.shutdown(wait=True, cancel_futures=True)
