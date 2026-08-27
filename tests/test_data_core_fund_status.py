from __future__ import annotations

import pandas as pd

from fund_advisor_data_core.audit import frame_fingerprint
from fund_advisor_data_core.providers.akshare import AKShareFundProvider
from fund_advisor_data_core.services import FundStatusService


def test_fund_status_reads_purchase_status_with_audit() -> None:
    names = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "华夏成长混合",
                "基金类型": "混合型",
                "拼音缩写": "HXCC",
                "拼音全称": "HUAXIACHENGZHANG",
            }
        ]
    )
    purchases = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "华夏成长混合",
                "基金类型": "混合型",
                "最新净值/万份收益": 1.23456,
                "最新净值/万份收益-报告时间": "2026-08-19",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "下一开放日": "2026-08-20",
                "购买起点": 10,
                "日累计限定金额": 10_000_000_000,
                "手续费": 0.15,
            }
        ]
    )
    service = FundStatusService(AKShareFundProvider(_FakeAkShare(names, purchases)))

    envelope = service.status("1")

    assert envelope.ok
    assert envelope.tool.value == "fund_status"
    assert envelope.sources == [
        {
            "provider": "AKShare",
            "provider_version": "test-akshare",
            "interface": "fund_name_em",
            "upstream": "东方财富-基金基本信息",
            "documentation_url": "https://akshare.akfamily.xyz/data/fund/fund_public.html",
        },
        {
            "provider": "AKShare",
            "provider_version": "test-akshare",
            "interface": "fund_purchase_em",
            "upstream": "东方财富-基金申购状态",
            "documentation_url": "https://akshare.akfamily.xyz/data/fund/fund_public.html",
        },
    ]
    assert [item["frame_sha256"] for item in envelope.data_audit] == [
        frame_fingerprint(names),
        frame_fingerprint(purchases),
    ]
    data = envelope.data
    assert data is not None
    assert data["fund"]["code"] == "000001"
    availability = data["availability"]
    assert availability["confirmed"] is True
    assert availability["mode"] == "off_exchange"
    assert availability["latest_nav_or_income"] == 1.2346
    off_exchange = availability["off_exchange"]
    assert off_exchange["can_submit_subscription"] is True
    assert off_exchange["can_submit_redemption"] is True
    assert off_exchange["daily_limit_cny"] is None
    assert off_exchange["source_daily_limit_cny"] == 10_000_000_000
    assert envelope.data_policy["ai_may_generate_market_data"] is False


def test_fund_status_returns_error_when_purchase_row_missing() -> None:
    names = pd.DataFrame(
        [
            {
                "基金代码": "000001",
                "基金简称": "华夏成长混合",
                "基金类型": "混合型",
                "拼音缩写": "HXCC",
                "拼音全称": "HUAXIACHENGZHANG",
            }
        ]
    )
    purchases = pd.DataFrame(
        [
            {
                "基金代码": "000002",
                "基金简称": "示例基金",
                "基金类型": "混合型",
                "最新净值/万份收益": 1.0,
                "最新净值/万份收益-报告时间": "2026-08-19",
                "申购状态": "开放申购",
                "赎回状态": "开放赎回",
                "下一开放日": "2026-08-20",
                "购买起点": 10,
                "日累计限定金额": 1000,
                "手续费": 0.15,
            }
        ]
    )
    service = FundStatusService(AKShareFundProvider(_FakeAkShare(names, purchases)))

    envelope = service.status("000001")

    assert envelope.ok is False
    assert envelope.data is None
    assert envelope.error is not None
    assert envelope.error.code == "STATUS_NOT_FOUND"
    assert [item["validation"] for item in envelope.data_audit] == [
        "passed",
        "passed",
    ]


class _FakeAkShare:
    __version__ = "test-akshare"

    def __init__(self, names: pd.DataFrame, purchases: pd.DataFrame) -> None:
        self._names = names
        self._purchases = purchases

    def fund_name_em(self) -> pd.DataFrame:
        return self._names

    def fund_purchase_em(self) -> pd.DataFrame:
        return self._purchases
