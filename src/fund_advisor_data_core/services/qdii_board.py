"""Audited QDII / overseas fund purchase-limit board.

Reuses the same audited interface as fund_status (`fund_purchase_em`) and the
same placeholder/limit semantics; it never fabricates a limit and never treats
the 9,999,999,999 "no effective limit" placeholder as a real threshold.
"""

from __future__ import annotations

from typing import Any, Protocol

import pandas as pd

from fund_advisor_data_core.audit import (
    INTERFACE_CONTRACTS,
    AuditBundle,
    json_value,
    normalize_code,
    optional_float,
    rounded,
    validate_frame,
)
from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_data_core.errors import RETRYABLE_CODES, DataCoreError

_FUND_PURCHASE_INTERFACE = "fund_purchase_em"
_FUND_PURCHASE_UPSTREAM = "东方财富-基金申购状态"

# 上游用 9,999,999,999 / 10,000,000,000 表示「未显示有效限额」。真实单日限额远低于
# 十亿量级，这里以 10 亿为阈值统一识别占位，不当作真实门槛。
_NO_EFFECTIVE_LIMIT_PLACEHOLDER = 1_000_000_000.0

# 只保留 QDII / 境内可投海外份额。名称含「联接/连接」的仍是场外份额，允许上榜。
_OVERSEAS_TYPE_MARKERS = ("QDII", "海外")

# 榜单只收「有限额」的两档；开放申购和场内交易不进榜。
_LIMITED_LARGE = "限大额"
_SUSPENDED = "暂停申购"

# 确定性主题标签：固定关键词规则，不是模型生成，也不是市场数值。
# 顺序敏感：更具体的主题排在更宽泛的主题之前。
_THEME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("纳斯达克100", ("纳斯达克100", "纳指100", "纳斯达克", "纳指", "NASDAQ")),
    ("标普500", ("标普500", "标普 500", "SP500", "S&P500", "S&P 500")),
    ("标普行业/主题", ("标普",)),
    ("道琼斯", ("道琼斯", "道指")),
    ("港股/中概", ("恒生", "港股", "中概", "中国互联网", "香港")),
    ("日经/日本", ("日经", "日本")),
    ("德国/欧洲", ("德国", "欧洲", "法国")),
    ("印度", ("印度",)),
    ("越南", ("越南",)),
    ("黄金/商品", ("黄金", "石油", "原油", "商品", "油气")),
)
_THEME_OTHER = "其他海外"


class QDIIBoardProvider(Protocol):
    @property
    def provider_version(self) -> str | None:
        ...

    def fund_purchases(self) -> pd.DataFrame:
        ...


