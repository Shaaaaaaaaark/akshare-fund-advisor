from __future__ import annotations

import pandas as pd

from fund_advisor_data_core.services import ETFSupplementService

DATES = [
    "2026-08-20",
    "2026-08-21",
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
    "2026-08-27",
]


class FakeETFProvider:
    provider_version = "1.18.64"

    def etf_scale_sse(self, date: str) -> pd.DataFrame:
        index = DATES.index(_display_date(date))
        return pd.DataFrame(
            [
                {
                    "序号": 1,
                    "基金代码": "510310",
                    "基金简称": "HS300ETF",
                    "ETF类型": "跨市",
                    "统计日期": _display_date(date),
                    "基金份额": 10_000_000_000 + index * 100_000_000,
                }
            ]
        )

    def margin_detail_sse(self, date: str) -> pd.DataFrame:
        index = DATES.index(_display_date(date))
        return pd.DataFrame(
            [
                {
                    "信用交易日期": date.replace("-", ""),
                    "标的证券代码": "510310",
                    "标的证券简称": "HS300ETF",
                    "融资余额": 200_000_000 + index * 10_000_000,
                    "融资买入额": 20_000_000,
                    "融资偿还额": 10_000_000,
                    "融券余量": 100,
                    "融券卖出量": 10,
                    "融券偿还量": 5,
                },
                {
                    "信用交易日期": date.replace("-", ""),
                    "标的证券代码": "600000",
                    "标的证券简称": "浦发银行",
                    "融资余额": 1_000_000_000 + index * 100_000_000,
                    "融资买入额": 20_000_000,
                    "融资偿还额": 10_000_000,
                    "融券余量": 100,
                    "融券卖出量": 10,
                    "融券偿还量": 5,
                },
            ]
        )

    def margin_detail_szse(self, date: str) -> pd.DataFrame:
        index = DATES.index(_display_date(date))
        return pd.DataFrame(
            [
                {
                    "证券代码": "159919",
                    "证券简称": "沪深300ETF嘉实",
                    "融资买入额": 20_000_000,
                    "融资余额": 300_000_000 + index * 10_000_000,
                    "融券卖出量": 10,
                    "融券余量": 100,
                    "融券余额": 1_000,
                    "融资融券余额": 301_000_000,
                },
                {
                    "证券代码": "000001",
                    "证券简称": "平安银行",
                    "融资买入额": 20_000_000,
                    "融资余额": 2_000_000_000 + index * 200_000_000,
                    "融券卖出量": 10,
                    "融券余量": 100,
                    "融券余额": 1_000,
                    "融资融券余额": 2_001_000_000,
                },
            ]
        )

    def index_constituents(self, symbol: str) -> pd.DataFrame:
        assert symbol == "000300"
        return pd.DataFrame(
            [
                {
                    "日期": DATES[-1],
                    "指数代码": "000300",
                    "指数名称": "沪深300",
                    "成分券代码": "600000",
                    "成分券名称": "浦发银行",
                    "交易所": "上海证券交易所",
                },
                {
                    "日期": DATES[-1],
                    "指数代码": "000300",
                    "指数名称": "沪深300",
                    "成分券代码": "000001",
                    "成分券名称": "平安银行",
                    "交易所": "深圳证券交易所",
                },
            ]
        )


def test_sse_supplement_audits_recent_share_and_financing_series() -> None:
    result = ETFSupplementService(FakeETFProvider()).recent("510310", DATES)

    share = result.data["share"]
    financing = result.data["financing"]
    assert share["status"] == "available"
    assert share["source_observations"] == 6
    assert share["latest"]["total_shares_yi_units"] == 105.0
    assert share["latest"]["total_shares_change_yi_units"] == 1.0
    assert financing["status"] == "available"
    assert financing["latest"]["financing_balance_yi_cny"] == 2.5
    assert financing["latest"]["financing_balance_change_yi_cny"] == 0.1
    assert result.data["range_summaries"] == [
        {
            "key": "one_week",
            "actual_start_date": "2026-08-21",
            "latest_date": "2026-08-27",
            "share_change_yi_units": 5.0,
            "financing_net_change_yi_cny": 0.5,
            "component_financing_net_change_yi_cny": None,
        }
    ]
    assert len(result.data_audit) == 12
    assert all(item["validation"] == "passed" for item in result.data_audit)
    assert all(item["frame_sha256"] for item in result.data_audit)


def test_szse_share_stays_unavailable_without_auditable_snapshot_date() -> None:
    result = ETFSupplementService(FakeETFProvider()).recent("159919", DATES)

    assert result.data["share"]["status"] == "unavailable"
    assert result.data["financing"]["status"] == "available"
    assert any(
        isinstance(warning, dict)
        and warning["code"] == "UNSUPPORTED"
        and warning["field"] == "share_history"
        for warning in result.data_warnings
    )
    assert {
        item["interface"]
        for item in result.data_audit
        if item["validation"] == "passed"
    } == {"stock_margin_detail_szse"}


def test_component_financing_uses_exact_index_constituents_and_both_exchanges() -> None:
    result = ETFSupplementService(FakeETFProvider()).recent(
        "510310",
        DATES,
        tracking_index={"name": "沪深300", "index_code": "000300"},
    )

    component = result.data["component_financing"]
    assert component["status"] == "available"
    assert component["tracking_index_name"] == "沪深300"
    assert component["tracking_index_code"] == "000300"
    assert component["constituent_as_of"] == DATES[-1]
    assert component["constituent_count"] == 2
    assert component["latest"]["financing_balance_yi_cny"] == 45.0
    assert component["latest"]["financing_balance_change_yi_cny"] == 3.0
    assert component["latest"]["reported_component_count"] == 2
    assert component["latest"]["coverage_pct"] == 100.0
    assert result.data["range_summaries"][0][
        "component_financing_net_change_yi_cny"
    ] == 15.0
    assert len(result.data_audit) == 19
    assert {
        item["interface"]
        for item in result.data_audit
        if item["validation"] == "passed"
    } == {
        "fund_etf_scale_sse",
        "index_stock_cons_csindex",
        "stock_margin_detail_sse",
        "stock_margin_detail_szse",
    }


def test_component_financing_is_partial_when_exchange_rows_miss_constituents() -> None:
    class PartialProvider(FakeETFProvider):
        def margin_detail_szse(self, date: str) -> pd.DataFrame:
            frame = super().margin_detail_szse(date)
            return frame[frame["证券代码"].ne("000001")]

    result = ETFSupplementService(PartialProvider()).recent(
        "510310",
        DATES,
        tracking_index={"name": "沪深300", "index_code": "000300"},
    )

    component = result.data["component_financing"]
    assert component["status"] == "partial"
    assert component["latest"]["reported_component_count"] == 1
    assert component["latest"]["coverage_pct"] == 50.0
    assert component["latest"]["financing_balance_change_yi_cny"] is None
    assert any(
        isinstance(warning, dict)
        and warning["code"] == "PARTIAL_DATA"
        and warning["field"] == "component_financing_history"
        for warning in result.data_warnings
    )


def _display_date(value: str) -> str:
    if "-" in value:
        return value
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"
