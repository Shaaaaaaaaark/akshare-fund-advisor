from __future__ import annotations

import pandas as pd

from fund_advisor_data_core.audit import frame_fingerprint
from fund_advisor_data_core.providers.akshare import AKShareMarketProvider
from fund_advisor_data_core.services import MarketPulseService


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "序号": 2,
                "板块": "银行",
                "涨跌幅": 1.38,
                "总成交量": 2036.29,
                "总成交额": 160.37,
                "净流入": 30.81,
                "上涨家数": 42,
                "下跌家数": 0,
                "均价": 7.88,
                "领涨股": "宁波银行",
                "领涨股-最新价": 35.84,
                "领涨股-涨跌幅": 3.4,
            },
            {
                "序号": 1,
                "板块": "元件",
                "涨跌幅": 2.16,
                "总成交量": 1463.6,
                "总成交额": 725.26,
                "净流入": 28.21,
                "上涨家数": 41,
                "下跌家数": 22,
                "均价": 49.55,
                "领涨股": "逸豪新材",
                "领涨股-最新价": 58.8,
                "领涨股-涨跌幅": 20.0,
            },
            {
                "序号": 3,
                "板块": "房地产服务",
                "涨跌幅": -0.5,
                "总成交量": 100.0,
                "总成交额": 20.0,
                "净流入": -1.0,
                "上涨家数": 2,
                "下跌家数": 8,
                "均价": 5.0,
                "领涨股": "示例公司",
                "领涨股-最新价": 10.0,
                "领涨股-涨跌幅": 1.0,
            },
        ]
    )


class _FakeAkShare:
    __version__ = "1.18.64"

    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def stock_board_industry_summary_ths(self) -> pd.DataFrame:
        return self._frame


def _service(frame: pd.DataFrame) -> MarketPulseService:
    return MarketPulseService(AKShareMarketProvider(_FakeAkShare(frame)))


def test_market_pulse_sorts_sectors_and_builds_stable_poll_topics() -> None:
    frame = _frame()

    envelope = _service(frame).pulse()

    assert envelope.ok
    assert envelope.tool.value == "market_pulse"
    assert envelope.sources[0]["interface"] == "stock_board_industry_summary_ths"
    assert envelope.data_audit[0]["frame_sha256"] == frame_fingerprint(frame)
    assert envelope.data is not None
    sectors = envelope.data["sectors"]
    assert [sector["name"] for sector in sectors] == [
        "元件",
        "银行",
        "房地产服务",
    ]
    assert sectors[0] == {
        "name": "元件",
        "change_pct": 2.16,
        "rising_count": 41,
        "falling_count": 22,
        "leading_stock": "逸豪新材",
        "leading_stock_change_pct": 20.0,
        "rank": 1,
    }
    topics = envelope.data["poll_topics"]
    assert len(topics) == 3
    assert topics[0]["key"].startswith("sector_")
    assert topics[0]["question"] == "元件板块今日能否延续强势？"
    assert topics[2]["question"] == "房地产服务板块今日能否率先修复？"


def test_market_pulse_rejects_rows_without_usable_change() -> None:
    frame = _frame()
    frame["涨跌幅"] = None

    envelope = _service(frame).pulse()

    assert envelope.ok is False
    assert envelope.error is not None
    assert envelope.error.code == "DATA_CONTRACT_ERROR"


def test_market_pulse_normalizes_upstream_failure() -> None:
    class _FailingAkShare:
        __version__ = "1.18.64"

        def stock_board_industry_summary_ths(self) -> pd.DataFrame:
            raise RuntimeError("upstream disconnected")

    envelope = MarketPulseService(AKShareMarketProvider(_FailingAkShare())).pulse()

    assert envelope.ok is False
    assert envelope.error is not None
    assert envelope.error.code == "DATA_SOURCE_ERROR"
    assert envelope.error.retryable is True
    assert envelope.data_audit[0]["validation"] == "failed"
