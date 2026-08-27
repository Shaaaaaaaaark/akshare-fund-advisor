"""Audited public-fund trading-status lookup."""

from __future__ import annotations

from typing import Any, Protocol

import pandas as pd

from fund_advisor_data_core.audit import (
    INTERFACE_CONTRACTS,
    AuditBundle,
    json_value,
    normalize_code,
    operation_is_open,
    optional_float,
    rounded,
    validate_frame,
)
from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_data_core.errors import RETRYABLE_CODES, DataCoreError
from fund_advisor_data_core.providers.akshare import AKShareFundProvider

from .fund_catalog import resolve_fund

_FUND_NAME_INTERFACE = "fund_name_em"
_FUND_NAME_UPSTREAM = "东方财富-基金基本信息"
_FUND_PURCHASE_INTERFACE = "fund_purchase_em"
_FUND_PURCHASE_UPSTREAM = "东方财富-基金申购状态"

# 名称含「联接／连接」的份额是场外基金，不能按 ETF/LOF 名称兜底判成场内。
_OFF_EXCHANGE_NAME_MARKERS = ("联接", "连接")


class FundStatusProvider(Protocol):
    @property
    def provider_version(self) -> str | None:
        ...

    def fund_names(self) -> pd.DataFrame:
        ...

    def fund_purchases(self) -> pd.DataFrame:
        ...


class FundStatusService:
    def __init__(self, provider: FundStatusProvider | None = None) -> None:
        self._provider = provider or AKShareFundProvider()

    def status(self, query: str) -> ToolEnvelope:
        audit = AuditBundle()
        try:
            names = self._frame(
                audit,
                _FUND_NAME_INTERFACE,
                _FUND_NAME_UPSTREAM,
                self._provider.fund_names,
            )
            fund = resolve_fund(names, query)
            purchases = self._frame(
                audit,
                _FUND_PURCHASE_INTERFACE,
                _FUND_PURCHASE_UPSTREAM,
                self._provider.fund_purchases,
            )
            data = {
                "ok": True,
                "action": "status",
                "fund": fund,
                "availability": self._status_for_fund(fund, purchases),
            }
            return ToolEnvelope(
                tool=ToolName.FUND_STATUS,
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
                tool=ToolName.FUND_STATUS,
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

    def _frame(
        self,
        audit: AuditBundle,
        interface: str,
        upstream: str,
        load: Any,
    ) -> pd.DataFrame:
        parameters = {"args": [], "kwargs": {}}
        try:
            frame = load()
            validated = validate_frame(
                frame,
                interface,
                required_columns=INTERFACE_CONTRACTS[interface],
            )
        except DataCoreError as exc:
            audit.add_failed_call(interface, parameters, exc)
            raise
        except Exception as exc:
            wrapped = DataCoreError(
                "DATA_SOURCE_ERROR",
                f"AKShare 接口 {interface} 查询失败，当前无法确认",
                {"interface": interface, "reason": str(exc)},
            )
            audit.add_failed_call(interface, parameters, wrapped)
            raise wrapped from exc

        audit.add_source(
            interface,
            upstream,
            provider_version=self._provider.provider_version,
        )
        audit.add_passed_frame(
            interface,
            parameters,
            validated,
            required_columns=INTERFACE_CONTRACTS[interface],
        )
        return validated

    def _status_for_fund(
        self,
        fund: dict[str, Any],
        purchases: pd.DataFrame,
    ) -> dict[str, Any]:
        row = self._purchase_row(purchases, fund["code"])
        if row is None:
            raise DataCoreError(
                "STATUS_NOT_FOUND",
                f"申购状态表中未找到基金 {fund['code']}，当前无法确认",
            )

        subscription_status = json_value(row.get("申购状态"))
        redemption_status = json_value(row.get("赎回状态"))
        exchange = self._is_exchange_record(fund, row)
        common: dict[str, Any] = {
            "confirmed": True,
            "mode": "exchange" if exchange else "off_exchange",
            "source_report_date": json_value(row.get("最新净值/万份收益-报告时间")),
            "latest_nav_or_income": rounded(row.get("最新净值/万份收益"), 4),
        }

        if exchange:
            common["exchange"] = {
                "source_subscription_status": subscription_status,
                "source_redemption_status": redemption_status,
                "market_session": None,
                "standard_market_open_now": None,
                "can_submit_standard_session_order": None,
                "can_buy_now": None,
                "can_sell_now": None,
                "note": (
                    "场内基金状态来自申赎状态表；是否可实时交易还需核对停牌、"
                    "券商通道、产品权限、流动性和最小交易单位。"
                ),
            }
            return common

        raw_limit = optional_float(row.get("日累计限定金额"))
        effective_limit = (
            None if raw_limit is not None and raw_limit >= 10_000_000_000 else raw_limit
        )
        common["off_exchange"] = {
            "subscription_status": subscription_status,
            "redemption_status": redemption_status,
            "can_submit_subscription": operation_is_open(subscription_status),
            "can_submit_redemption": operation_is_open(redemption_status),
            "next_open_date": json_value(row.get("下一开放日")),
            "minimum_purchase_cny": rounded(row.get("购买起点")),
            "daily_limit_cny": rounded(effective_limit),
            "source_daily_limit_cny": rounded(raw_limit),
            "purchase_fee_pct": rounded(row.get("手续费")),
            "note": (
                "状态表示业务是否开放，不保证立即确认。截止时间、确认日、到账日、"
                "持有期锁定和平台规则需核对基金公告及销售平台。"
            ),
        }
        return common

    @staticmethod
    def _purchase_row(frame: pd.DataFrame, code: str) -> pd.Series | None:
        normalized = normalize_code(code)
        matched = frame[frame["基金代码"].map(normalize_code).eq(normalized)]
        if matched.empty:
            return None
        if len(matched) > 1:
            # 与 resolve_fund 的 AMBIGUOUS 语义一致：拒绝静默取第一行。
            raise DataCoreError(
                "AMBIGUOUS_FUND",
                f"申购状态表中基金代码 {normalized} 命中多行，拒绝自动选择，请确认份额",
                {
                    "fund_code": normalized,
                    "matched_rows": int(len(matched)),
                    "candidates": [
                        {
                            "code": normalize_code(row.get("基金代码")),
                            "name": json_value(row.get("基金简称")),
                            "type": json_value(row.get("基金类型")),
                            "subscription_status": json_value(row.get("申购状态")),
                            "redemption_status": json_value(row.get("赎回状态")),
                            "source_report_date": json_value(
                                row.get("最新净值/万份收益-报告时间")
                            ),
                        }
                        for _, row in matched.head(10).iterrows()
                    ],
                },
            )
        return matched.iloc[0]

    @staticmethod
    def _is_exchange_record(
        fund: dict[str, Any],
        purchase_row: pd.Series | None,
    ) -> bool:
        name = str(fund.get("name") or "")
        # ETF/LOF 联接（连接）基金是场外份额，名称兜底不得把它们判成场内。
        if any(marker in name for marker in _OFF_EXCHANGE_NAME_MARKERS):
            return False
        if purchase_row is not None:
            statuses = (
                str(purchase_row.get("申购状态") or ""),
                str(purchase_row.get("赎回状态") or ""),
            )
            if any("场内交易" in item for item in statuses):
                return True
        upper_name = name.upper()
        return "ETF" in upper_name or "LOF" in upper_name
