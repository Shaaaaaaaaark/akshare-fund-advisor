"""Audited recent ETF share and financing snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, Sequence

import pandas as pd

from fund_advisor_data_core.audit import (
    INTERFACE_CONTRACTS,
    AuditBundle,
    normalize_code,
    optional_float,
    validate_frame,
)
from fund_advisor_data_core.contracts import ETFSupplementData
from fund_advisor_data_core.errors import DataCoreError
from fund_advisor_data_core.providers.akshare import AKShareETFProvider

_SSE_SCALE_INTERFACE = "fund_etf_scale_sse"
_SSE_MARGIN_INTERFACE = "stock_margin_detail_sse"
_SZSE_MARGIN_INTERFACE = "stock_margin_detail_szse"
_SSE_SCALE_URL = "https://www.sse.com.cn/assortment/fund/etf/list/scale/"
_SSE_MARGIN_URL = "https://www.sse.com.cn/market/othersdata/margin/detail/"
_SZSE_MARGIN_URL = "https://www.szse.cn/disclosure/margin/margin/index.html"
_MAX_RECENT_SESSIONS = 7


class ETFMarketProvider(Protocol):
    @property
    def provider_version(self) -> str | None:
        ...

    def etf_scale_sse(self, date: str) -> pd.DataFrame:
        ...

    def margin_detail_sse(self, date: str) -> pd.DataFrame:
        ...

    def margin_detail_szse(self, date: str) -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class ETFSupplementResult:
    data: dict[str, Any]
    sources: list[dict[str, Any]]
    data_audit: list[dict[str, Any]]
    data_warnings: list[dict[str, Any] | str]


class ETFSupplementService:
    """Load a bounded number of exchange snapshots for one exact ETF code."""

    def __init__(self, provider: ETFMarketProvider | None = None) -> None:
        self._provider = provider or AKShareETFProvider()

    def recent(self, code: str, trading_dates: Sequence[str]) -> ETFSupplementResult:
        audit = AuditBundle()
        normalized_code = normalize_code(code)
        dates = sorted(
            {
                parsed
                for value in trading_dates
                if (parsed := _normalize_date(value)) is not None
            }
        )[-_MAX_RECENT_SESSIONS:]

        if len(normalized_code) != 6 or not normalized_code.isdigit():
            raise DataCoreError(
                "INVALID_ARGUMENT",
                "ETF 代码必须是 6 位数字",
                {"fund_code": normalized_code},
            )

        share_rows: list[dict[str, Any]] = []
        if normalized_code.startswith(("5", "6")):
            share_rows = self._load_series(
                audit=audit,
                interface=_SSE_SCALE_INTERFACE,
                upstream="上海证券交易所-ETF 基金规模",
                documentation_url=_SSE_SCALE_URL,
                dates=dates,
                fetch=self._provider.etf_scale_sse,
                code=normalized_code,
                code_column="基金代码",
                value_column="基金份额",
                source_date_column="统计日期",
                fact_name="total_shares",
            )
        else:
            _warn(
                audit,
                "UNSUPPORTED",
                "深交所 ETF 份额接口不返回统计日期，无法通过时效审计",
                "share_history",
                {"fund_code": normalized_code, "interface": "fund_etf_scale_szse"},
            )

        if normalized_code.startswith(("5", "6")):
            margin_interface = _SSE_MARGIN_INTERFACE
            margin_upstream = "上海证券交易所-融资融券明细"
            margin_url = _SSE_MARGIN_URL
            margin_fetch = self._provider.margin_detail_sse
            margin_code_column = "标的证券代码"
        elif normalized_code.startswith(("0", "1", "2", "3")):
            margin_interface = _SZSE_MARGIN_INTERFACE
            margin_upstream = "深圳证券交易所-融资融券交易明细"
            margin_url = _SZSE_MARGIN_URL
            margin_fetch = self._provider.margin_detail_szse
            margin_code_column = "证券代码"
        else:
            margin_interface = ""
            margin_upstream = ""
            margin_url = ""
            margin_fetch = None
            margin_code_column = ""

        financing_rows: list[dict[str, Any]] = []
        if margin_fetch is not None:
            financing_rows = self._load_series(
                audit=audit,
                interface=margin_interface,
                upstream=margin_upstream,
                documentation_url=margin_url,
                dates=dates,
                fetch=margin_fetch,
                code=normalized_code,
                code_column=margin_code_column,
                value_column="融资余额",
                source_date_column=(
                    "信用交易日期" if margin_interface == _SSE_MARGIN_INTERFACE else None
                ),
                fact_name="financing_balance_cny",
            )
        else:
            _warn(
                audit,
                "UNSUPPORTED",
                "当前代码无法映射到沪深交易所融资明细接口",
                "financing_history",
                {"fund_code": normalized_code},
            )

        return self._result(
            normalized_code,
            dates,
            share_rows,
            financing_rows,
            audit,
        )

    def _load_series(
        self,
        *,
        audit: AuditBundle,
        interface: str,
        upstream: str,
        documentation_url: str,
        dates: list[str],
        fetch: Callable[[str], pd.DataFrame],
        code: str,
        code_column: str,
        value_column: str,
        source_date_column: str | None,
        fact_name: str,
    ) -> list[dict[str, Any]]:
        values_by_date: dict[str, float] = {}
        for trading_date in dates:
            frame = self._call(
                audit,
                interface,
                upstream,
                documentation_url,
                fetch,
                trading_date,
            )
            if frame is None:
                continue
            matched = frame[frame[code_column].map(normalize_code).eq(code)]
            if len(matched) != 1:
                _warn(
                    audit,
                    "UNSUPPORTED",
                    f"{interface} 未返回唯一 ETF 记录",
                    fact_name,
                    {
                        "fund_code": code,
                        "date": trading_date,
                        "matched_rows": len(matched),
                    },
                )
                continue
            row = matched.iloc[0]
            if source_date_column is not None:
                source_date = _normalize_date(row.get(source_date_column))
                if source_date != trading_date:
                    _warn(
                        audit,
                        "STALE_DATA",
                        f"{interface} 返回日期与请求交易日不一致",
                        fact_name,
                        {
                            "fund_code": code,
                            "requested_date": trading_date,
                            "source_date": source_date,
                        },
                    )
                    continue
            value = optional_float(row.get(value_column))
            if value is None or value < 0:
                _warn(
                    audit,
                    "DATA_CONTRACT_ERROR",
                    f"{interface} 返回无效数值",
                    fact_name,
                    {
                        "fund_code": code,
                        "date": trading_date,
                        "value_column": value_column,
                    },
                )
                continue
            values_by_date[trading_date] = value

        return _with_changes(dates, values_by_date, fact_name)

    def _call(
        self,
        audit: AuditBundle,
        interface: str,
        upstream: str,
        documentation_url: str,
        fetch: Callable[[str], pd.DataFrame],
        trading_date: str,
    ) -> pd.DataFrame | None:
        provider_date = trading_date.replace("-", "")
        parameters = {"args": [], "kwargs": {"date": provider_date}}
        try:
            frame = validate_frame(
                fetch(provider_date),
                interface,
                required_columns=INTERFACE_CONTRACTS[interface],
            )
        except DataCoreError as exc:
            audit.add_failed_call(interface, parameters, exc)
            _warn(audit, exc.code, exc.message, interface, exc.details)
            return None
        except Exception as exc:
            wrapped = DataCoreError(
                "UPSTREAM_ERROR",
                f"AKShare 接口 {interface} 查询失败，当前无法确认",
                {"interface": interface, "reason": str(exc)},
            )
            audit.add_failed_call(interface, parameters, wrapped)
            _warn(audit, wrapped.code, wrapped.message, interface, wrapped.details)
            return None

        audit.add_source(
            interface,
            upstream,
            provider_version=self._provider.provider_version,
            documentation_url=documentation_url,
        )
        audit.add_passed_frame(
            interface,
            parameters,
            frame,
            required_columns=INTERFACE_CONTRACTS[interface],
        )
        return frame

    @staticmethod
    def _result(
        code: str,
        dates: list[str],
        share_rows: list[dict[str, Any]],
        financing_rows: list[dict[str, Any]],
        audit: AuditBundle,
    ) -> ETFSupplementResult:
        unavailable: list[str] = [
            "净申购赎回金额",
            "成分股融资净新增与历史分位",
            "汇金、证金及关联主体实时持仓",
        ]
        if len(share_rows) < 2:
            unavailable.insert(0, "可审计的 ETF 份额变化")
        else:
            unavailable.insert(0, "ETF 长期份额历史（当前仅最近 7 个交易日）")
        if len(financing_rows) < 2:
            unavailable.insert(1, "可审计的 ETF 融资净新增")
        else:
            unavailable.insert(1, "ETF 融资长期历史分位（当前仅最近 7 个交易日）")

        data = {
            "fund_code": code,
            "requested_trading_dates": dates,
            "share": _series_payload(
                share_rows,
                requested_observations=len(dates),
                value_key="total_shares",
                change_key="total_shares_change",
                value_unit="份",
                scaled_value_key="total_shares_yi_units",
                scaled_change_key="total_shares_change_yi_units",
                scaled_unit="亿份",
            ),
            "financing": _series_payload(
                financing_rows,
                requested_observations=len(dates),
                value_key="financing_balance_cny",
                change_key="financing_balance_change_cny",
                value_unit="元",
                scaled_value_key="financing_balance_yi_cny",
                scaled_change_key="financing_balance_change_yi_cny",
                scaled_unit="亿元",
            ),
            "range_summaries": _range_summaries(
                share_rows,
                financing_rows,
            ),
            "unavailable_metrics": unavailable,
            "data_integrity": {
                "ai_generated_market_data": False,
                "interpolation": "none",
                "forward_fill": "none",
                "coverage": "最近最多 7 个已审计交易日",
            },
        }
        validated = ETFSupplementData.model_validate(data).model_dump(mode="json")
        return ETFSupplementResult(
            data=validated,
            sources=audit.sources,
            data_audit=audit.data_audit,
            data_warnings=audit.data_warnings,
        )


def _series_payload(
    rows: list[dict[str, Any]],
    *,
    requested_observations: int,
    value_key: str,
    change_key: str,
    value_unit: str,
    scaled_value_key: str,
    scaled_change_key: str,
    scaled_unit: str,
) -> dict[str, Any]:
    scaled_series = [
        [row["date"], row[scaled_value_key]]
        for row in rows
        if row.get(scaled_value_key) is not None
    ]
    return {
        "status": (
            "available"
            if len(rows) >= 2 and len(rows) == requested_observations
            else "partial"
            if rows
            else "unavailable"
        ),
        "source_observations": len(rows),
        "actual_start_date": rows[0]["date"] if rows else None,
        "latest_date": rows[-1]["date"] if rows else None,
        "value_field": value_key,
        "change_field": change_key,
        "unit": value_unit,
        "scaled_unit": scaled_unit,
        "latest": rows[-1] if rows else None,
        "rows": rows,
        "chart_series": scaled_series,
        "derived_formulas": {
            scaled_value_key: f"{value_key} / 100000000",
            scaled_change_key: f"{change_key} / 100000000",
            change_key: "当日源值 - 前一相邻审计交易日源值",
        },
    }


def _range_summaries(
    share_rows: list[dict[str, Any]],
    financing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    share_summary = _five_change_summary(
        share_rows,
        "total_shares_change_yi_units",
    )
    financing_summary = _five_change_summary(
        financing_rows,
        "financing_balance_change_yi_cny",
    )
    bounds = (
        share_summary[:2]
        if share_summary is not None
        else financing_summary[:2]
        if financing_summary is not None
        else None
    )
    if bounds is None:
        return []
    start_date, latest_date = bounds
    return [
        {
            "key": "one_week",
            "actual_start_date": start_date,
            "latest_date": latest_date,
            "share_change_yi_units": (
                share_summary[2]
                if share_summary is not None
                and share_summary[:2] == bounds
                else None
            ),
            "financing_net_change_yi_cny": (
                financing_summary[2]
                if financing_summary is not None
                and financing_summary[:2] == bounds
                else None
            ),
        }
    ]


def _five_change_summary(
    rows: list[dict[str, Any]],
    change_key: str,
) -> tuple[str, str, float] | None:
    usable = [row for row in rows if row.get(change_key) is not None]
    if len(usable) < 5:
        return None
    window = usable[-5:]
    return (
        window[0]["date"],
        window[-1]["date"],
        round(sum(row[change_key] for row in window), 4),
    )


def _with_changes(
    dates: list[str],
    values_by_date: dict[str, float],
    fact_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, trading_date in enumerate(dates):
        value = values_by_date.get(trading_date)
        if value is None:
            continue
        previous_date = dates[index - 1] if index > 0 else None
        previous_value = values_by_date.get(previous_date) if previous_date else None
        change = value - previous_value if previous_value is not None else None
        row: dict[str, Any] = {
            "date": trading_date,
            fact_name: value,
            "previous_date": previous_date if previous_value is not None else None,
        }
        if fact_name == "total_shares":
            row["total_shares_yi_units"] = round(value / 100_000_000, 4)
            row["total_shares_change"] = change
            row["total_shares_change_yi_units"] = (
                round(change / 100_000_000, 4) if change is not None else None
            )
        else:
            row["financing_balance_yi_cny"] = round(value / 100_000_000, 4)
            row["financing_balance_change_cny"] = change
            row["financing_balance_change_yi_cny"] = (
                round(change / 100_000_000, 4) if change is not None else None
            )
        rows.append(row)
    return rows


def _normalize_date(value: Any) -> str | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _warn(
    audit: AuditBundle,
    code: str,
    message: str,
    field: str,
    details: dict[str, Any],
) -> None:
    audit.data_warnings.append(
        {
            "code": code,
            "message": message,
            "field": field,
            "effect": "该补充指标保持 unavailable，不影响已审计 ETF 行情主序列。",
            "details": details,
        }
    )
