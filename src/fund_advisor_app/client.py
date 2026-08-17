"""Synchronous SSE client used by the terminal product."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from .schemas import SessionView, StreamEvent


class AgentApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 1800,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def create_session(self) -> SessionView:
        response = self._client.post("/api/sessions")
        response.raise_for_status()
        return SessionView.model_validate(response.json())

    def delete_session(self, session_id: str) -> None:
        response = self._client.delete(f"/api/sessions/{session_id}")
        response.raise_for_status()

    def stream_message(
        self,
        message: str,
        *,
        session_id: str | None,
    ) -> Iterator[StreamEvent]:
        with self._client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": message, "session_id": session_id},
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            yield from _parse_sse(response.iter_lines())

    def __enter__(self) -> AgentApiClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _parse_sse(lines: Iterator[str]) -> Iterator[StreamEvent]:
    event_name = "status"
    data_lines: list[str] = []
    for line in lines:
        if not line:
            if data_lines:
                yield _event(event_name, data_lines)
            event_name = "status"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        yield _event(event_name, data_lines)


def _event(name: str, data_lines: list[str]) -> StreamEvent:
    payload = json.loads("\n".join(data_lines))
    return StreamEvent.model_validate({"event": name, "data": payload})
