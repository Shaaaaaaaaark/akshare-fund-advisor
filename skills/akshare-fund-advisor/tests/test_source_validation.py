import importlib.util
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "fund_advisor.py"
SPEC = importlib.util.spec_from_file_location("fund_advisor_source_test", SCRIPT_PATH)
fund_advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fund_advisor)
source_validation = fund_advisor.source_validation
SHANGHAI = ZoneInfo("Asia/Shanghai")


def market_now():
    """测试基准时钟：取运行当下的上海时间，与生产时效校验保持同一口径。"""
    return datetime.now(SHANGHAI)


def recent_trading_dates(periods):
    """以运行当天为锚点回推的交易日序列。

    生产代码用「当前真实时间」判定时效（窗口约 10 天），夹具日期一旦写死
    就只能在写下后的十天内通过。这里改为动态回推：序列最后一日恒为不晚于
    今天的最近一个工作日（周末最多回退 2 天），既稳定落在时效窗口内，也不
    会出现未来日期导致的负数 age。
    """
    return pd.bdate_range(end=market_now().date(), periods=periods)


def slow_provider(delay):
    time.sleep(delay)
    return {"completed": True}


def canonical_prices(
    values,
    *,
    end="2026-08-14",
    adjustment="none",
    code="600519",
):
    dates = pd.bdate_range(end=end, periods=len(values))
    return pd.DataFrame(
        {
            "date": dates,
            "code": [code] * len(values),
            "close": values,
            "volume": [1000] * len(values),
            "amount": [100000.0] * len(values),
            "adjustment": [adjustment] * len(values),
        }
    )


def make_stock_advisor(ak, now=None):
    advisor = fund_advisor.FundAdvisor.__new__(fund_advisor.FundAdvisor)
    advisor.ak = ak
    advisor.now = now or market_now()
    advisor.timeout_seconds = 1
    advisor.source_validation_sources = ("baostock",)
    advisor.sources = []
    advisor.data_warnings = []
    advisor.data_audit = []
    advisor._stock_names_frame = None
    return advisor


def test_compare_daily_close_agrees_without_warning():
    primary = canonical_prices([10.0, 10.1, 10.2, 10.3, 10.4])
    check = canonical_prices([10.0, 10.1, 10.2, 10.3, 10.4])

    comparison, warnings, summary = source_validation.compare_daily_close(
        primary,
        check,
        entity="600519",
        primary_source="akshare",
        check_source="baostock",
        metric_basis="none_daily_close",
    )

    assert len(comparison) == 5
    assert warnings == []
    assert summary["mismatch_observations"] == 0
    assert summary["interpolation"] == "none"


def test_provider_frame_exposes_audit_metadata():
    frame = canonical_prices([10.0, 10.1])

    result = source_validation.ProviderFrame(
        source_name="fixture",
        provider_version="1.0",
        interface="fixture.daily",
        upstream="fixture",
        documentation_url="https://example.com",
        parameters={"code": "600519"},
        metric_basis="none_daily_close",
        frame=frame,
    )

    assert result.columns == tuple(frame.columns)
    assert result.as_of == "2026-08-14"
    assert len(result.frame_sha256) == 64


def test_compare_daily_close_reports_difference_without_mutating_primary():
    primary = canonical_prices([10.0, 10.1, 10.2, 10.3, 10.4])
    original = primary.copy(deep=True)
    check = canonical_prices([10.0, 10.1, 10.2, 10.3, 11.0])

    _, warnings, summary = source_validation.compare_daily_close(
        primary,
        check,
        entity="600519",
        primary_source="akshare",
        check_source="baostock",
        metric_basis="none_daily_close",
    )

    pd.testing.assert_frame_equal(primary, original)
    assert warnings[0]["code"] == "SOURCE_DISAGREE"
    assert warnings[0]["mismatch_observations"] == 1
    assert summary["mismatch_observations"] == 1


def test_compare_daily_close_rejects_different_adjustment_basis():
    primary = canonical_prices([10.0] * 5, adjustment="none")
    check = canonical_prices([10.0] * 5, adjustment="forward")

    comparison, warnings, summary = source_validation.compare_daily_close(
        primary,
        check,
        entity="600519",
        primary_source="akshare",
        check_source="baostock",
        metric_basis="daily_close",
    )

    assert comparison.empty
    assert warnings[0]["code"] == "SOURCE_BASIS_MISMATCH"
    assert summary == {"comparable": False}


def test_compare_daily_close_reports_stale_and_insufficient_overlap():
    primary = canonical_prices([10.0] * 5, end="2026-08-14")
    check = canonical_prices([10.0] * 2, end="2026-08-07")

    comparison, warnings, summary = source_validation.compare_daily_close(
        primary,
        check,
        entity="600519",
        primary_source="akshare",
        check_source="baostock",
        metric_basis="none_daily_close",
    )

    assert comparison.empty
    assert {warning["code"] for warning in warnings} == {
        "SOURCE_STALE",
        "SOURCE_UNAVAILABLE",
    }
    assert summary["overlap_observations"] == 0


