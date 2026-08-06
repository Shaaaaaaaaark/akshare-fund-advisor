"""Transport-neutral MCP client contract used by graph nodes."""

from __future__ import annotations

from typing import Any, Protocol


class EnvelopeModel(Protocol):
    def model_dump(self, *, mode: str = "python") -> dict[str, Any]: ...


class McpToolClient(Protocol):
    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> EnvelopeModel: ...

    async def healthcheck(self) -> bool: ...
