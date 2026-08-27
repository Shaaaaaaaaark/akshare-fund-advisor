from __future__ import annotations

import pandas as pd

from fund_advisor_data_core.audit import frame_fingerprint
from fund_advisor_data_core.providers.akshare import AKShareFundProvider
from fund_advisor_data_core.services import FundSearchService


def test_fund_search_scores_limits_and_audits_akshare_names() -> None:
    frame = pd.DataFrame(
        [
            {
                "基金代码": "510310",
                "基金简称": "沪深300ETF易方达",
                "基金类型": "指数型-股票",
                "拼音缩写": "HS300ETF",
                "拼音全称": "HUSHENSANBAIETF",
            },
            {
                "基金代码": "510300",
                "基金简称": "沪深300ETF华泰柏瑞",
                "基金类型": "指数型-股票",
                "拼音缩写": "HS300ETFHTBR",
                "拼音全称": "HUSHENSANBAIETFHUATAIBAIRUI",
            },
            {
                "基金代码": 1.0,
                "基金简称": "华夏成长混合",
                "基金类型": "混合型",
                "拼音缩写": "HXCC",
                "拼音全称": "HUAXIACHENGZHANG",
            },
            {
                "基金代码": "001000",
                "基金简称": "中欧沪深增强",
                "基金类型": "混合型",
                "拼音缩写": "ZOHSZQ",
                "拼音全称": "ZHONGOUHUSHENZENGQIANG",
            },
        ]
    )
    service = FundSearchService(AKShareFundProvider(_FakeAkShare(frame)))

    envelope = service.search("沪深", limit=2)
    exact_code = service.search("1", limit=5)

    assert envelope.ok
    assert envelope.tool.value == "fund_search"
    data = envelope.data
    assert data is not None
    assert data["count"] == 2
    assert data["has_more"] is True
    assert [item["code"] for item in data["results"]] == [
        "510300",
        "510310",
    ]
    assert data["guidance"] == "存在多个份额或近似名称时，请使用明确基金代码继续查询。"
    assert envelope.sources[0]["provider"] == "AKShare"
    assert envelope.sources[0]["provider_version"] == "test-akshare"
    assert envelope.data_audit[0]["interface"] == "fund_name_em"
    assert envelope.data_audit[0]["row_count"] == 4
    assert envelope.data_audit[0]["frame_sha256"] == frame_fingerprint(frame)
    assert envelope.data_policy["ai_may_generate_market_data"] is False
    exact_data = exact_code.data
    assert exact_data is not None
    assert exact_data["results"][0]["code"] == "000001"


def test_fund_search_reports_data_contract_error_with_failed_audit() -> None:
    service = FundSearchService(AKShareFundProvider(_FakeAkShare(pd.DataFrame())))

    envelope = service.search("沪深", limit=5)

    assert envelope.ok is False
    assert envelope.data is None
    assert envelope.error is not None
    assert envelope.error.code == "DATA_CONTRACT_ERROR"
    assert envelope.data_audit[0]["validation"] == "failed"
    assert envelope.data_audit[0]["error"]["code"] == "DATA_CONTRACT_ERROR"
    assert envelope.data_policy["ai_may_generate_market_data"] is False


class _FakeAkShare:
    __version__ = "test-akshare"

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def fund_name_em(self) -> pd.DataFrame:
        return self._frame
