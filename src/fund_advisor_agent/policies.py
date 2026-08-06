"""Deterministic intent, tool and error policies."""

from __future__ import annotations

import re
from typing import Any

from .state import (
    AgentStatus,
    Intent,
    RegisteredTool,
    ToolCallSpec,
)

_URL_PATTERN = re.compile(r"https?://[^\s]+")
_CODE_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
_QUOTED_PATTERN = re.compile(r"[“\"']([^”\"']+)[”\"']")
_KNOWN_INDEXES = (
    "沪深300",
    "中证500",
    "中证1000",
    "上证50",
    "创业板",
    "科创50",
)
_UNSUPPORTED_TERMS = (
    "预测涨跌",
    "目标价",
    "稳赚",
    "保证收益",
    "自动交易",
    "自动下单",
)


def classify_question(question: str) -> tuple[Intent, list[str]]:
    text = question.strip()
    lowered = text.lower()
    urls = _URL_PATTERN.findall(text)
    codes = _CODE_PATTERN.findall(text)
    quoted = _QUOTED_PATTERN.findall(text)
    known_indexes = [name for name in _KNOWN_INDEXES if name in text]
    entities = _deduplicate([*codes, *known_indexes, *quoted])

    if any(term in text for term in _UNSUPPORTED_TERMS):
        return Intent.UNSUPPORTED, entities
    if urls and any(term in text for term in ("文档", "合同", "公告", "说明书", "读取")):
        return Intent.DOCUMENT_READ, urls
    if any(term in text for term in ("新闻", "政策", "监管", "网页", "搜索网络")):
        return Intent.WEB_RESEARCH, entities
    if any(term in text for term in ("比较", "对比", "怎么选", "哪个好")):
        return Intent.FUND_COMPARE, entities
    if any(term in text for term in ("申购", "赎回", "限购", "交易状态", "开市")):
        return Intent.FUND_STATUS, entities
    if known_indexes or "指数估值" in text:
        return Intent.INDEX_VALUATION, entities
    if (
        any(term in text for term in ("个股", "股票", "股价", "市盈率", "市净率"))
        or re.search(r"(?<![a-z])(?:pe|pb)(?![a-z])", lowered)
    ):
        return Intent.STOCK_VALUATION, entities
    if any(term in text for term in ("搜索基金", "查找基金", "有哪些基金", "基金列表")):
        return Intent.FUND_SEARCH, entities
    return Intent.FUND_ANALYSIS, entities


def should_use_intent_model(
    intent: Intent,
    entities: list[str],
) -> bool:
    return intent is Intent.FUND_ANALYSIS and not entities


def plan_tools(
    intent: Intent,
    question: str,
    entities: list[str],
    *,
    include_asset_background: bool = False,
) -> tuple[list[ToolCallSpec], AgentStatus, list[str]]:
    if intent is Intent.UNSUPPORTED:
        return [], AgentStatus.UNSUPPORTED, ["当前不支持收益预测或自动交易请求。"]

    years = _requested_years(question)
    subject = entities[0] if entities else _fallback_subject(question)

    if intent is Intent.DOCUMENT_READ:
        urls = _URL_PATTERN.findall(question)
        if not urls:
            return [], AgentStatus.NEED_CLARIFICATION, ["请提供需要读取的公开文档 URL。"]
        return [
            ToolCallSpec(
                tool=RegisteredTool.DOCUMENT_READ,
                source="web",
                arguments={"url": urls[0], "max_chars": 20000},
            )
        ], AgentStatus.RUNNING, []

    if intent is Intent.WEB_RESEARCH:
        return [
            ToolCallSpec(
                tool=RegisteredTool.WEB_SEARCH,
                source="web",
                arguments={"query": question, "max_results": 5},
            )
        ], AgentStatus.RUNNING, []

    if intent is Intent.FUND_COMPARE:
        if len(entities) < 2:
            return (
                [],
                AgentStatus.NEED_CLARIFICATION,
                ["请提供 2 到 5 个明确基金代码后再比较。"],
            )
        return [
            ToolCallSpec(
                tool=RegisteredTool.FUND_COMPARE,
                source="fund",
                arguments={"funds": entities[:5], "years": _fund_years(years)},
            )
        ], AgentStatus.RUNNING, []

    if intent is Intent.FUND_SEARCH:
        query = subject or question
        return [
            ToolCallSpec(
                tool=RegisteredTool.FUND_SEARCH,
                source="fund",
                arguments={"query": query, "limit": 10},
            )
        ], AgentStatus.RUNNING, []

    if not subject:
        return [], AgentStatus.NEED_CLARIFICATION, ["请提供明确的基金、指数或股票名称/代码。"]

    if intent is Intent.FUND_STATUS:
        call = ToolCallSpec(
            tool=RegisteredTool.FUND_STATUS,
            source="fund",
            arguments={"fund": subject},
        )
    elif intent is Intent.INDEX_VALUATION:
        call = ToolCallSpec(
            tool=RegisteredTool.INDEX_VALUATION,
            source="fund",
            arguments={
                "index": subject,
                "years": _index_years(years),
                "max_points": 600,
            },
        )
    elif intent is Intent.STOCK_VALUATION:
        call = ToolCallSpec(
            tool=RegisteredTool.STOCK_VALUATION,
            source="fund",
            arguments={
                "stock": subject,
                "years": _stock_years(years),
                "max_points": 600,
            },
        )
    else:
        call = ToolCallSpec(
            tool=RegisteredTool.FUND_ANALYZE,
            source="fund",
            arguments={"fund": subject, "years": _fund_years(years)},
        )
    plan = [call]
    if include_asset_background and intent in {
        Intent.FUND_ANALYSIS,
        Intent.STOCK_VALUATION,
    }:
        plan.extend(_asset_background_calls(intent, subject))
    return plan, AgentStatus.RUNNING, []


