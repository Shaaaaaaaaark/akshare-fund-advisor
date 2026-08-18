from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from io import StringIO
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rich.console import Console

from fund_advisor_agent.state import AgentResponse, AgentStatus, Intent
from fund_advisor_app.api import create_app
from fund_advisor_app.cli import _chat
from fund_advisor_app.client import AgentApiClient, _parse_sse
from fund_advisor_app.schemas import ChatRequest, SessionView, StreamEvent
from fund_advisor_app.service import AgentChatService
from fund_advisor_app.sessions import (
    InMemorySessionStore,
    SessionCapacityError,
)
from fund_advisor_mcp.config import AppConfig


class FakeGraph:
    def __init__(self) -> None:
        self.inputs: list[Any] = []

    async def astream(
        self,
        initial_state: Any,
        *,
        stream_mode: str,
    ) -> AsyncIterator[dict[str, dict[str, Any]]]:
        assert stream_mode == "updates"
        self.inputs.append(initial_state)
        yield {
            "CLASSIFY": {
                "intent": Intent.FUND_ANALYSIS,
                "entities": ["000001"],
            }
        }
        yield {
            "RENDER_ANSWER": {
                "status": AgentStatus.COMPLETED,
                "final_answer": "已完成可信数据分析。",
            }
        }


class UnsupportedGraph:
    async def astream(
        self,
        _initial_state: Any,
        *,
        stream_mode: str,
    ) -> AsyncIterator[dict[str, dict[str, Any]]]:
        assert stream_mode == "updates"
        yield {
            "CLASSIFY": {
                "intent": Intent.UNSUPPORTED,
            }
        }
        yield {
            "PLAN_REGISTERED_TOOLS": {
                "status": AgentStatus.UNSUPPORTED,
                "tool_plan": [],
            }
        }
        yield {
            "RENDER_ANSWER": {
                "final_answer": "当前数据能力不支持该请求。",
            }
        }


