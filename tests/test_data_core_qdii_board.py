from __future__ import annotations

import pandas as pd

from fund_advisor_data_core.audit import frame_fingerprint
from fund_advisor_data_core.providers.akshare import AKShareFundProvider
from fund_advisor_data_core.services import QDIIPurchaseBoardService


class _FakeAkShare:
    __version__ = "test-akshare"

    def __init__(self, purchases: pd.DataFrame) -> None:
        self._purchases = purchases

    def fund_purchase_em(self) -> pd.DataFrame:
        return self._purchases


def _record(
    code: str,
    name: str,
    fund_type: str,
    status: str,
    limit: float,
    report_date: str = "2026-08-31",
) -> dict[str, object]:
    return {
        "基金代码": code,
        "基金简称": name,
        "基金类型": fund_type,
        "最新净值/万份收益": 1.5,
        "最新净值/万份收益-报告时间": report_date,
        "申购状态": status,
        "赎回状态": "开放赎回",
        "下一开放日": "",
        "购买起点": 10,
        "日累计限定金额": limit,
        "手续费": 0.12,
    }


def _service(purchases: pd.DataFrame) -> QDIIPurchaseBoardService:
    return QDIIPurchaseBoardService(AKShareFundProvider(_FakeAkShare(purchases)))


def test_board_keeps_only_overseas_limited_and_suspended() -> None:
    purchases = pd.DataFrame(
        [
            _record("000834", "大成纳斯达克100ETF联接(QDII)A", "指数型-海外股票", "限大额", 10_000.0),
            _record("003718", "易方达标普500指数美元汇A", "指数型-海外股票", "暂停申购", 0.01),
            _record("510300", "沪深300ETF", "指数型-股票", "限大额", 5_000.0),  # 境内，排除
            _record("000001", "华夏成长混合", "混合型-偏股", "开放申购", 0.0),  # 非限额，排除
        ]
    )

    envelope = _service(purchases).board()

    assert envelope.ok
    assert envelope.tool.value == "qdii_purchase_board"
    assert envelope.sources[0]["interface"] == "fund_purchase_em"
    assert [item["frame_sha256"] for item in envelope.data_audit] == [
        frame_fingerprint(purchases),
    ]
    data = envelope.data
    assert data is not None
    assert data["summary"] == {
        "limited_large_count": 1,
        "limited_large_amount_disclosed_count": 1,
        "suspended_count": 1,
        "category_count": 2,
    }
    codes = {
        entry["code"]
        for tier in data["tiers"].values()
        for entry in tier["funds"]
    }
    assert codes == {"000834", "003718"}


def test_board_splits_tiers_and_suppresses_suspended_limit() -> None:
    purchases = pd.DataFrame(
        [
            _record("A00001", "华宝纳斯达克科技QDII", "QDII-被动指数型", "限大额", 20_000.0),
            _record("A00002", "易方达标普500(QDII)", "指数型-海外股票", "暂停申购", 0.01),
        ]
    )

    data = _service(purchases).board().data
    assert data is not None

    limited = data["tiers"]["limited_large"]["funds"]
    suspended = data["tiers"]["suspended"]["funds"]
    assert len(limited) == 1 and len(suspended) == 1
    # 限大额保留真实限额。
    assert limited[0]["effective_daily_limit_cny"] == 20_000.0
    assert limited[0]["status_tier"] == "limited_large"
    # 暂停申购不给有效金额，脏值不上榜为门槛。
    assert suspended[0]["effective_daily_limit_cny"] is None
    assert suspended[0]["source_daily_limit_cny"] == 0.01
    assert suspended[0]["status_tier"] == "suspended"


