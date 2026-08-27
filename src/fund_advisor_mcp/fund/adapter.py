"""Transport-neutral adapter around the AKShare FundAdvisor class."""

from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from fund_advisor_data_core.contracts import ToolEnvelope, ToolError, ToolName
from fund_advisor_data_core.services import FundSearchService, FundStatusService
from fund_advisor_mcp.config import AppConfig, get_config

from .cache import EnvelopeCache, build_envelope_cache
from .schemas import (
    AnalyzeInput,
    AuditInput,
    CompareInput,
    ETFDashboardInput,
    FundInput,
    SearchInput,
    StockValuationInput,
    ValuationInput,
)
from .skill_loader import load_skill_module

SHANGHAI = ZoneInfo("Asia/Shanghai")

_RETRYABLE_CODES = {
    "DATA_SOURCE_ERROR",
    "VALUATION_SOURCE_UNAVAILABLE",
    "RATE_LIMITED",
    "UPSTREAM_TIMEOUT",
}


class ToolExecutionTimeout(TimeoutError):
    pass


class FundSearchRunner(Protocol):
    def search(self, query: str, limit: int) -> ToolEnvelope:
        ...


class FundStatusRunner(Protocol):
    def status(self, query: str) -> ToolEnvelope:
        ...


class FundAdvisorToolAdapter:
    """Execute Skill methods and preserve their audit payload verbatim."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        advisor_factory: Callable[[], Any] | None = None,
        fund_search_service: FundSearchRunner | None = None,
        fund_status_service: FundStatusRunner | None = None,
        cache: EnvelopeCache | None = None,
    ) -> None:
        self._config = config or get_config()
        self._semaphore = threading.BoundedSemaphore(self._config.mcp.concurrency)
        self._cache = cache or build_envelope_cache(self._config)
        self._advisor_factory = advisor_factory or self._default_advisor_factory
        self._fund_search_service = fund_search_service or FundSearchService()
        self._fund_status_service = fund_status_service or FundStatusService()
        self._executor = ThreadPoolExecutor(
            max_workers=self._config.mcp.concurrency,
            thread_name_prefix="fund-advisor-tool",
        )

    def _default_advisor_factory(self) -> Any:
        module = load_skill_module()
        return module.FundAdvisor(timeout_seconds=self._config.mcp.timeout_seconds)

    def _cache_key(self, tool: ToolName, arguments: dict[str, Any]) -> str:
        normalized = json.dumps(
            arguments,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"{tool.value}:1.1:{digest}"

    @staticmethod
    def _ttl(tool: ToolName) -> int:
        return {
            ToolName.FUND_SEARCH: 6 * 60 * 60,
            ToolName.FUND_STATUS: 5 * 60,
            ToolName.FUND_ANALYZE: 30 * 60,
            ToolName.ETF_DASHBOARD: 30 * 60,
            ToolName.FUND_PROFILE: 6 * 60 * 60,
            ToolName.FUND_RATING: 12 * 60 * 60,
            ToolName.INDEX_VALUATION: 30 * 60,
            ToolName.STOCK_VALUATION: 30 * 60,
            ToolName.FUND_COMPARE: 30 * 60,
            ToolName.INTERFACE_AUDIT: 60,
        }[tool]

    def _execute(
        self,
        tool: ToolName,
        arguments: dict[str, Any],
        call: Callable[[Any], dict[str, Any]],
        *,
        cache: bool = True,
    ) -> ToolEnvelope:
        key = self._cache_key(tool, arguments)
        if cache:
            cached = self._cache.get(key)
            if cached is not None:
                return ToolEnvelope.model_validate(cached)

        advisor: Any | None = None
        try:
            advisor = self._advisor_factory()
            data = self._invoke_with_timeout(call, advisor)
            common = advisor.common_output()
            envelope = ToolEnvelope(
                tool=tool,
                ok=bool(data.get("ok", True)),
                data=data,
                sources=common.get("sources", []),
                data_audit=common.get("data_audit", []),
                data_warnings=common.get("data_warnings", []),
                data_policy=common.get("data_policy", {}),
                queried_at=common.get("queried_at", datetime.now(SHANGHAI)),
            )
            if cache and envelope.ok:
                self._cache.set(
                    key,
                    envelope.model_dump(mode="json"),
                    self._ttl(tool),
                )
            return envelope
        except Exception as exc:
            module = load_skill_module()
            common = (
                {}
                if isinstance(exc, ToolExecutionTimeout)
                else advisor.common_output()
                if advisor is not None
                else {}
            )
            if isinstance(exc, ToolExecutionTimeout):
                code = "UPSTREAM_TIMEOUT"
                message = str(exc)
                details = {"timeout_seconds": self._config.mcp.timeout_seconds}
            elif isinstance(exc, module.AdvisorError):
                code = exc.code
                message = exc.message
                details = exc.details
            else:
                code = "INTERNAL_ERROR"
                message = "Fund Advisor 工具执行失败"
                details = {"reason": str(exc)}
            return ToolEnvelope(
                tool=tool,
                ok=False,
                data=None,
                sources=common.get("sources", []),
                data_audit=common.get("data_audit", []),
                data_warnings=common.get("data_warnings", []),
                data_policy=common.get(
                    "data_policy",
                    {"ai_may_generate_market_data": False},
                ),
                queried_at=common.get("queried_at", datetime.now(SHANGHAI)),
                error=ToolError(
                    code=code,
                    message=message,
                    retryable=code in _RETRYABLE_CODES,
                    details=details,
                ),
            )

    def _invoke_with_timeout(
        self,
        call: Callable[[Any], dict[str, Any]],
        advisor: Any,
    ) -> dict[str, Any]:
        def invoke() -> dict[str, Any]:
            with self._semaphore:
                return call(advisor)

        future = self._executor.submit(invoke)
        try:
            return future.result(timeout=self._config.mcp.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ToolExecutionTimeout(
                f"Fund Advisor 超过 {self._config.mcp.timeout_seconds} 秒未完成"
            ) from exc

    def _invoke_envelope_with_timeout(
        self,
        call: Callable[[], ToolEnvelope],
    ) -> ToolEnvelope:
        def invoke() -> ToolEnvelope:
            with self._semaphore:
                return call()

        future = self._executor.submit(invoke)
        try:
            return future.result(timeout=self._config.mcp.timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ToolExecutionTimeout(
                f"Fund Advisor 超过 {self._config.mcp.timeout_seconds} 秒未完成"
            ) from exc

    def _execute_core_envelope(
        self,
        tool: ToolName,
        arguments: dict[str, Any],
        call: Callable[[], ToolEnvelope],
        *,
        cache: bool = True,
    ) -> ToolEnvelope:
        key = self._cache_key(tool, arguments)
        if cache:
            cached = self._cache.get(key)
            if cached is not None:
                return ToolEnvelope.model_validate(cached)

        try:
            envelope = self._invoke_envelope_with_timeout(call)
            if cache and envelope.ok:
                self._cache.set(
                    key,
                    envelope.model_dump(mode="json"),
                    self._ttl(tool),
                )
            return envelope
        except ToolExecutionTimeout as exc:
            return ToolEnvelope(
                tool=tool,
                ok=False,
                data=None,
                data_policy={"ai_may_generate_market_data": False},
                queried_at=datetime.now(SHANGHAI),
                error=ToolError(
                    code="UPSTREAM_TIMEOUT",
                    message=str(exc),
                    retryable=True,
                    details={"timeout_seconds": self._config.mcp.timeout_seconds},
                ),
            )
        except Exception as exc:
            return ToolEnvelope(
                tool=tool,
                ok=False,
                data=None,
                data_policy={"ai_may_generate_market_data": False},
                queried_at=datetime.now(SHANGHAI),
                error=ToolError(
                    code="INTERNAL_ERROR",
                    message="Fund Advisor 工具执行失败",
                    details={"reason": str(exc)},
                ),
            )

    def fund_search(self, **kwargs: Any) -> ToolEnvelope:
        request = SearchInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute_core_envelope(
            ToolName.FUND_SEARCH,
            arguments,
            lambda: self._fund_search_service.search(request.query, request.limit),
        )

    def fund_status(self, **kwargs: Any) -> ToolEnvelope:
        request = FundInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute_core_envelope(
            ToolName.FUND_STATUS,
            arguments,
            lambda: self._fund_status_service.status(request.fund),
        )

    def fund_analyze(self, **kwargs: Any) -> ToolEnvelope:
        request = AnalyzeInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.FUND_ANALYZE,
            arguments,
            lambda advisor: advisor.analyze(request.fund, request.years),
        )

    def etf_dashboard(self, **kwargs: Any) -> ToolEnvelope:
        request = ETFDashboardInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.ETF_DASHBOARD,
            arguments,
            lambda advisor: advisor.etf_dashboard(
                request.fund,
                request.years,
                request.max_points,
            ),
        )

    def index_valuation(self, **kwargs: Any) -> ToolEnvelope:
        request = ValuationInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.INDEX_VALUATION,
            arguments,
            lambda advisor: advisor.valuation(
                request.index,
                request.years,
                request.max_points,
            ),
        )

    def stock_valuation(self, **kwargs: Any) -> ToolEnvelope:
        request = StockValuationInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.STOCK_VALUATION,
            arguments,
            lambda advisor: advisor.stock_valuation(
                request.stock,
                request.years,
                request.max_points,
            ),
        )

    def fund_compare(self, **kwargs: Any) -> ToolEnvelope:
        request = CompareInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.FUND_COMPARE,
            arguments,
            lambda advisor: advisor.compare(request.funds, request.years),
        )

    def fund_profile(self, **kwargs: Any) -> ToolEnvelope:
        request = FundInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.FUND_PROFILE,
            arguments,
            lambda advisor: advisor.profile(request.fund),
        )

    def fund_rating(self, **kwargs: Any) -> ToolEnvelope:
        request = FundInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.FUND_RATING,
            arguments,
            lambda advisor: advisor.rating(request.fund),
        )

    def interface_audit(self, **kwargs: Any) -> ToolEnvelope:
        request = AuditInput.model_validate(kwargs)
        arguments = request.model_dump()
        return self._execute(
            ToolName.INTERFACE_AUDIT,
            arguments,
            lambda advisor: advisor.audit(
                request.fund,
                request.etf,
                request.lof,
                request.index,
            ),
            cache=False,
        )

    def call(self, tool: str | ToolName, arguments: dict[str, Any]) -> ToolEnvelope:
        name = ToolName(tool)
        method = getattr(self, name.value)
        return method(**arguments)