class StubChatService:
    def __init__(self) -> None:
        self.session = _session_view("a" * 32)
        self.messages: list[str] = []

    async def create_session(self) -> SessionView:
        return self.session

    async def get_session(self, session_id: str) -> SessionView | None:
        return self.session if session_id == self.session.session_id else None

    async def delete_session(self, session_id: str) -> bool:
        return session_id == self.session.session_id

    async def stream(
        self,
        *,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[StreamEvent]:
        self.messages.append(message)
        resolved = session_id or self.session.session_id
        yield StreamEvent(event="session", data={"session_id": resolved})
        yield StreamEvent(
            event="status",
            data={"node": "CLASSIFY", "message": "正在理解问题"},
        )
        yield StreamEvent(
            event="result",
            data={
                "session_id": resolved,
                "response": {
                    "status": "completed",
                    "answer": "测试回答",
                },
            },
        )
        yield StreamEvent(event="done", data={"session_id": resolved})


class StubCliClient:
    def __init__(self) -> None:
        self.session = _session_view("c" * 32)
        self.deleted: list[str] = []

    def create_session(self) -> SessionView:
        return self.session

    def delete_session(self, session_id: str) -> None:
        self.deleted.append(session_id)


class CapacityChatService(StubChatService):
    async def create_session(self) -> SessionView:
        raise SessionCapacityError

    async def stream(
        self,
        *,
        message: str,
        session_id: str | None,
    ) -> AsyncIterator[StreamEvent]:
        del message, session_id
        raise SessionCapacityError
        yield StreamEvent(event="done", data={})


def _config() -> AppConfig:
    config = AppConfig()
    app = config.app.model_copy(
        update={
            "session_ttl_seconds": 60,
            "max_sessions": 4,
            "max_turns_per_session": 4,
        }
    )
    return config.model_copy(update={"app": app})


def _session_view(session_id: str) -> SessionView:
    now = datetime.now(timezone.utc)
    return SessionView(
        session_id=session_id,
        created_at=now,
        updated_at=now,
    )


def _agent_response(answer: str, entity: str) -> AgentResponse:
    return AgentResponse(
        status=AgentStatus.COMPLETED,
        intent=Intent.FUND_ANALYSIS,
        entities=[entity],
        answer=answer,
    )


def test_chat_request_strips_message_and_rejects_blank() -> None:
    request = ChatRequest(message="  分析 000001  ")
    assert request.message == "分析 000001"

    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


@pytest.mark.asyncio
async def test_session_store_is_bounded_and_keeps_latest_context() -> None:
    store = InMemorySessionStore(
        ttl_seconds=60,
        max_sessions=2,
        max_turns_per_session=2,
    )
    record = await store.create()
    await store.record_exchange(
        record,
        "第一问",
        _agent_response("第一答", "000001"),
    )
    await store.record_exchange(
        record,
        "第二问",
        _agent_response("第二答", "000002"),
    )

    view = store.view(record)
    assert [turn.content for turn in view.turns] == ["第二问", "第二答"]
    assert record.last_entities == ["000002"]
    assert record.last_intent is Intent.FUND_ANALYSIS

    second = await store.create()
    third = await store.create()
    assert await store.get(record.session_id) is None
    assert await store.get(second.session_id) is not None
    assert await store.get(third.session_id) is not None


@pytest.mark.asyncio
async def test_session_store_does_not_evict_active_session() -> None:
    store = InMemorySessionStore(
        ttl_seconds=60,
        max_sessions=1,
        max_turns_per_session=2,
    )
    active = await store.create()
    await active.lock.acquire()
    try:
        with pytest.raises(SessionCapacityError):
            await store.create()
        assert await store.get(active.session_id) is active
    finally:
        active.lock.release()

    assert await store.delete(active.session_id) is True


@pytest.mark.asyncio
async def test_chat_service_streams_progress_and_reuses_context() -> None:
    graph = FakeGraph()
    service = AgentChatService(config=_config(), graph=graph)

    first_events = [
        item
        async for item in service.stream(
            message="分析 000001",
            session_id=None,
        )
    ]
    session_id = str(first_events[0].data["session_id"])
    second_events = [
        item
        async for item in service.stream(
            message="它的风险呢",
            session_id=session_id,
        )
    ]

    assert [item.event for item in first_events] == [
        "session",
        "status",
        "status",
        "status",
        "result",
        "done",
    ]
    assert first_events[1].data == {
        "node": "CLASSIFY",
        "message": "正在理解问题",
    }
    assert first_events[3].data["message"] == "回答已生成"
    assert second_events[-2].data["response"]["answer"] == "已完成可信数据分析。"
    assert graph.inputs[1].context_entities == ["000001"]
    assert graph.inputs[1].context_intent is Intent.FUND_ANALYSIS


@pytest.mark.asyncio
async def test_chat_service_does_not_report_tool_query_without_plan() -> None:
    service = AgentChatService(config=_config(), graph=UnsupportedGraph())

    events = [
        item
        async for item in service.stream(
            message="请帮我自动交易",
            session_id=None,
        )
    ]
    statuses = [
        str(item.data["message"])
        for item in events
        if item.event == "status"
    ]

    assert "正在查询可信数据" not in statuses
    assert "正在生成回答" in statuses


def test_api_exposes_sessions_sse_and_validation() -> None:
    service = StubChatService()
    app = create_app(
        config=_config(),
        service=service,  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        health = client.get("/health")
        session = client.post("/api/sessions")
        response = client.post(
            "/api/chat/stream",
            json={"message": "  分析 000001  ", "session_id": None},
        )
        root = client.get("/")
        blank = client.post(
            "/api/chat/stream",
            json={"message": "   ", "session_id": None},
        )

    assert health.json() == {"status": "ok"}
    assert session.json()["session_id"] == "a" * 32
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert '"answer":"测试回答"' in response.text
    assert root.json() == {
        "name": "Fund Advisor Agent API",
        "docs": "/api/docs",
    }
    assert service.messages == ["分析 000001"]
    assert blank.status_code == 422


def test_api_reports_session_capacity_without_dropping_active_context() -> None:
    app = create_app(
        config=_config(),
        service=CapacityChatService(),  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        session = client.post("/api/sessions")
        stream = client.post(
            "/api/chat/stream",
            json={"message": "分析 000001", "session_id": None},
        )

    assert session.status_code == 503
    assert session.json()["detail"] == "临时会话已满，请稍后重试"
    assert "SESSION_CAPACITY_EXCEEDED" in stream.text
    assert "event: done" in stream.text


def test_sse_parser_handles_multiple_events() -> None:
    events = list(
        _parse_sse(
            iter(
                [
                    "event: session",
                    'data: {"session_id":"abc"}',
                    "",
                    "event: done",
                    "data: {}",
                    "",
                ]
            )
        )
    )

    assert [item.event for item in events] == ["session", "done"]
    assert events[0].data == {"session_id": "abc"}


def test_agent_api_client_consumes_sse() -> None:
    now = datetime.now(timezone.utc).isoformat()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/sessions":
            return httpx.Response(
                200,
                json={
                    "session_id": "b" * 32,
                    "turns": [],
                    "created_at": now,
                    "updated_at": now,
                },
            )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text=(
                "event: session\n"
                'data: {"session_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}\n\n'
                "event: done\n"
                "data: {}\n\n"
            ),
        )

    with AgentApiClient(
        "http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        session = client.create_session()
        events = list(
            client.stream_message(
                "分析 000001",
                session_id=session.session_id,
            )
        )

    assert session.session_id == "b" * 32
    assert [item.event for item in events] == ["session", "done"]


def test_interactive_cli_deletes_session_on_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = StubCliClient()
    console = Console(file=StringIO(), force_terminal=False)
    monkeypatch.setattr(
        "fund_advisor_app.cli.Prompt.ask",
        lambda *_args, **_kwargs: "/exit",
    )

    result = _chat(  # type: ignore[arg-type]
        client,
        console,
    )

    assert result == 0
    assert client.deleted == ["c" * 32]
