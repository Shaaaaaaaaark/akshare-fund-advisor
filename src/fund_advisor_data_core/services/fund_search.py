"""Audited public-fund search backed directly by data providers."""

from __future__ import annotations

from typing import Any, Protocol

import pandas as pd

from fund_advisor_data_core.audit import (
    INTERFACE_CONTRACTS,
    AuditBundle,
    validate_frame,
)
from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_data_core.errors import RETRYABLE_CODES, DataCoreError
from fund_advisor_data_core.providers.akshare import AKShareFundProvider

from .fund_catalog import search_candidates

_FUND_NAME_INTERFACE = "fund_name_em"
_FUND_NAME_UPSTREAM = "东方财富-基金基本信息"


class FundNameProvider(Protocol):
    @property
    def provider_version(self) -> str | None:
        ...

    def fund_names(self) -> pd.DataFrame:
        ...


class FundSearchService:
    def __init__(self, provider: FundNameProvider | None = None) -> None:
        self._provider = provider or AKShareFundProvider()

    def search(self, query: str, limit: int = 10) -> ToolEnvelope:
        audit = AuditBundle()
        try:
            data = self._search_data(query, limit, audit)
            return ToolEnvelope(
                tool=ToolName.FUND_SEARCH,
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
                tool=ToolName.FUND_SEARCH,
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

    def _search_data(
        self,
        query: str,
        limit: int,
        audit: AuditBundle,
    ) -> dict[str, Any]:
        clean_query = query.strip()
        if not clean_query:
            raise DataCoreError("INVALID_ARGUMENT", "搜索词不能为空")
        if limit < 1:
            raise DataCoreError(
                "INVALID_ARGUMENT",
                "搜索结果数量限制必须大于 0",
                {"limit": limit},
            )

        candidates = search_candidates(self._names(audit), clean_query)
        return {
            "ok": True,
            "action": "search",
            "query": query,
            "count": min(len(candidates), limit),
            "has_more": len(candidates) > limit,
            "results": [record for _, record in candidates[:limit]],
            "guidance": (
                "存在多个份额或近似名称时，请使用明确基金代码继续查询。"
                if len(candidates) > 1
                else None
            ),
        }

    def _names(self, audit: AuditBundle) -> pd.DataFrame:
        parameters = {"args": [], "kwargs": {}}
        try:
            frame = self._provider.fund_names()
            validated = validate_frame(
                frame,
                _FUND_NAME_INTERFACE,
                required_columns=INTERFACE_CONTRACTS[_FUND_NAME_INTERFACE],
            )
        except DataCoreError as exc:
            audit.add_failed_call(_FUND_NAME_INTERFACE, parameters, exc)
            raise
        except Exception as exc:
            wrapped = DataCoreError(
                "DATA_SOURCE_ERROR",
                f"AKShare 接口 {_FUND_NAME_INTERFACE} 查询失败，当前无法确认",
                {"interface": _FUND_NAME_INTERFACE, "reason": str(exc)},
            )
            audit.add_failed_call(_FUND_NAME_INTERFACE, parameters, wrapped)
            raise wrapped from exc

        audit.add_source(
            _FUND_NAME_INTERFACE,
            _FUND_NAME_UPSTREAM,
            provider_version=self._provider.provider_version,
        )
        audit.add_passed_frame(
            _FUND_NAME_INTERFACE,
            parameters,
            validated,
            required_columns=INTERFACE_CONTRACTS[_FUND_NAME_INTERFACE],
        )
        return validated
