from datetime import datetime
from threading import Event, Lock
from threading import enumerate as enumerate_threads
from zoneinfo import ZoneInfo

import pytest

from fund_advisor_mcp.fund.adapter import (
    FundAdvisorToolAdapter,
    ToolExecutionTimeout,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeAdvisor:
    def search(self, query, limit):
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
            "lookback": {
                "requested_years": years,
                "chart_max_points": max_points,
            },
            "summary": {"latest_close": 4.801},
        }

    def common_output(self):
        return {
            "queried_at": datetime.now(SHANGHAI),
            "sources": [{"provider": "AKShare", "interface": "fund_name_em"}],
            "data_audit": [
                {
                    "interface": "fund_name_em",
                    "validation": "passed",
                    "frame_sha256": "source-hash",
                }
            ],
            "data_warnings": [],
            "data_policy": {"ai_may_generate_market_data": False},
        }


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


def test_adapter_preserves_skill_data_and_audit(test_config) -> None:
    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=FakeAdvisor,
    )

    envelope = adapter.fund_search(query="示例", limit=5)

    assert envelope.ok
    assert envelope.data["results"][0]["code"] == "000001"
    assert envelope.data_audit[0]["frame_sha256"] == "source-hash"
    assert envelope.data_policy["ai_may_generate_market_data"] is False


def test_adapter_reuses_complete_cached_envelope(test_config) -> None:
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return FakeAdvisor()

    adapter = FundAdvisorToolAdapter(test_config, advisor_factory=factory)
    first = adapter.fund_search(query="示例", limit=5)
    second = adapter.fund_search(query="示例", limit=5)

    assert calls == 1
    assert first.request_id == second.request_id
    assert second.data_audit == first.data_audit


def test_adapter_exposes_etf_dashboard_with_audit(test_config) -> None:
    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=FakeAdvisor,
    )

    envelope = adapter.etf_dashboard(
        fund="510300",
        years=3,
        max_points=600,
    )

    assert envelope.ok
    assert envelope.tool.value == "etf_dashboard"
    assert envelope.data["summary"]["latest_close"] == 4.801
    assert envelope.data["lookback"]["chart_max_points"] == 600
    assert envelope.data_audit[0]["frame_sha256"] == "source-hash"


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
    assert envelope.data["summary"]["stock_price"]["current"] == 100.0
    assert [item["role"] for item in envelope.data_audit] == [
        "cross_validation_primary",
        "cross_validation_source",
        "cross_validation_comparison",
    ]
    assert envelope.data_warnings[0]["code"] == "SOURCE_DISAGREE"


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

    def blocked_call(_advisor):
        nonlocal started
        with started_lock:
            started += 1
        release.wait(timeout=2)
        return {"ok": True}

    try:
        for _ in range(5):
            with pytest.raises(ToolExecutionTimeout):
                adapter._invoke_with_timeout(blocked_call, FakeAdvisor())

        workers = [
            thread
            for thread in enumerate_threads()
            if thread.name.startswith("fund-advisor-tool")
        ]
        assert started == concurrency
        assert len(workers) <= concurrency
    finally:
        release.set()
        adapter._executor.shutdown(wait=True, cancel_futures=True)