class QDIIPurchaseBoardService:
    """Deterministic QDII/overseas purchase-limit board from one audited snapshot."""

    def __init__(self, provider: QDIIBoardProvider | None = None) -> None:
        from fund_advisor_data_core.providers.akshare import AKShareFundProvider

        self._provider = provider or AKShareFundProvider()

    def board(self) -> ToolEnvelope:
        audit = AuditBundle()
        try:
            purchases = self._frame(audit)
            data = self._board_data(purchases)
            return ToolEnvelope(
                tool=ToolName.QDII_PURCHASE_BOARD,
                ok=True,
                data=data,
                sources=audit.sources,
                data_audit=audit.data_audit,
                data_warnings=audit.data_warnings,
                data_policy=audit.data_policy,
                queried_at=audit.queried_at,
            )
        except DataCoreError as exc:
            return ToolEnvelope(
                tool=ToolName.QDII_PURCHASE_BOARD,
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
            frame = self._provider.fund_purchases()
            validated = validate_frame(
                frame,
                _FUND_PURCHASE_INTERFACE,
                required_columns=INTERFACE_CONTRACTS[_FUND_PURCHASE_INTERFACE],
            )
        except DataCoreError as exc:
            audit.add_failed_call(_FUND_PURCHASE_INTERFACE, parameters, exc)
            raise
        except Exception as exc:  # noqa: BLE001 - normalize upstream failures
            wrapped = DataCoreError(
                "DATA_SOURCE_ERROR",
                f"AKShare 接口 {_FUND_PURCHASE_INTERFACE} 查询失败，当前无法确认",
                {"interface": _FUND_PURCHASE_INTERFACE, "reason": str(exc)},
            )
            audit.add_failed_call(_FUND_PURCHASE_INTERFACE, parameters, wrapped)
            raise wrapped from exc

        audit.add_source(
            _FUND_PURCHASE_INTERFACE,
            _FUND_PURCHASE_UPSTREAM,
            provider_version=self._provider.provider_version,
        )
        audit.add_passed_frame(
            _FUND_PURCHASE_INTERFACE,
            parameters,
            validated,
            required_columns=INTERFACE_CONTRACTS[_FUND_PURCHASE_INTERFACE],
        )
        return validated

    def _board_data(self, purchases: pd.DataFrame) -> dict[str, Any]:
        report_dates: set[str] = set()
        limited_large: list[dict[str, Any]] = []
        suspended: list[dict[str, Any]] = []

        for _, row in purchases.iterrows():
            fund_type = str(row.get("基金类型") or "")
            if not _is_overseas(fund_type):
                continue
            status = str(row.get("申购状态") or "").strip()
            if status not in (_LIMITED_LARGE, _SUSPENDED):
                continue

            report_date = json_value(row.get("最新净值/万份收益-报告时间"))
            if isinstance(report_date, str) and report_date:
                report_dates.add(report_date)

            entry = _fund_entry(row, fund_type, status)
            if status == _LIMITED_LARGE:
                limited_large.append(entry)
            else:
                suspended.append(entry)

        # 限大额：按有效限额升序（越紧张越靠前），无有效限额占位排最后。
        limited_large.sort(key=_limit_sort_key)
        # 暂停申购：源限额字段无意义，按代码稳定排序。
        suspended.sort(key=lambda item: item["code"])

        categories = _grouped_by_theme(limited_large, suspended)
        disclosed_amount_count = sum(
            1 for entry in limited_large if entry["amount_disclosed"]
        )
        sorted_dates = sorted(report_dates)
        latest_report_date = sorted_dates[-1] if sorted_dates else None
        return {
            "ok": True,
            "action": "qdii_purchase_board",
            "scope": "境内可投海外（QDII/海外）基金申购限额榜",
            "latest_source_report_date": latest_report_date,
            "source_report_date_span": (
                {"earliest": sorted_dates[0], "latest": sorted_dates[-1]}
                if sorted_dates
                else None
            ),
            "summary": {
                "limited_large_count": len(limited_large),
                "limited_large_amount_disclosed_count": disclosed_amount_count,
                "suspended_count": len(suspended),
                "category_count": len(categories),
            },
            "tiers": {
                "limited_large": {
                    "label": "限大额",
                    "count": len(limited_large),
                    "funds": limited_large,
                },
                "suspended": {
                    "label": "暂停申购",
                    "count": len(suspended),
                    "funds": suspended,
                },
            },
            "categories": categories,
            "notes": [
                "范围为境内公募 QDII/海外份额，不是全球所有基金。",
                "申购状态与限额为查询当日的同一份实时快照；表头只显示最新净值报告日，"
                "各基金净值报告日可能较早（QDII 净值有延迟），保留在每只基金的 source_report_date。",
                "限额金额仅在『限大额』且源披露正数门槛时展示；大量『限大额』记录源金额为 0，"
                "按未披露处理，不编造 0 元门槛。",
                "『暂停申购』和 >= 10 亿的占位值都不展示金额。",
                "为当日申赎状态快照，无历史限额序列；不构成申购建议。",
            ],
            "derived_formulas": {
                "effective_daily_limit_cny": (
                    "仅当申购状态为『限大额』且源日累计限定金额为 (0, 1e9) 的正数时取原值，"
                    "否则置空（未披露或占位）"
                ),
                "theme": "对基金简称按固定关键词规则打标签，非模型生成",
                "status_tier": "直接来自源『申购状态』，仅保留限大额/暂停申购",
            },
        }


def _is_overseas(fund_type: str) -> bool:
    return any(marker in fund_type for marker in _OVERSEAS_TYPE_MARKERS)


def _theme_of(name: str) -> str:
    for theme, keywords in _THEME_RULES:
        if any(keyword in name for keyword in keywords):
            return theme
    return _THEME_OTHER


def _fund_entry(row: pd.Series, fund_type: str, status: str) -> dict[str, Any]:
    name = str(json_value(row.get("基金简称")) or "")
    raw_limit = optional_float(row.get("日累计限定金额"))
    has_placeholder = raw_limit is not None and raw_limit >= _NO_EFFECTIVE_LIMIT_PLACEHOLDER
    # 限额金额只在「限大额」且披露了正数门槛时有意义。暂停申购、占位值、以及大量
    # 「限大额但金额为 0」的记录都视为未披露有效金额，不编造 0 元门槛。
    has_disclosed_amount = raw_limit is not None and 0 < raw_limit < _NO_EFFECTIVE_LIMIT_PLACEHOLDER
    effective_limit = raw_limit if (status == _LIMITED_LARGE and has_disclosed_amount) else None
    return {
        "code": normalize_code(row.get("基金代码")),
        "name": name,
        "fund_type": fund_type,
        "theme": _theme_of(name),
        "subscription_status": status,
        "status_tier": "limited_large" if status == _LIMITED_LARGE else "suspended",
        "effective_daily_limit_cny": rounded(effective_limit),
        "amount_disclosed": bool(status == _LIMITED_LARGE and has_disclosed_amount),
        "source_daily_limit_cny": rounded(raw_limit),
        "no_effective_limit_placeholder": bool(has_placeholder),
        "minimum_purchase_cny": rounded(row.get("购买起点")),
        "purchase_fee_pct": rounded(row.get("手续费")),
        "next_open_date": json_value(row.get("下一开放日")),
        "source_report_date": json_value(row.get("最新净值/万份收益-报告时间")),
    }


def _limit_sort_key(entry: dict[str, Any]) -> tuple[int, float, str]:
    limit = entry["effective_daily_limit_cny"]
    if limit is None:
        # 无有效限额占位排在所有真实限额之后。
        return (1, 0.0, entry["code"])
    return (0, float(limit), entry["code"])


def _grouped_by_theme(
    limited_large: list[dict[str, Any]],
    suspended: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    order: list[str] = [theme for theme, _ in _THEME_RULES] + [_THEME_OTHER]
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for entry in limited_large:
        buckets.setdefault(entry["theme"], {"limited_large": [], "suspended": []})
        buckets[entry["theme"]]["limited_large"].append(entry)
    for entry in suspended:
        buckets.setdefault(entry["theme"], {"limited_large": [], "suspended": []})
        buckets[entry["theme"]]["suspended"].append(entry)

    categories: list[dict[str, Any]] = []
    for theme in order:
        tiers = buckets.get(theme)
        if tiers is None:
            continue
        categories.append(
            {
                "theme": theme,
                "limited_large_count": len(tiers["limited_large"]),
                "suspended_count": len(tiers["suspended"]),
                "limited_large": tiers["limited_large"],
                "suspended": tiers["suspended"],
            }
        )
    return categories
