"""Single-responsibility nodes for the fixed LangGraph workflow."""

from __future__ import annotations

import asyncio
from typing import Any

from fund_advisor_mcp.config import AppConfig, get_config

from .associations import AssociationModel
from .clients import McpToolClient
from .model_client import IntentClassifier
from .policies import (
    classify_question,
    plan_tools,
    should_use_intent_model,
)
from .renderer import render_answer
from .state import (
    AgentState,
    AgentStatus,
    AssociationDraft,
    RegisteredTool,
    ToolCallSpec,
    ToolExecution,
)
from .validator import validate_associations, validate_tool_results


class AgentNodes:
    def __init__(
        self,
        fund_client: McpToolClient,
        web_client: McpToolClient,
        association_model: AssociationModel,
        intent_classifier: IntentClassifier | None,
        config: AppConfig | None = None,
    ) -> None:
        self._fund_client = fund_client
        self._web_client = web_client
        self._association_model = association_model
        self._intent_classifier = intent_classifier
        self._config = config or get_config()

    async def classify(self, value: AgentState) -> dict[str, Any]:
        state = _state(value)
        intent, entities = classify_question(state.question)
        warnings = list(state.warnings)
        if (
            self._intent_classifier is not None
            and should_use_intent_model(intent, entities)
        ):
            try:
                decision = await self._intent_classifier.classify(
                    state.question
                )
                if decision.confidence >= 0.7:
                    intent = decision.intent
                    entities = decision.entities
                else:
                    warnings.append(
                        "模型意图置信度不足，已保留规则分类结果。"
                    )
            except Exception as exc:
                warnings.append(
                    "意图模型不可用，已保留规则分类结果："
                    f"{type(exc).__name__}"
                )
        return {
            "intent": intent,
            "entities": entities,
            "status": AgentStatus.RUNNING,
            "warnings": warnings,
        }

    async def plan_registered_tools(
        self,
        value: AgentState,
    ) -> dict[str, Any]:
        state = _state(value)
        if state.intent is None:
            return {
                "status": AgentStatus.FAILED,
                "limitations": ["问题尚未完成意图分类。"],
            }
        plan, status, limitations = plan_tools(
            state.intent,
            state.question,
            state.entities,
            include_asset_background=self._config.web_research.enabled,
        )
        maximum = self._config.agent.maximum_tool_calls
        warnings = list(state.warnings)
        if len(plan) > maximum:
            plan = plan[:maximum]
            warnings.append("工具计划超过上限，已按注册顺序截断。")
        return {
            "tool_plan": plan,
            "status": status,
            "limitations": [*state.limitations, *limitations],
            "warnings": warnings,
        }

    async def call_mcp(self, value: AgentState) -> dict[str, Any]:
        state = _state(value)
        semaphore = asyncio.Semaphore(self._config.mcp.concurrency)

        async def execute(call: ToolCallSpec) -> ToolExecution:
            async with semaphore:
                try:
                    if call.source == "fund":
                        envelope = await self._fund_client.call(
                            call.tool.value,
                            call.arguments,
                        )
                    else:
                        envelope = await self._web_client.call(
                            call.tool.value,
                            call.arguments,
                        )
                    payload = envelope.model_dump(mode="json")
                except Exception as exc:
                    payload = _client_error_envelope(
                        call.tool,
                        call.source,
                        exc,
                    )
            return ToolExecution(
                tool=call.tool,
                arguments=call.arguments,
                source=call.source,
                required=call.required,
                envelope=payload,
            )

        executions = list(
            await asyncio.gather(*(execute(call) for call in state.tool_plan))
        )
        return {"tool_results": executions}

    async def validate_tool_envelopes(
        self,
        value: AgentState,
    ) -> dict[str, Any]:
        state = _state(value)
        status, facts, limitations, warnings, errors = validate_tool_results(
            state.tool_results,
            maximum_facts=self._config.agent.maximum_facts,
        )
        return {
            "status": status,
            "facts": facts,
            "limitations": [*state.limitations, *limitations],
            "warnings": [*state.warnings, *warnings],
            "errors": [*state.errors, *errors],
        }

    async def build_associations(
        self,
        value: AgentState,
    ) -> dict[str, Any]:
        state = _state(value)
        try:
            raw_associations = await self._association_model.build_associations(
                state.facts,
                state.question,
            )
            associations = [
                item
                if isinstance(item, AssociationDraft)
                else AssociationDraft.model_validate(item)
                for item in raw_associations
            ]
            return {"associations": associations}
        except Exception as exc:
            return {
                "associations": [],
                "warnings": [
                    *state.warnings,
                    f"关联模型不可用，已回退为事实报告：{type(exc).__name__}",
                ],
                "status": (
                    AgentStatus.PARTIAL_RESULT
                    if state.status is AgentStatus.RUNNING
                    else state.status
                ),
            }

    async def validate_response(
        self,
        value: AgentState,
    ) -> dict[str, Any]:
        state = _state(value)
        associations, warnings = validate_associations(
            state.associations,
            state.facts,
        )
        status = state.status
        if warnings and status is AgentStatus.RUNNING:
            status = AgentStatus.PARTIAL_RESULT
        return {
            "associations": associations,
            "warnings": [*state.warnings, *warnings],
            "status": status,
        }

    async def render_answer(self, value: AgentState) -> dict[str, Any]:
        state = _state(value)
        status = (
            AgentStatus.COMPLETED
            if state.status is AgentStatus.RUNNING
            else state.status
        )
        rendered_state = state.model_copy(update={"status": status})
        return {
            "status": status,
            "final_answer": render_answer(rendered_state),
        }


def _state(value: AgentState | dict[str, Any]) -> AgentState:
    if isinstance(value, AgentState):
        return value
    return AgentState.model_validate(value)


def _client_error_envelope(
    tool: RegisteredTool,
    source: str,
    exc: Exception,
) -> dict[str, Any]:
    data_policy: dict[str, Any] = {"ai_may_generate_market_data": False}
    if source == "web":
        data_policy.update(
            {
                "numeric_allowed": False,
                "may_override_market_tools": False,
                "purpose": "background_only",
            }
        )
    return {
        "schema_version": "1.0",
        "tool": tool.value,
        "ok": False,
        "data": None,
        "sources": [],
        "data_audit": [],
        "data_warnings": [],
        "data_policy": data_policy,
        "error": {
            "code": "MCP_CLIENT_ERROR",
            "message": "MCP 客户端调用失败",
            "retryable": True,
            "details": {"reason": type(exc).__name__},
        },
    }
