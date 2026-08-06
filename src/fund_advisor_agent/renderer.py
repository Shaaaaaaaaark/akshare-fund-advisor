"""Deterministic user-facing response rendering."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from .policies import error_message_for_status
from .state import AgentState, AgentStatus, AssociationDraft, FactRef


def render_answer(state: AgentState) -> str:
    if state.status in {
        AgentStatus.NEED_CLARIFICATION,
        AgentStatus.NOT_FOUND,
        AgentStatus.UNSUPPORTED,
        AgentStatus.CANNOT_CONFIRM,
        AgentStatus.STALE_DATA,
        AgentStatus.FAILED,
    }:
        details = state.errors[0].details if state.errors else {}
        return error_message_for_status(state.status, details)

    sections = [
        _render_facts(state.facts),
        _render_background_sources(state.facts),
        _render_associations(state.associations, state.facts),
        _render_limitations(state.limitations, state.warnings),
        (
            "## 条件式参考\n"
            "以上内容仅用于个人研究。历史统计与关联关系不代表因果，也不预测未来表现。"
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def _render_facts(facts: list[FactRef]) -> str:
    if not facts:
        return "## 事实\n- 当前没有可展示的稳定事实字段。"
    stable_facts = [
        fact for fact in facts if fact.source_kind != "background"
    ]
    if not stable_facts:
        return ""
    lines = ["## 事实"]
    for fact in stable_facts:
        value = _display_value(fact.value)
        suffix = f" {fact.unit}" if fact.unit else ""
        date_text = f"，截至 {fact.as_of}" if fact.as_of else ""
        lines.append(
            f"- {fact.label}：{value}{suffix}{date_text}"
            f"（{fact.tool.value}:{fact.field_path}）"
        )
    return "\n".join(lines)


def _render_background_sources(facts: list[FactRef]) -> str:
    source_labels = {
        "official": "官方/监管",
        "research": "机构研究",
        "media": "财经媒体",
        "creator": "博主/社区",
        "other": "其他公开来源",
    }
    lines = [
        "## 相关文章与公开观点",
        "- 以下链接仅作 Web 非数值背景，不作为市场事实；来源分类不代表身份认证。",
    ]
    seen_urls: set[str] = set()
    for fact in facts:
        if fact.source_kind != "background" or not isinstance(fact.value, dict):
            continue
        url = _safe_public_link(str(fact.value.get("url") or ""))
        if url is None or url in seen_urls:
            continue
        seen_urls.add(url)
        title = _single_line(
            str(fact.value.get("title") or fact.label or "公开网页")
        )
        source_type = str(fact.value.get("source_type") or "other")
        source_label = source_labels.get(source_type, source_labels["other"])
        domain = str(
            fact.value.get("domain") or urlsplit(url).hostname or ""
        )
        domain_text = f"，{domain}" if domain else ""
        lines.append(
            f"- [{source_label}] {title}：<{url}>（{fact.tool.value}{domain_text}）"
        )
    return "\n".join(lines) if len(lines) > 2 else ""


def _render_associations(
    associations: list[AssociationDraft],
    facts: list[FactRef],
) -> str:
    if not associations:
        return "## 关联说明\n- 当前事实不足以形成额外关联说明。"
    labels = {fact.fact_id: fact.label for fact in facts}
    lines = ["## 关联说明"]
    for association in associations:
        refs = "、".join(
            labels.get(fact_id, fact_id)
            for fact_id in association.evidence_refs
        )
        lines.append(
            f"- {association.explanation} "
            f"依据：{refs}；关系：{association.relationship.value}；"
            f"置信度：{association.confidence.value}。"
        )
    return "\n".join(lines)


def _render_limitations(
    limitations: list[str],
    warnings: list[str],
) -> str:
    items = list(dict.fromkeys([*limitations, *warnings]))
    if not items:
        return "## 限制\n- 历史数据和统计口径不能证明因果关系。"
    return "\n".join(["## 限制", *(f"- {item}" for item in items)])


def _display_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _safe_public_link(value: str) -> str | None:
    if any(character.isspace() for character in value):
        return None
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return value.replace("<", "%3C").replace(">", "%3E")


def _single_line(value: str) -> str:
    return " ".join(value.split())[:300]
