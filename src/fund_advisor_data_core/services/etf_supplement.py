"""Audited recent ETF share and financing snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

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
_CSI_CONSTITUENTS_INTERFACE = "index_stock_cons_csindex"
_SSE_SCALE_URL = "https://www.sse.com.cn/assortment/fund/etf/list/scale/"
_SSE_MARGIN_URL = "https://www.sse.com.cn/market/othersdata/margin/detail/"
_SZSE_MARGIN_URL = "https://www.szse.cn/disclosure/margin/margin/index.html"
_CSI_CONSTITUENTS_URL = "https://www.csindex.com.cn/zh-CN/indices/index-detail/"
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

    def index_constituents(self, symbol: str) -> pd.DataFrame:
        ...


@dataclass(frozen=True)
class ETFSupplementResult:
    data: dict[str, Any]
    sources: list[dict[str, Any]]
    data_audit: list[dict[str, Any]]
    data_warnings: list[dict[str, Any] | str]


@dataclass(frozen=True)
class ETFConstituentUniverse:
    index_name: str
    index_code: str
    as_of: str
    codes_by_market: dict[str, set[str]]

    @property
    def codes(self) -> set[str]:
        return set().union(*self.codes_by_market.values())


class ETFSupplementService:
    """Load a bounded number of exchange snapshots for one exact ETF code."""

    def __init__(self, provider: ETFMarketProvider | None = None) -> None:
        self._provider = provider or AKShareETFProvider()

    def recent(
        self,
        code: str,
        trading_dates: Sequence[str],
        *,
        tracking_index: Mapping[str, Any] | None = None,
    ) -> ETFSupplementResult:
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

        constituent_universe = self._load_constituent_universe(
            audit,
            tracking_index,
            dates,
        )
        margin_specs = self._required_margin_specs(
            normalized_code,
            constituent_universe,
        )
        margin_frames = {
            interface: self._load_frames(
                audit=audit,
                interface=interface,
                upstream=upstream,
                documentation_url=documentation_url,
                dates=dates,
                fetch=fetch,
            )
            for interface, (upstream, documentation_url, fetch) in (
                margin_specs.items()
            )
        }

        financing_rows: list[dict[str, Any]] = []
        margin_interface = self._etf_margin_interface(normalized_code)
        if margin_interface is not None:
            financing_rows = self._rows_from_frames(
                audit=audit,
                interface=margin_interface,
                dates=dates,
                frames=margin_frames.get(margin_interface, {}),
                code=normalized_code,
                code_column=(
                    "标的证券代码"
                    if margin_interface == _SSE_MARGIN_INTERFACE
                    else "证券代码"
                ),
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

        component_financing_rows = self._component_financing_rows(
            audit=audit,
            dates=dates,
            universe=constituent_universe,
            margin_frames=margin_frames,
        )
        return self._result(
            normalized_code,
            dates,
            share_rows,
            financing_rows,
            constituent_universe,
            component_financing_rows,
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
        frames = self._load_frames(
            audit=audit,
            interface=interface,
            upstream=upstream,
            documentation_url=documentation_url,
            dates=dates,
            fetch=fetch,
        )
        return self._rows_from_frames(
            audit=audit,
            interface=interface,
            dates=dates,
            frames=frames,
            code=code,
            code_column=code_column,
            value_column=value_column,
            source_date_column=source_date_column,
            fact_name=fact_name,
        )

    def _load_frames(
        self,
        *,
        audit: AuditBundle,
        interface: str,
        upstream: str,
        documentation_url: str,
        dates: list[str],
        fetch: Callable[[str], pd.DataFrame],
    ) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
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
            frames[trading_date] = frame
        return frames

    @staticmethod
    def _rows_from_frames(
        *,
        audit: AuditBundle,
        interface: str,
        dates: list[str],
        frames: Mapping[str, pd.DataFrame],
        code: str,
        code_column: str,
        value_column: str,
        source_date_column: str | None,
        fact_name: str,
    ) -> list[dict[str, Any]]:
        values_by_date: dict[str, float] = {}
        for trading_date in dates:
            frame = frames.get(trading_date)
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

    @staticmethod
    def _etf_margin_interface(code: str) -> str | None:
        if code.startswith(("5", "6")):
            return _SSE_MARGIN_INTERFACE
        if code.startswith(("0", "1", "2", "3")):
            return _SZSE_MARGIN_INTERFACE
        return None

    def _required_margin_specs(
        self,
        code: str,
        universe: ETFConstituentUniverse | None,
    ) -> dict[str, tuple[str, str, Callable[[str], pd.DataFrame]]]:
        required = {
            interface
            for interface in [self._etf_margin_interface(code)]
            if interface is not None
        }
        if universe is not None:
            if universe.codes_by_market.get("sse"):
                required.add(_SSE_MARGIN_INTERFACE)
            if universe.codes_by_market.get("szse"):
                required.add(_SZSE_MARGIN_INTERFACE)

        specs = {
            _SSE_MARGIN_INTERFACE: (
                "上海证券交易所-融资融券明细",
                _SSE_MARGIN_URL,
                self._provider.margin_detail_sse,
            ),
            _SZSE_MARGIN_INTERFACE: (
                "深圳证券交易所-融资融券交易明细",
                _SZSE_MARGIN_URL,
                self._provider.margin_detail_szse,
            ),
        }
        return {interface: specs[interface] for interface in sorted(required)}

    def _load_constituent_universe(
        self,
        audit: AuditBundle,
        tracking_index: Mapping[str, Any] | None,
        trading_dates: list[str],
    ) -> ETFConstituentUniverse | None:
        index_name = str((tracking_index or {}).get("name") or "").strip()
        index_code = normalize_code((tracking_index or {}).get("index_code"))
        if not index_name or len(index_code) != 6 or not index_code.isdigit():
            _warn(
                audit,
                "UNSUPPORTED",
                "ETF 未精确映射到支持的底层指数，无法汇总成分股融资",
                "component_financing_history",
                {"tracking_index": dict(tracking_index or {})},
            )
            return None

        parameters = {"args": [], "kwargs": {"symbol": index_code}}
        frame = self._call_frame(
            audit=audit,
            interface=_CSI_CONSTITUENTS_INTERFACE,
            upstream="中证指数有限公司-指数成份股",
            documentation_url=f"{_CSI_CONSTITUENTS_URL}{index_code}",
            parameters=parameters,
            fetch=lambda: self._provider.index_constituents(index_code),
        )
        if frame is None:
            return None

        matched = frame[
            frame["指数代码"].map(normalize_code).eq(index_code)
        ].copy()
        if matched.empty:
            _warn(
                audit,
                "UNSUPPORTED",
                "中证指数成份接口未返回目标指数",
                "component_financing_history",
                {"index_name": index_name, "index_code": index_code},
            )
            return None

        source_dates = {
            value
            for raw in matched["日期"]
            if (value := _normalize_date(raw)) is not None
        }
        if len(source_dates) != 1:
            _warn(
                audit,
                "DATA_CONTRACT_ERROR",
                "中证指数成份接口未返回唯一有效日期",
                "component_financing_history",
                {
                    "index_code": index_code,
                    "source_dates": sorted(source_dates),
                },
            )
            return None
        constituent_as_of = next(iter(source_dates))
        if trading_dates:
            lag_days = (
                pd.Timestamp(trading_dates[-1]) - pd.Timestamp(constituent_as_of)
            ).days
            if lag_days > 10:
                _warn(
                    audit,
                    "STALE_DATA",
                    "中证指数成份快照早于 ETF 最近交易日超过 10 天",
                    "component_financing_history",
                    {
                        "index_code": index_code,
                        "constituent_as_of": constituent_as_of,
                        "latest_trading_date": trading_dates[-1],
                        "lag_days": lag_days,
                    },
                )
                return None

        codes_by_market: dict[str, set[str]] = {"sse": set(), "szse": set()}
        unknown_exchanges: set[str] = set()
        code_markets: dict[str, str] = {}
        for row in matched.to_dict("records"):
            component_code = normalize_code(row.get("成分券代码"))
            exchange = str(row.get("交易所") or "").strip()
            market = (
                "sse"
                if "上海" in exchange
                else "szse"
                if "深圳" in exchange
                else None
            )
            if len(component_code) != 6 or not component_code.isdigit():
                continue
            if market is None:
                unknown_exchanges.add(exchange)
                continue
            existing = code_markets.get(component_code)
            if existing is not None and existing != market:
                _warn(
                    audit,
                    "DATA_CONTRACT_ERROR",
                    "指数成份证券代码映射到多个交易所",
                    "component_financing_history",
                    {
                        "index_code": index_code,
                        "component_code": component_code,
                        "markets": sorted({existing, market}),
                    },
                )
                return None
            code_markets[component_code] = market
            codes_by_market[market].add(component_code)

        if unknown_exchanges:
            _warn(
                audit,
                "PARTIAL_DATA",
                "部分指数成份交易所无法映射，未纳入融资汇总",
                "component_financing_history",
                {
                    "index_code": index_code,
                    "unknown_exchanges": sorted(unknown_exchanges),
                },
            )
        if not code_markets:
            _warn(
                audit,
                "UNSUPPORTED",
                "指数成份接口没有可映射的沪深证券代码",
                "component_financing_history",
                {"index_code": index_code},
            )
            return None

        return ETFConstituentUniverse(
            index_name=index_name,
            index_code=index_code,
            as_of=constituent_as_of,
            codes_by_market=codes_by_market,
        )

    @staticmethod
    def _component_financing_rows(
        *,
        audit: AuditBundle,
        dates: list[str],
        universe: ETFConstituentUniverse | None,
        margin_frames: Mapping[str, Mapping[str, pd.DataFrame]],
    ) -> list[dict[str, Any]]:
        if universe is None:
            return []

        values_by_date: dict[str, tuple[float, int]] = {}
        market_specs = {
            "sse": (_SSE_MARGIN_INTERFACE, "标的证券代码", "信用交易日期"),
            "szse": (_SZSE_MARGIN_INTERFACE, "证券代码", None),
        }
        for trading_date in dates:
            total_balance = 0.0
            reported_codes: set[str] = set()
            complete = True
            for market, codes in universe.codes_by_market.items():
                if not codes:
                    continue
                interface, code_column, source_date_column = market_specs[market]
                frame = margin_frames.get(interface, {}).get(trading_date)
                if frame is None:
                    complete = False
                    break
                if source_date_column is not None:
                    source_dates = {
                        value
                        for raw in frame[source_date_column]
                        if (value := _normalize_date(raw)) is not None
                    }
                    if source_dates != {trading_date}:
                        _warn(
                            audit,
                            "STALE_DATA",
                            f"{interface} 返回日期与请求交易日不一致",
                            "component_financing_history",
                            {
                                "requested_date": trading_date,
                                "source_dates": sorted(source_dates),
                            },
                        )
                        complete = False
                        break

                normalized_codes = frame[code_column].map(normalize_code)
                matched = frame[normalized_codes.isin(codes)].copy()
                matched["_normalized_code"] = normalized_codes[
                    normalized_codes.isin(codes)
                ]
                if matched["_normalized_code"].duplicated().any():
                    _warn(
                        audit,
                        "DATA_CONTRACT_ERROR",
                        f"{interface} 返回重复成份证券代码",
                        "component_financing_history",
                        {
                            "index_code": universe.index_code,
                            "date": trading_date,
                        },
                    )
                    complete = False
                    break
                matched["融资余额"] = pd.to_numeric(
                    matched["融资余额"],
                    errors="coerce",
                )
                if matched["融资余额"].isna().any() or (
                    matched["融资余额"] < 0
                ).any():
                    _warn(
                        audit,
                        "DATA_CONTRACT_ERROR",
                        f"{interface} 返回无效成份融资余额",
                        "component_financing_history",
                        {
                            "index_code": universe.index_code,
                            "date": trading_date,
                        },
                    )
                    complete = False
                    break
                total_balance += float(matched["融资余额"].sum())
                reported_codes.update(matched["_normalized_code"])

            if complete and reported_codes:
                if len(reported_codes) < len(universe.codes):
                    _warn(
                        audit,
                        "PARTIAL_DATA",
                        "交易所融资明细未覆盖全部指数成份证券",
                        "component_financing_history",
                        {
                            "index_code": universe.index_code,
                            "date": trading_date,
                            "constituent_count": len(universe.codes),
                            "reported_component_count": len(reported_codes),
                        },
                    )
                values_by_date[trading_date] = (
                    total_balance,
                    len(reported_codes),
                )

        rows: list[dict[str, Any]] = []
        constituent_count = len(universe.codes)
        for index, trading_date in enumerate(dates):
            value = values_by_date.get(trading_date)
            if value is None:
                continue
            balance, reported_count = value
            previous_date = dates[index - 1] if index > 0 else None
            previous = values_by_date.get(previous_date) if previous_date else None
            full_coverage = reported_count == constituent_count
            previous_full_coverage = (
                previous is not None and previous[1] == constituent_count
            )
            change = (
                balance - previous[0]
                if full_coverage and previous_full_coverage
                else None
            )
            rows.append(
                {
                    "date": trading_date,
                    "financing_balance_cny": balance,
                    "financing_balance_yi_cny": round(
                        balance / 100_000_000,
                        4,
                    ),
                    "previous_date": previous_date if previous is not None else None,
                    "financing_balance_change_cny": change,
                    "financing_balance_change_yi_cny": (
                        round(change / 100_000_000, 4)
                        if change is not None
                        else None
                    ),
                    "constituent_count": constituent_count,
                    "reported_component_count": reported_count,
                    "coverage_pct": round(
                        reported_count / constituent_count * 100,
                        2,
                    ),
                }
            )
        return rows

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
        return self._call_frame(
            audit=audit,
            interface=interface,
            upstream=upstream,
            documentation_url=documentation_url,
            parameters=parameters,
            fetch=lambda: fetch(provider_date),
        )

    def _call_frame(
        self,
        *,
        audit: AuditBundle,
        interface: str,
        upstream: str,
        documentation_url: str,
        parameters: dict[str, Any],
        fetch: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame | None:
        try:
            frame = validate_frame(
                fetch(),
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
        constituent_universe: ETFConstituentUniverse | None,
        component_financing_rows: list[dict[str, Any]],
        audit: AuditBundle,
    ) -> ETFSupplementResult:
        unavailable: list[str] = [
            "净申购赎回金额",
            "汇金、证金及关联主体实时持仓",
        ]
        if len(share_rows) < 2:
            unavailable.insert(0, "可审计的 ETF 份额变化")
        else:
            unavailable.insert(0, "ETF 长期份额历史（当前仅最近 7 个交易日）")
        if len(financing_rows) < 2:
            unavailable.insert(1, "可审计的 ETF 融资余额变动")
        else:
            unavailable.insert(1, "ETF 融资长期历史分位（当前仅最近 7 个交易日）")
        if len(component_financing_rows) < 2:
            unavailable.append("成分股融资余额变动与历史分位")
        else:
            unavailable.append(
                "成分股融资长期历史分位（当前仅最近 7 个交易日）"
            )

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
            "component_financing": _component_financing_payload(
                component_financing_rows,
                requested_observations=len(dates),
                universe=constituent_universe,
            ),
            "range_summaries": _range_summaries(
                share_rows,
                financing_rows,
                component_financing_rows,
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


def _component_financing_payload(
    rows: list[dict[str, Any]],
    *,
    requested_observations: int,
    universe: ETFConstituentUniverse | None,
) -> dict[str, Any]:
    full_coverage = bool(rows) and all(
        row.get("reported_component_count") == row.get("constituent_count")
        for row in rows
    )
    return {
        "status": (
            "available"
            if (
                len(rows) >= 2
                and len(rows) == requested_observations
                and full_coverage
            )
            else "partial"
            if rows
            else "unavailable"
        ),
        "tracking_index_name": universe.index_name if universe else None,
        "tracking_index_code": universe.index_code if universe else None,
        "constituent_as_of": universe.as_of if universe else None,
        "constituent_count": len(universe.codes) if universe else 0,
        "source_observations": len(rows),
        "actual_start_date": rows[0]["date"] if rows else None,
        "latest_date": rows[-1]["date"] if rows else None,
        "unit": "元",
        "scaled_unit": "亿元",
        "latest": rows[-1] if rows else None,
        "rows": rows,
        "chart_series": [
            [row["date"], row["financing_balance_yi_cny"]]
            for row in rows
        ],
        "scope_note": (
            "使用中证指数官网最新成份快照，汇总沪深交易所逐证券披露的融资余额；"
            "只统计交易所明细中实际返回的成份证券，不把未返回证券补零。"
        ),
        "derived_formulas": {
            "financing_balance_cny": (
                "同日沪深交易所融资明细中命中当前指数成份证券的融资余额求和"
            ),
            "financing_balance_yi_cny": "financing_balance_cny / 100000000",
            "financing_balance_change_cny": (
                "当日成份融资余额合计 - 前一相邻审计交易日合计"
            ),
            "coverage_pct": (
                "交易所融资明细命中成份证券数 / 最新成份证券总数 * 100"
            ),
        },
    }


def _range_summaries(
    share_rows: list[dict[str, Any]],
    financing_rows: list[dict[str, Any]],
    component_financing_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    share_summary = _five_change_summary(
        share_rows,
        "total_shares_change_yi_units",
    )
    financing_summary = _five_change_summary(
        financing_rows,
        "financing_balance_change_yi_cny",
    )
    component_financing_summary = _full_coverage_five_change_summary(
        component_financing_rows,
        "financing_balance_change_yi_cny",
    )
    bounds = (
        share_summary[:2]
        if share_summary is not None
        else financing_summary[:2]
        if financing_summary is not None
        else component_financing_summary[:2]
        if component_financing_summary is not None
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
            "component_financing_net_change_yi_cny": (
                component_financing_summary[2]
                if component_financing_summary is not None
                and component_financing_summary[:2] == bounds
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


def _full_coverage_five_change_summary(
    rows: list[dict[str, Any]],
    change_key: str,
) -> tuple[str, str, float] | None:
    if any(
        row.get("reported_component_count") != row.get("constituent_count")
        for row in rows
    ):
        return None
    return _five_change_summary(rows, change_key)


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
            "effect": (
                "不修正或覆盖 ETF 行情主序列；调用方按补充序列 status "
                "区分 available、partial 与 unavailable。"
            ),
            "details": details,
        }
    )
