"""In-process, stdio and HTTP clients for the Web Research MCP."""

from __future__ import annotations

import json
import shlex
import sys
from typing import Any, Protocol

from financial_agent.config import AppConfig, get_config

from .schemas import WebToolEnvelope
from .service import WebResearchService


class WebResearchClient(Protocol):
    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> WebToolEnvelope: ...

    async def healthcheck(self) -> bool: ...


class InProcessWebResearchClient:
    def __init__(self, service: WebResearchService | None = None) -> None:
        self._service = service or WebResearchService()

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> WebToolEnvelope:
        if tool == "web_search":
            return await self._service.web_search(**arguments)
        if tool == "web_fetch":
            return await self._service.web_fetch(**arguments)
        if tool == "document_read":
            return await self._service.document_read(**arguments)
        raise ValueError(f"未注册的网页研究工具：{tool}")

    async def healthcheck(self) -> bool:
        return True


class StdioWebResearchClient:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    def _command(self) -> tuple[str, list[str]]:
        configured = self._config.web_research.server_command.strip()
        if configured:
            parts = shlex.split(configured)
            return parts[0], parts[1:]
        return sys.executable, ["-m", "financial_agent.web_research.server"]

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> WebToolEnvelope:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command, args = self._command()
        parameters = StdioServerParameters(command=command, args=args)
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
        return _parse_web_result(tool, result)

    async def healthcheck(self) -> bool:
        try:
            command, args = self._command()
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            parameters = StdioServerParameters(command=command, args=args)
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
            return {item.name for item in tools.tools} == {
                "web_search",
                "web_fetch",
                "document_read",
            }
        except Exception:
            return False


class HTTPWebResearchClient:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> WebToolEnvelope:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(
            self._config.web_research.server_url
        ) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
        return _parse_web_result(tool, result)

    async def healthcheck(self) -> bool:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with streamable_http_client(
                self._config.web_research.server_url
            ) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
            return {item.name for item in tools.tools} == {
                "web_search",
                "web_fetch",
                "document_read",
            }
        except Exception:
            return False


def _parse_web_result(tool: str, result: Any) -> WebToolEnvelope:
    content = getattr(result, "content", [])
    if getattr(result, "isError", False):
        messages = [
            str(text).strip()
            for item in content
            if (text := getattr(item, "text", None))
        ]
        detail = "；".join(messages) or "未返回错误详情"
        raise RuntimeError(f"网页研究 MCP 工具 {tool} 执行失败：{detail}")

    payload = getattr(result, "structuredContent", None)
    if isinstance(payload, dict):
        candidate = payload.get("result", payload)
        if isinstance(candidate, dict):
            return WebToolEnvelope.model_validate(candidate)

    for item in content:
        text = getattr(item, "text", None)
        if not text or not text.strip():
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"网页研究 MCP 工具 {tool} 返回非 JSON 文本：{text[:200]}"
            ) from exc
        candidate = (
            parsed.get("result", parsed)
            if isinstance(parsed, dict)
            else parsed
        )
        return WebToolEnvelope.model_validate(candidate)
    raise RuntimeError(f"网页研究 MCP 工具 {tool} 未返回 WebToolEnvelope")


def build_web_research_client(
    config: AppConfig | None = None,
    *,
    service: WebResearchService | None = None,
) -> WebResearchClient:
    settings = config or get_config()
    if settings.web_research.transport == "http":
        return HTTPWebResearchClient(settings)
    if settings.web_research.transport == "stdio":
        return StdioWebResearchClient(settings)
    return InProcessWebResearchClient(service or WebResearchService(settings))