def test_board_sorts_by_limit_with_placeholder_last() -> None:
    purchases = pd.DataFrame(
        [
            _record("P00001", "纳指QDII无限额占位", "QDII-被动指数型", "限大额", 9_999_999_999.0),
            _record("P00002", "纳指QDII小额限购", "QDII-被动指数型", "限大额", 1_000.0),
            _record("P00003", "纳指QDII中额限购", "QDII-被动指数型", "限大额", 50_000.0),
        ]
    )

    data = _service(purchases).board().data
    assert data is not None
    funds = data["tiers"]["limited_large"]["funds"]
    assert [item["code"] for item in funds] == ["P00002", "P00003", "P00001"]
    # 占位值置空且标记，不当作 100 亿真实限额。
    placeholder = funds[-1]
    assert placeholder["effective_daily_limit_cny"] is None
    assert placeholder["no_effective_limit_placeholder"] is True
    assert placeholder["source_daily_limit_cny"] == 9_999_999_999.0


def test_board_groups_by_theme() -> None:
    purchases = pd.DataFrame(
        [
            _record("T00001", "大成纳斯达克100ETF联接(QDII)A", "指数型-海外股票", "限大额", 10_000.0),
            _record("T00002", "易方达标普500指数(QDII)", "指数型-海外股票", "限大额", 20_000.0),
            _record("T00003", "华宝油气QDII", "QDII-被动指数型", "暂停申购", 0.0),
        ]
    )

    data = _service(purchases).board().data
    assert data is not None
    themes = {category["theme"]: category for category in data["categories"]}
    assert "纳斯达克100" in themes
    assert "标普500" in themes
    assert "黄金/商品" in themes
    assert themes["纳斯达克100"]["limited_large_count"] == 1
    assert themes["黄金/商品"]["suspended_count"] == 1


def test_limited_large_with_zero_limit_is_undisclosed_not_zero_threshold() -> None:
    purchases = pd.DataFrame(
        [
            _record("Z00001", "广发纳斯达克100ETF联接美元(QDII)A", "指数型-海外股票", "限大额", 0.0),
        ]
    )

    data = _service(purchases).board().data
    assert data is not None
    entry = data["tiers"]["limited_large"]["funds"][0]
    assert entry["subscription_status"] == "限大额"
    assert entry["effective_daily_limit_cny"] is None
    assert entry["amount_disclosed"] is False
    assert entry["source_daily_limit_cny"] == 0.0
    assert data["summary"]["limited_large_amount_disclosed_count"] == 0


def test_board_upstream_failure_returns_error_envelope() -> None:
    class _FailingAkShare:
        __version__ = "test-akshare"

        def fund_purchase_em(self) -> pd.DataFrame:
            raise RuntimeError("upstream down")

    service = QDIIPurchaseBoardService(AKShareFundProvider(_FailingAkShare()))

    envelope = service.board()

    assert envelope.ok is False
    assert envelope.data is None
    assert envelope.error is not None
    assert envelope.error.code == "DATA_SOURCE_ERROR"
    assert envelope.error.retryable is True
    assert envelope.data_audit[0]["validation"] == "failed"


def test_board_reports_only_latest_date_but_keeps_all_current_funds() -> None:
    purchases = pd.DataFrame(
        [
            _record(
                "L00001", "早报告日纳指QDII", "QDII-被动指数型", "限大额", 1_000.0,
                report_date="2026-08-27",
            ),
            _record(
                "L00002", "最新报告日纳指QDII", "QDII-被动指数型", "限大额", 2_000.0,
                report_date="2026-09-01",
            ),
        ]
    )

    data = _service(purchases).board().data
    assert data is not None
    # 表头只显示最新日期。
    assert data["latest_source_report_date"] == "2026-09-01"
    assert data["source_report_date_span"] == {
        "earliest": "2026-08-27",
        "latest": "2026-09-01",
    }
    # 但不因报告日较早而剔除基金：两只都在榜。
    assert data["summary"]["limited_large_count"] == 2
    funds = data["tiers"]["limited_large"]["funds"]
    assert {f["code"] for f in funds} == {"L00001", "L00002"}
    # 每只基金仍保留各自报告日可审计。
    by_code = {f["code"]: f["source_report_date"] for f in funds}
    assert by_code["L00001"] == "2026-08-27"
    assert by_code["L00002"] == "2026-09-01"