def status_for_error(code: str) -> AgentStatus:
    if code in {"AMBIGUOUS_FUND", "ENTITY_AMBIGUOUS"}:
        return AgentStatus.NEED_CLARIFICATION
    if code in {"FUND_NOT_FOUND", "STOCK_NOT_FOUND", "FUND_RATING_NOT_FOUND"}:
        return AgentStatus.NOT_FOUND
    if code in {
        "INDEX_NOT_SUPPORTED",
        "STOCK_MARKET_UNSUPPORTED",
        "UNSUPPORTED_EXCHANGE_FUND",
        "WEB_RESEARCH_DISABLED",
    }:
        return AgentStatus.UNSUPPORTED
    if code in {"STALE_OR_INVALID_DATA", "STALE_DATA"}:
        return AgentStatus.STALE_DATA
    return AgentStatus.CANNOT_CONFIRM


def error_message_for_status(
    status: AgentStatus,
    details: dict[str, Any] | None = None,
) -> str:
    if status is AgentStatus.NEED_CLARIFICATION:
        candidates = (details or {}).get("candidates") or []
        suffix = f" 候选：{candidates}" if candidates else ""
        return f"存在多个候选，请确认具体标的。{suffix}".strip()
    if status is AgentStatus.NOT_FOUND:
        return "目录查询成功，但未找到该标的。"
    if status is AgentStatus.UNSUPPORTED:
        return "当前数据能力不支持该请求。"
    if status is AgentStatus.STALE_DATA:
        return "数据已过期，不用于当前判断。"
    if status is AgentStatus.FAILED:
        return "响应未通过校验，已阻止输出。"
    return "上游数据当前不可用，当前无法确认。"


def _requested_years(question: str) -> int | None:
    matched = re.search(r"(?<!\d)(1|3|5|10|20)\s*年", question)
    return int(matched.group(1)) if matched else None


def _fund_years(years: int | None) -> int:
    return years if years in {1, 3, 5} else 3


def _stock_years(years: int | None) -> int:
    return years if years in {1, 3, 5, 10} else 10


def _index_years(years: int | None) -> int:
    return years if years in {3, 5, 10, 20} else 10


def _asset_background_calls(
    intent: Intent,
    subject: str,
) -> list[ToolCallSpec]:
    asset_type = "股票" if intent is Intent.STOCK_VALUATION else "基金"
    search_subject = " ".join(subject.replace('"', " ").split())
    queries = (
        (
            f'"{search_subject}" {asset_type} 深度分析 研究报告 财经媒体',
            ["official", "research", "media"],
        ),
        (
            f'"{search_subject}" {asset_type} 观点 分享 '
            "site:xueqiu.com OR site:zhihu.com",
            ["creator"],
        ),
    )
    return [
        ToolCallSpec(
            tool=RegisteredTool.WEB_SEARCH,
            source="web",
            arguments={
                "query": query,
                "max_results": 5,
                "source_types": source_types,
            },
            required=False,
        )
        for query, source_types in queries
    ]


def _fallback_subject(question: str) -> str:
    text = question
    for term in (
        "帮我",
        "请",
        "分析",
        "查询",
        "看看",
        "基金",
        "股票",
        "个股",
        "指数",
        "估值",
        "风险",
        "如何",
        "怎么样",
    ):
        text = text.replace(term, " ")
    text = re.sub(r"\s+", " ", text).strip(" ，。？?")
    return text[:100]


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))
