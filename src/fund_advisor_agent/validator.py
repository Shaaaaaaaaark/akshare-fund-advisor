"""Deterministic ToolEnvelope and association validation."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .policies import status_for_error
from .state import (
    AgentError,
    AgentStatus,
    AssociationDraft,
    FactRef,
    RegisteredTool,
    ToolExecution,
)

_FORBIDDEN_ASSOCIATION_PATTERNS = (
    re.compile(r"因为.+所以"),
    re.compile(r"导致"),
    re.compile(r"必然"),
    re.compile(r"一定会"),
    re.compile(r"保证"),
    re.compile(r"稳赚"),
    re.compile(r"抄底"),
    re.compile(r"逃顶"),
    re.compile(r"满仓"),
    re.compile(r"必须买"),
    re.compile(r"必须卖"),
    re.compile(r"综合估值"),
    re.compile(r"净值.+(?:低估|高估)"),
)


def validate_tool_results(
    executions: list[ToolExecution],
    *,
    maximum_facts: int,
) -> tuple[
    AgentStatus,
    list[FactRef],
    list[str],
    list[str],
    list[AgentError],
]:
    facts: list[FactRef] = []
    limitations: list[str] = []
    warnings: list[str] = []
    errors: list[AgentError] = []
    failure_statuses: list[AgentStatus] = []
    required_failure_statuses: list[AgentStatus] = []
    success_count = 0

    for execution in executions:
        envelope = execution.envelope
        if not envelope.get("ok"):
            error = envelope.get("error") or {}
            code = str(error.get("code") or "MCP_TOOL_ERROR")
            status = status_for_error(code)
            failure_statuses.append(status)
            if execution.required:
                required_failure_statuses.append(status)
            else:
                warnings.append(
                    f"可选背景工具 {execution.tool.value} 不可用：{code}"
                )
            errors.append(
                AgentError(
                    code=code,
                    message=str(error.get("message") or "工具调用失败"),
                    retryable=bool(error.get("retryable")),
                    details=error.get("details") or {},
                )
            )
            continue

        policy = envelope.get("data_policy") or {}
        if policy.get("ai_may_generate_market_data") is not False:
            failure_statuses.append(AgentStatus.FAILED)
            if execution.required:
                required_failure_statuses.append(AgentStatus.FAILED)
            errors.append(
                AgentError(
                    code="INVALID_DATA_POLICY",
                    message="工具结果缺少禁止模型生成市场数据的策略",
                )
            )
            continue
        if execution.source == "web" and policy.get("numeric_allowed") is not False:
            failure_statuses.append(AgentStatus.FAILED)
            if execution.required:
                required_failure_statuses.append(AgentStatus.FAILED)
            errors.append(
                AgentError(
                    code="WEB_NUMERIC_POLICY_VIOLATION",
                    message="Web 工具结果不允许作为市场数值来源",
                )
            )
            continue

        audit_records = envelope.get("data_audit") or []
        audit_ref = _audit_ref(audit_records)
        if execution.source == "fund" and audit_ref is None:
            failure_statuses.append(AgentStatus.FAILED)
            if execution.required:
                required_failure_statuses.append(AgentStatus.FAILED)
            errors.append(
                AgentError(
                    code="MISSING_DATA_AUDIT",
                    message="市场工具结果缺少通过校验的审计指纹",
                )
            )
            continue

        success_count += 1
        for item in envelope.get("data_warnings") or []:
            warnings.append(_warning_text(item))
        extracted = _extract_facts(execution, audit_ref)
        if execution.tool is RegisteredTool.WEB_SEARCH and not extracted:
            warnings.append(
                "网页搜索成功，但没有符合来源类别的相关公开链接。"
            )
        for fact in extracted:
            fact.audit_ref = (
                _audit_ref_for_fact(
                    audit_records,
                    execution.tool,
                    fact.field_path,
                )
                or fact.audit_ref
            )
        facts.extend(extracted)

    facts = facts[:maximum_facts]
    if required_failure_statuses:
        status = _highest_priority_status(required_failure_statuses)
    elif failure_statuses and success_count == 0:
        status = _highest_priority_status(failure_statuses)
    elif failure_statuses or warnings:
        status = AgentStatus.PARTIAL_RESULT
        limitations.append("部分工具或可选数据不可用，仅展示通过校验的事实。")
    elif success_count:
        status = AgentStatus.RUNNING
    else:
        status = AgentStatus.CANNOT_CONFIRM
        errors.append(
            AgentError(
                code="NO_TOOL_RESULTS",
                message="没有可验证的工具结果",
            )
        )

    if not facts and status in {AgentStatus.RUNNING, AgentStatus.PARTIAL_RESULT}:
        limitations.append("工具调用成功，但没有可用于当前回答的稳定事实字段。")
    return status, facts, limitations, warnings, errors


def validate_associations(
    associations: list[AssociationDraft],
    facts: list[FactRef],
) -> tuple[list[AssociationDraft], list[str]]:
    known = {fact.fact_id for fact in facts}
    valid: list[AssociationDraft] = []
    warnings: list[str] = []
    for association in associations:
        refs = association.evidence_refs
        if len(set(refs)) < 2 or any(ref not in known for ref in refs):
            warnings.append("关联说明引用了不存在或不足两个事实，已移除。")
            continue
        if re.search(r"\d", association.explanation):
            warnings.append("关联说明包含模型生成数字，已移除。")
            continue
        if any(
            pattern.search(association.explanation)
            for pattern in _FORBIDDEN_ASSOCIATION_PATTERNS
        ):
            warnings.append("关联说明包含因果或确定性交易表达，已移除。")
            continue
        valid.append(association)
    return valid, warnings


def _audit_ref(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("validation") != "passed":
            continue
        value = record.get("frame_sha256") or record.get("response_sha256")
        if value:
            return str(value)
    return None


def _audit_ref_for_fact(
    records: list[dict[str, Any]],
    tool: RegisteredTool,
    field_path: str,
) -> str | None:
    candidates: list[tuple[str, str | None]] = []
    if ".pe_ttm." in field_path:
        candidates = [
            (
                (
                    "stock_zh_valuation_baidu"
                    if tool is RegisteredTool.STOCK_VALUATION
                    else "stock_index_pe_lg"
                ),
                "市盈率" if tool is RegisteredTool.STOCK_VALUATION else None,
            )
        ]
    elif ".pb." in field_path:
        candidates = [
            (
                (
                    "stock_zh_valuation_baidu"
                    if tool is RegisteredTool.STOCK_VALUATION
                    else "stock_index_pb_lg"
                ),
                "市净率" if tool is RegisteredTool.STOCK_VALUATION else None,
            )
        ]
    elif "stock_price" in field_path:
        candidates = [("stock_zh_a_daily", None)]
    elif "index_points" in field_path:
        candidates = [("stock_zh_index_daily", None)]
    elif "market_snapshot" in field_path:
        candidates = [("fund_etf_spot_em", None)]
    elif "availability" in field_path:
        candidates = [
            ("fund_purchase_em", None),
            ("tool_trade_date_hist_sina", None),
        ]
    elif tool is RegisteredTool.FUND_SEARCH:
        candidates = [("fund_name_em", None)]
    elif tool in {RegisteredTool.FUND_ANALYZE, RegisteredTool.FUND_COMPARE}:
        candidates = [
            ("fund_open_fund_info_em", None),
            ("fund_etf_hist_em", None),
            ("fund_lof_hist_em", None),
            ("fund_etf_hist_sina", None),
        ]

    for interface, indicator in candidates:
        for record in records:
            if record.get("validation") != "passed":
                continue
            if record.get("interface") != interface:
                continue
            if indicator is not None:
                parameters = record.get("parameters") or {}
                kwargs = parameters.get("kwargs") or {}
                if indicator not in str(kwargs.get("indicator") or ""):
                    continue
            value = record.get("frame_sha256") or record.get("response_sha256")
            if value:
                return str(value)
    return None


def _warning_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        code = value.get("error", {}).get("code") or value.get("code")
        interface = value.get("interface")
        return " / ".join(str(item) for item in (interface, code) if item) or json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
        )
    return str(value)


def _extract_facts(
    execution: ToolExecution,
    audit_ref: str | None,
) -> list[FactRef]:
    data = execution.envelope.get("data") or {}
    queried_at = str(execution.envelope.get("queried_at") or "")
    tool = execution.tool

    if tool is RegisteredTool.FUND_ANALYZE:
        specs = [
            ("fund.code", "基金代码", None, "entity"),
            ("fund.name", "基金名称", None, "entity"),
            (
                "analysis.performance.annualized_volatility_pct",
                "年化波动",
                "%",
                "market",
            ),
            (
                "analysis.performance.current_drawdown_pct",
                "当前回撤",
                "%",
                "market",
            ),
            (
                "analysis.performance.max_drawdown_pct",
                "最大回撤",
                "%",
                "market",
            ),
            (
                "analysis.performance.history_position_percentile",
                "历史位置分位",
                "%",
                "market",
            ),
            (
                "analysis.holding_experience.annualized_return_pct",
                "观察期年化收益",
                "%",
                "market",
            ),
            (
                "analysis.valuation.pe_ttm.percentile",
                "跟踪指数 PE TTM 历史分位",
                "%",
                "market",
            ),
            (
                "analysis.valuation.pb.percentile",
                "跟踪指数 PB 历史分位",
                "%",
                "market",
            ),
            (
                "analysis.trading_context.market_snapshot.premium_rate_pct",
                "ETF 场内溢价",
                "%",
                "market",
            ),
        ]
        as_of = _first_value(
            data,
            "analysis.data_quality.latest_date",
            "metrics.latest_date",
        )
        return _facts_from_specs(tool, data, specs, as_of, audit_ref)

    if tool in {
        RegisteredTool.INDEX_VALUATION,
        RegisteredTool.STOCK_VALUATION,
    }:
        identity_path = (
            "index.name"
            if tool is RegisteredTool.INDEX_VALUATION
            else "stock.name"
        )
        identity_label = (
            "指数名称"
            if tool is RegisteredTool.INDEX_VALUATION
            else "股票名称"
        )
        specs = [
            (identity_path, identity_label, None, "entity"),
            ("summary.pe_ttm.current", "PE TTM 当前值", "倍", "market"),
            ("summary.pe_ttm.percentile", "PE TTM 历史分位", "%", "market"),
            ("summary.pb.current", "PB 当前值", "倍", "market"),
            ("summary.pb.percentile", "PB 历史分位", "%", "market"),
        ]
        if tool is RegisteredTool.STOCK_VALUATION:
            specs.append(
                ("summary.stock_price.current", "前复权价格", "元", "market")
            )
        else:
            specs.append(
                (
                    "charts.index_points.current",
                    "指数点位",
                    "点",
                    "market",
                )
            )
        as_of = _first_value(data, "lookback.latest_date")
        return _facts_from_specs(tool, data, specs, as_of, audit_ref)

    if tool is RegisteredTool.FUND_STATUS:
        specs = [
            ("fund.code", "基金代码", None, "entity"),
            ("fund.name", "基金名称", None, "entity"),
            (
                "availability.off_exchange.subscription_status",
                "申购状态",
                None,
                "market",
            ),
            (
                "availability.off_exchange.redemption_status",
                "赎回状态",
                None,
                "market",
            ),
            (
                "availability.off_exchange.daily_limit_cny",
                "单日申购限额",
                "元",
                "market",
            ),
            (
                "availability.exchange.market_session.state",
                "标准交易时段状态",
                None,
                "market",
            ),
        ]
        return _facts_from_specs(tool, data, specs, queried_at, audit_ref)

    if tool is RegisteredTool.FUND_SEARCH:
        return _search_facts(tool, data, audit_ref, queried_at)

    if tool is RegisteredTool.FUND_COMPARE:
        return _compare_facts(tool, data, audit_ref)

    if tool in {RegisteredTool.WEB_SEARCH, RegisteredTool.DOCUMENT_READ}:
        return _web_facts(tool, data, audit_ref, queried_at)

    return []


def _facts_from_specs(
    tool: RegisteredTool,
    data: dict[str, Any],
    specs: list[tuple[str, str, str | None, str]],
    as_of: Any,
    audit_ref: str | None,
) -> list[FactRef]:
    facts: list[FactRef] = []
    for path, label, unit, source_kind in specs:
        value = _get_path(data, path)
        if value is None or isinstance(value, (dict, list)):
            continue
        facts.append(
            _fact(
                tool,
                f"data.{path}",
                label,
                value,
                unit,
                as_of,
                audit_ref,
                source_kind,
            )
        )
    return facts


def _search_facts(
    tool: RegisteredTool,
    data: dict[str, Any],
    audit_ref: str | None,
    as_of: str,
) -> list[FactRef]:
    facts: list[FactRef] = []
    for index, item in enumerate(data.get("results") or []):
        if not isinstance(item, dict):
            continue
        for key, label in (("code", "基金代码"), ("name", "基金名称")):
            value = item.get(key)
            if value:
                facts.append(
                    _fact(
                        tool,
                        f"data.results.{index}.{key}",
                        label,
                        value,
                        None,
                        as_of,
                        audit_ref,
                        "entity",
                    )
                )
    return facts


def _compare_facts(
    tool: RegisteredTool,
    data: dict[str, Any],
    audit_ref: str | None,
) -> list[FactRef]:
    facts: list[FactRef] = []
    for index, item in enumerate(data.get("results") or []):
        if not isinstance(item, dict) or not item.get("ok"):
            continue
        name = _get_path(item, "fund.name") or f"基金 {index + 1}"
        as_of = _first_value(
            item,
            "analysis.data_quality.latest_date",
            "metrics.latest_date",
        )
        specs = [
            (
                "analysis.performance.annualized_volatility_pct",
                f"{name} 年化波动",
                "%",
                "market",
            ),
            (
                "analysis.performance.max_drawdown_pct",
                f"{name} 最大回撤",
                "%",
                "market",
            ),
            (
                "analysis.holding_experience.annualized_return_pct",
                f"{name} 观察期年化收益",
                "%",
                "market",
            ),
        ]
        for fact in _facts_from_specs(tool, item, specs, as_of, audit_ref):
            fact.field_path = fact.field_path.replace(
                "data.",
                f"data.results.{index}.",
                1,
            )
            fact.fact_id = _fact_id(tool, fact.field_path)
            facts.append(fact)
    return facts


def _web_facts(
    tool: RegisteredTool,
    data: dict[str, Any],
    audit_ref: str | None,
    as_of: str,
) -> list[FactRef]:
    if tool is RegisteredTool.DOCUMENT_READ:
        title = data.get("title")
        content = str(data.get("content") or "")[:1000]
        if not title or not content:
            return []
        final_url = str(data.get("final_url") or data.get("requested_url") or "")
        return [
            _fact(
                tool,
                "data.content",
                str(title),
                {
                    "title": str(title),
                    "url": final_url,
                    "snippet": content,
                    "source_type": "other",
                    "domain": None,
                    "published_at": None,
                },
                None,
                as_of,
                audit_ref,
                "background",
            )
        ]

    facts: list[FactRef] = []
    query = str(data.get("query") or "")
    query_ref = hashlib.sha256(query.encode("utf-8")).hexdigest()[:10]
    for index, item in enumerate(data.get("results") or []):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if title and url:
            facts.append(
                _fact(
                    tool,
                    f"data.searches.{query_ref}.results.{index}",
                    title,
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "source_type": str(
                            item.get("source_type") or "other"
                        ),
                        "domain": item.get("domain"),
                        "published_at": item.get("published_at"),
                    },
                    None,
                    item.get("published_at") or as_of,
                    audit_ref,
                    "background",
                )
            )
    return facts


def _fact(
    tool: RegisteredTool,
    field_path: str,
    label: str,
    value: Any,
    unit: str | None,
    as_of: Any,
    audit_ref: str | None,
    source_kind: str,
) -> FactRef:
    return FactRef(
        fact_id=_fact_id(tool, field_path),
        tool=tool,
        field_path=field_path,
        label=label,
        value=value,
        unit=unit,
        as_of=str(as_of) if as_of else None,
        audit_ref=audit_ref,
        source_kind=source_kind,
    )


def _fact_id(tool: RegisteredTool, field_path: str) -> str:
    digest = hashlib.sha256(
        f"{tool.value}:{field_path}".encode("utf-8")
    ).hexdigest()[:12]
    return f"fact_{digest}"


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _first_value(data: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = _get_path(data, path)
        if value is not None:
            return value
    return None


def _highest_priority_status(statuses: list[AgentStatus]) -> AgentStatus:
    priorities = (
        AgentStatus.NEED_CLARIFICATION,
        AgentStatus.NOT_FOUND,
        AgentStatus.UNSUPPORTED,
        AgentStatus.STALE_DATA,
        AgentStatus.FAILED,
        AgentStatus.CANNOT_CONFIRM,
    )
    return next(
        (status for status in priorities if status in statuses),
        AgentStatus.CANNOT_CONFIRM,
    )
