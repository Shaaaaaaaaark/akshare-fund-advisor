"""In-process, stdio and HTTP clients for the Fund Advisor MCP."""

from __future__ import annotations

import asyncio
import json
import shlex
import sys
from typing import Any, Protocol

from fund_advisor_mcp.config import AppConfig, get_config

from .adapter import FundAdvisorToolAdapter
from .schemas import ToolEnvelope, ToolName


class FundToolClient(Protocol):
    async def call(self, tool: str, arguments: dict[str, Any]) -> ToolEnvelope: ...

    async def healthcheck(self) -> bool: ...


class InProcessFundToolClient:
    def __init__(self, adapter: FundAdvisorToolAdapter | None = None) -> None:
        self._adapter = adapter or FundAdvisorToolAdapter()

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> ToolEnvelope:
        return await asyncio.to_thread(self._adapter.call, tool, arguments)

    async def healthcheck(self) -> bool:
        return True


class StdioFundToolClient:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    def _command(self) -> tuple[str, list[str]]:
        configured = self._config.mcp.server_command.strip()
        if configured:
            parts = shlex.split(configured)
            return parts[0], parts[1:]
        return sys.executable, ["-m", "fund_advisor_mcp.fund.server"]

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> ToolEnvelope:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command, args = self._command()
        parameters = StdioServerParameters(command=command, args=args)
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
        return _parse_result(tool, result)

    async def healthcheck(self) -> bool:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            command, args = self._command()
            parameters = StdioServerParameters(command=command, args=args)
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
            return {item.name for item in tools.tools} == {
                item.value for item in ToolName
            }
        except Exception:
            return False


class HTTPFundToolClient:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> ToolEnvelope:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(
            self._config.mcp.server_url
        ) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments=arguments)
        return _parse_result(tool, result)

    async def healthcheck(self) -> bool:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client

            async with streamable_http_client(
                self._config.mcp.server_url
            ) as (reader, writer, _):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    tools = await session.list_tools()
            return {item.name for item in tools.tools} == {
                item.value for item in ToolName
            }
        except Exception:
            return False


def _parse_result(tool: str, result: Any) -> ToolEnvelope:
    content = getattr(result, "content", [])
    if getattr(result, "isError", False):
        messages = [
            str(text).strip()
            for item in content
            if (text := getattr(item, "text", None))
        ]
        detail = "；".join(messages) or "未返回错误详情"
        raise RuntimeError(f"MCP 工具 {tool} 执行失败：{detail}")

    payload = getattr(result, "structuredContent", None)
    if isinstance(payload, dict):
        candidate = payload.get("result", payload)
        if isinstance(candidate, dict):
            return ToolEnvelope.model_validate(candidate)

    for item in content:
        text = getattr(item, "text", None)
        if not text or not text.strip():
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"MCP 工具 {tool} 返回非 JSON 文本：{text[:200]}"
            ) from exc
        candidate = (
            parsed.get("result", parsed)
            if isinstance(parsed, dict)
            else parsed
        )
        return ToolEnvelope.model_validate(candidate)
    raise RuntimeError(f"MCP 工具 {tool} 未返回 ToolEnvelope")


def build_fund_tool_client(
    config: AppConfig | None = None,
    *,
    adapter: FundAdvisorToolAdapter | None = None,
) -> FundToolClient:
    settings = config or get_config()
    if settings.mcp.transport == "http":
        return HTTPFundToolClient(settings)
    if settings.mcp.transport == "stdio":
        return StdioFundToolClient(settings)
    return InProcessFundToolClient(adapter)
