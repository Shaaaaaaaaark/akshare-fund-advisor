"""Serializable state carried through the LangGraph workflow."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    schema_version: str
    task_id: str
    conversation_id: str
    trace_id: str
    user_query: str
    resolved_query: str
    conversation_history: list[dict[str, Any]]
    status: str
    prompt_versions: dict[str, str]

    intent: str
    intent_confidence: float
    entities: list[dict[str, Any]]
    policy_violation: str | None
    clarification: dict[str, Any] | None

    user_context: dict[str, Any]
    tool_plan: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    external_context: list[dict[str, Any]]

    evidence: list[dict[str, Any]]
    gate_decision: dict[str, Any]
    suitability: dict[str, Any]
    claims: list[dict[str, Any]]
    final_report: dict[str, Any]
    warnings: list[str]
    errors: list[dict[str, Any]]
