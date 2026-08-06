"""Fixed acyclic LangGraph assembly and execution."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from fund_advisor_mcp.config import AppConfig, get_config
from fund_advisor_mcp.fund.client import FundToolClient, build_fund_tool_client
from fund_advisor_mcp.web.client import (
    WebResearchClient,
    build_web_research_client,
)

from .associations import AssociationModel
from .model_client import (
    IntentClassifier,
    build_association_model,
    build_intent_classifier,
)
from .nodes import AgentNodes
from .state import AgentResponse, AgentState, AgentStatus


def build_agent_graph(
    *,
    config: AppConfig | None = None,
    fund_client: FundToolClient | None = None,
    web_client: WebResearchClient | None = None,
    association_model: AssociationModel | None = None,
    intent_classifier: IntentClassifier | None = None,
) -> Any:
    settings = config or get_config()
    selected_model = association_model
    if selected_model is None:
        model_config = settings.model.model_copy(
            update={
                "enabled": (
                    settings.model.enabled
                    and settings.agent.use_llm_for_associations
                )
            }
        )
        selected_model = build_association_model(model_config)
    selected_intent_classifier = intent_classifier
    if selected_intent_classifier is None:
        selected_intent_classifier = build_intent_classifier(
            settings.model,
            enabled=settings.agent.use_llm_for_intent,
        )
    nodes = AgentNodes(
        fund_client or build_fund_tool_client(settings),
        web_client or build_web_research_client(settings),
        selected_model,
        selected_intent_classifier,
        settings,
    )

    builder = StateGraph(AgentState)
    builder.add_node("CLASSIFY", nodes.classify)
    builder.add_node("PLAN_REGISTERED_TOOLS", nodes.plan_registered_tools)
    builder.add_node("CALL_MCP", nodes.call_mcp)
    builder.add_node(
        "VALIDATE_TOOL_ENVELOPES",
        nodes.validate_tool_envelopes,
    )
    builder.add_node("BUILD_ASSOCIATIONS", nodes.build_associations)
    builder.add_node("VALIDATE_RESPONSE", nodes.validate_response)
    builder.add_node("RENDER_ANSWER", nodes.render_answer)

    builder.add_edge(START, "CLASSIFY")
    builder.add_edge("CLASSIFY", "PLAN_REGISTERED_TOOLS")
    builder.add_conditional_edges(
        "PLAN_REGISTERED_TOOLS",
        _route_after_plan,
        {
            "call_mcp": "CALL_MCP",
            "render": "RENDER_ANSWER",
        },
    )
    builder.add_edge("CALL_MCP", "VALIDATE_TOOL_ENVELOPES")
    builder.add_conditional_edges(
        "VALIDATE_TOOL_ENVELOPES",
        _route_after_tool_validation,
        {
            "associate": "BUILD_ASSOCIATIONS",
            "render": "RENDER_ANSWER",
        },
    )
    builder.add_edge("BUILD_ASSOCIATIONS", "VALIDATE_RESPONSE")
    builder.add_edge("VALIDATE_RESPONSE", "RENDER_ANSWER")
    builder.add_edge("RENDER_ANSWER", END)
    return builder.compile()


async def run_agent(
    question: str,
    *,
    graph: Any | None = None,
) -> AgentResponse:
    compiled = graph or build_agent_graph()
    result = await compiled.ainvoke(AgentState(question=question))
    state = (
        result
        if isinstance(result, AgentState)
        else AgentState.model_validate(result)
    )
    return AgentResponse(
        status=state.status,
        facts=state.facts,
        associations=state.associations,
        limitations=state.limitations,
        warnings=state.warnings,
        errors=state.errors,
        answer=state.final_answer or "",
    )


def _route_after_plan(value: AgentState | dict[str, Any]) -> str:
    status = _status(value)
    return "call_mcp" if status is AgentStatus.RUNNING else "render"


def _route_after_tool_validation(
    value: AgentState | dict[str, Any],
) -> str:
    status = _status(value)
    if status in {AgentStatus.RUNNING, AgentStatus.PARTIAL_RESULT}:
        return "associate"
    return "render"


def _status(value: AgentState | dict[str, Any]) -> AgentStatus:
    if isinstance(value, AgentState):
        return value.status
    return AgentStatus(value.get("status", AgentStatus.RUNNING))