def test_compare_daily_close_rejects_schema_drift():
    primary = canonical_prices([10.0] * 5)
    check = canonical_prices([10.0] * 5).drop(columns=["amount"])

    with pytest.raises(
        source_validation.SourceValidationError,
        match="缺少已审计字段",
    ) as captured:
        source_validation.compare_daily_close(
            primary,
            check,
            entity="600519",
            primary_source="akshare",
            check_source="baostock",
            metric_basis="none_daily_close",
        )

    assert captured.value.code == "SOURCE_SCHEMA_CHANGED"


def test_isolated_provider_timeout_returns_bounded_failure():
    started = time.monotonic()

    with pytest.raises(
        source_validation.SourceValidationError,
        match="已终止校验进程",
    ) as captured:
        source_validation._run_isolated(
            slow_provider,
            {"delay": 5},
            timeout_seconds=1,
            interface="fixture.slow",
        )

    assert captured.value.code == "SOURCE_UNAVAILABLE"
    assert time.monotonic() - started < 4


def test_source_validation_timeout_is_bounded_by_tool_budget():
    assert fund_advisor.configured_source_validation_timeout(60, "") == 10

    with pytest.raises(fund_advisor.AdvisorError) as captured:
        fund_advisor.configured_source_validation_timeout(60, "21")

    assert captured.value.code == "INVALID_ARGUMENT"


def test_stock_valuation_keeps_primary_price_when_baostock_disagrees():
    dates = recent_trading_dates(120)
    pe = pd.DataFrame({"date": dates, "value": [15.0] * 120})
    pb = pd.DataFrame({"date": dates, "value": [1.5] * 120})
    qfq = pd.DataFrame(
        {
            "date": dates,
            "open": [1200.0] * 120,
            "high": [1210.0] * 120,
            "low": [1190.0] * 120,
            "close": [1200.0 + item for item in range(120)],
            "volume": [100000] * 120,
        }
    )
    unadjusted = pd.DataFrame(
        {
            "date": dates,
            "open": [100.0] * 120,
            "high": [101.0] * 120,
            "low": [99.0] * 120,
            "close": [100.0 + item / 10 for item in range(120)],
            "volume": [100000] * 120,
            "amount": [1000000.0] * 120,
        }
    )

    class FakeAK:
        __version__ = "1.18.64"

        @staticmethod
        def stock_info_a_code_name():
            return pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})

        @staticmethod
        def stock_zh_valuation_baidu(**kwargs):
            return pe if kwargs["indicator"] == "市盈率(TTM)" else pb

        @staticmethod
        def stock_zh_a_daily(**kwargs):
            return qfq if kwargs["adjust"] == "qfq" else unadjusted

    check_frame = canonical_prices(
        [value + 1.0 for value in unadjusted["close"]],
        end=dates[-1],
    )
    provider_result = source_validation.ProviderFrame(
        source_name="Baostock",
        provider_version="0.9.3",
        interface="baostock.query_history_k_data_plus",
        upstream="Baostock 自有数据服务",
        documentation_url=source_validation.BAOSTOCK_DOC,
        parameters={"code": "sh.600519"},
        metric_basis="none_daily_close",
        frame=check_frame,
    )
    advisor = make_stock_advisor(FakeAK())

    with patch.object(
        source_validation.BaostockProvider,
        "fetch_stock_daily",
        return_value=provider_result,
    ):
        result = advisor.stock_valuation("600519", years=3, max_points=50)

    assert result["summary"]["stock_price"]["current"] == 1319.0
    assert any(
        warning.get("code") == "SOURCE_DISAGREE"
        for warning in advisor.data_warnings
    )
    assert {
        item.get("role")
        for item in advisor.data_audit
        if item.get("role")
    } >= {
        "cross_validation_primary",
        "cross_validation_source",
        "cross_validation_comparison",
    }


def test_stock_valuation_survives_validation_source_failure():
    dates = recent_trading_dates(120)
    metric = pd.DataFrame({"date": dates, "value": [15.0] * 120})
    prices = pd.DataFrame(
        {
            "date": dates,
            "open": [10.0] * 120,
            "high": [10.0] * 120,
            "low": [10.0] * 120,
            "close": [10.0] * 120,
            "volume": [1000] * 120,
        }
    )

    class FakeAK:
        __version__ = "1.18.64"

        @staticmethod
        def stock_info_a_code_name():
            return pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})

        @staticmethod
        def stock_zh_valuation_baidu(**_kwargs):
            return metric

        @staticmethod
        def stock_zh_a_daily(**_kwargs):
            return prices

    advisor = make_stock_advisor(FakeAK())
    failure = source_validation.SourceValidationError(
        "SOURCE_UNAVAILABLE",
        "校验源不可用",
    )
    with patch.object(
        source_validation.BaostockProvider,
        "fetch_stock_daily",
        side_effect=failure,
    ):
        result = advisor.stock_valuation("600519", years=3, max_points=50)

    assert result["ok"] is True
    assert any(
        warning.get("code") == "SOURCE_UNAVAILABLE"
        for warning in advisor.data_warnings
    )
