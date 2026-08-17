"""Shared chat application service for web and terminal clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fund_advisor_agent.graph import (
    build_agent_graph,
    response_from_state,
    stream_agent,
)
from fund_advisor_agent.state import AgentState, AgentStatus
from fund_advisor_mcp.config import AppConfig, get_config

from .schemas import SessionView, StreamEvent
from .sessions import InMemorySessionStore

_NEXT_NODE_MESSAGES = {
    "CLASSIFY": "正在制定研究步骤",
    "PLAN_REGISTERED_TOOLS": "正在查询可信数据",
    "CALL_MCP": "正在校验数据与来源",
    "VALIDATE_TOOL_ENVELOPES": "正在整理研究问题与证据",
    "BUILD_RESEARCH_SYNTHESIS": "正在检查回答边界",
    "VALIDATE_RESPONSE": "正在生成回答",
    "RENDER_ANSWER": "回答已生成",
}


class AgentChatService:
    def __init__(
        self,
        *,
        config: AppConfig | None = None,
        graph: Any | None = None,
        sessions: InMemorySessionStore | None = None,
    ) -> None:
        self._config = config or get_config()
        self._graph = graph or build_agent_graph(config=self._config)
        app = self._config.app
        self._sessions = sessions or InMemorySessionStore(
            ttl_seconds=app.session_ttl_seconds,
            max_sessions=app.max_sessions,
            max_turns_per_session=app.max_turns_per_session,
        )

    async def create_session(self) -> SessionView:
        record = await self._sessions.create()
        return self._sessions.view(record)

    async def get_session(self, session_id: str) -> SessionView | None:
        record = await self._sessions.get(session_id)
        return self._sessions.view(record) if record is not None else None

    async def delete_session(self, session_id: str) -> bool:
        return await self._sessions.delete(session_id)

    async def stream(
        self,
        *,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[StreamEvent]:
        record = await self._sessions.get_or_create(session_id)
        yield StreamEvent(
            event="session",
            data={"session_id": record.session_id},
        )

        async with record.lock:
            state = AgentState(
                question=message,
                context_entities=record.last_entities,
                context_intent=record.last_intent,
            )
            yield StreamEvent(
                event="status",
                data={
                    "node": "CLASSIFY",
                    "message": "正在理解问题",
                },
            )
            async for progress in stream_agent(state, graph=self._graph):
                state = progress.state
                details: dict[str, Any] = {
                    "node": progress.node,
                    "message": _NEXT_NODE_MESSAGES.get(
                        progress.node,
                        "正在处理研究请求",
                    ),
                }
                if (
                    progress.node == "PLAN_REGISTERED_TOOLS"
                    and not state.tool_plan
                ) or (
                    progress.node == "VALIDATE_TOOL_ENVELOPES"
                    and state.status
                    not in {
                        AgentStatus.RUNNING,
                        AgentStatus.PARTIAL_RESULT,
                    }
                ):
                    details["message"] = "正在生成回答"
                if progress.node == "PLAN_REGISTERED_TOOLS":
                    details["tools"] = [
                        item.tool.value for item in state.tool_plan
                    ]
                yield StreamEvent(event="status", data=details)

            response = response_from_state(state)
            await self._sessions.record_exchange(
                record,
                message,
                response,
            )
            yield StreamEvent(
                event="result",
                data={
                    "session_id": record.session_id,
                    "response": response.model_dump(mode="json"),
                },
            )
            yield StreamEvent(
                event="done",
                data={"session_id": record.session_id},
            )
