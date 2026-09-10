"""Audited A-share industry ranking used by the dashboard header."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

import pandas as pd

from fund_advisor_data_core.audit import (
    INTERFACE_CONTRACTS,
    AuditBundle,
    json_value,
    optional_float,
    rounded,
    validate_frame,
)
from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_data_core.errors import RETRYABLE_CODES, DataCoreError

_INTERFACE = "stock_board_industry_summary_ths"
_UPSTREAM = "同花顺-行业板块实时行情"
_DOCUMENTATION_URL = "https://akshare.akfamily.xyz/data/stock/stock.html"
_SECTOR_LIMIT = 8
_POLL_LIMIT = 6


class MarketPulseProvider(Protocol):
    @property
    def provider_version(self) -> str | None: ...

    def industry_summary(self) -> pd.DataFrame: ...


class MarketPulseService:
    """Return a deterministic ranking and poll topics from one market snapshot."""

    def __init__(self, provider: MarketPulseProvider | None = None) -> None:
        from fund_advisor_data_core.providers.akshare import AKShareMarketProvider

        self._provider = provider or AKShareMarketProvider()

    def pulse(self) -> ToolEnvelope:
        audit = AuditBundle()
        try:
            frame = self._frame(audit)
            sectors = _sector_rows(frame, _SECTOR_LIMIT)
            if not sectors:
                raise DataCoreError(
                    "DATA_CONTRACT_ERROR",
                    "行业板块快照没有可用的板块名称和涨跌幅",
                    {"interface": _INTERFACE},
                )
            snapshot_date = audit.queried_at.strftime("%Y%m%d")
            return ToolEnvelope(
                tool=ToolName.MARKET_PULSE,
                ok=True,
                data={
                    "market": "A股",
                    "snapshot_at": audit.queried_at.isoformat(),
                    "ranking_basis": "同花顺行业板块实时涨跌幅降序",
                    "sectors": sectors,
                    "poll_topics": [
                        _poll_topic(sector, snapshot_date) for sector in sectors[:_POLL_LIMIT]
                    ],
                    "notes": [
                        "热门仅表示当前快照涨跌幅排序，不代表推荐或持续性判断。",
                        "接口未提供交易所官方行情时间，snapshot_at 为本服务查询时间。",
                    ],
                },
                sources=audit.sources,
                data_audit=audit.data_audit,
                data_warnings=audit.data_warnings,
                data_policy=audit.data_policy,
                queried_at=audit.queried_at,
            )
        except DataCoreError as exc:
            return ToolEnvelope(
                tool=ToolName.MARKET_PULSE,
                ok=False,
                data=None,
                sources=audit.sources,
                data_audit=audit.data_audit,
                data_warnings=audit.data_warnings,
                data_policy=audit.data_policy,
                queried_at=audit.queried_at,
                error=ToolError(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.code in RETRYABLE_CODES,
                    details=exc.details,
                ),
            )

    def _frame(self, audit: AuditBundle) -> pd.DataFrame:
        parameters: dict[str, Any] = {"args": [], "kwargs": {}}
        try:
            frame = self._provider.industry_summary()
            validated = validate_frame(
                frame,
                _INTERFACE,
                required_columns=INTERFACE_CONTRACTS[_INTERFACE],
            )
        except DataCoreError as exc:
            audit.add_failed_call(_INTERFACE, parameters, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - normalize upstream failures
            wrapped = DataCoreError(
                "DATA_SOURCE_ERROR",
                f"AKShare 接口 {_INTERFACE} 查询失败，当前无法确认热门板块",
                {"interface": _INTERFACE, "reason": str(exc)},
            )
            audit.add_failed_call(_INTERFACE, parameters, wrapped)
            raise wrapped from exc

        audit.add_source(
            _INTERFACE,
            _UPSTREAM,
            provider_version=self._provider.provider_version,
            documentation_url=_DOCUMENTATION_URL,
        )
        audit.add_passed_frame(
            _INTERFACE,
            parameters,
            validated,
            required_columns=INTERFACE_CONTRACTS[_INTERFACE],
        )
        return validated


def _sector_rows(frame: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in frame.iterrows():
        name = str(json_value(row.get("板块")) or "").strip()
        change_pct = optional_float(row.get("涨跌幅"))
        if not name or change_pct is None:
            continue
        rows.append(
            {
                "name": name,
                "change_pct": rounded(change_pct),
                "rising_count": _optional_int(row.get("上涨家数")),
                "falling_count": _optional_int(row.get("下跌家数")),
                "leading_stock": str(json_value(row.get("领涨股")) or "").strip() or None,
                "leading_stock_change_pct": rounded(row.get("领涨股-涨跌幅")),
            }
        )

    rows.sort(key=lambda item: (-float(item["change_pct"]), item["name"]))
    selected = rows[:limit]
    for rank, item in enumerate(selected, start=1):
        item["rank"] = rank
    return selected


def _poll_topic(sector: dict[str, Any], snapshot_date: str) -> dict[str, Any]:
    name = str(sector["name"])
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    direction = "延续强势" if float(sector["change_pct"]) >= 0 else "率先修复"
    return {
        "key": f"sector_{snapshot_date}_{digest}",
        "question": f"{name}板块今日能否{direction}？",
        "sector_name": name,
    }


def _optional_int(value: Any) -> int | None:
    number = optional_float(value)
    return int(number) if number is not None else None
