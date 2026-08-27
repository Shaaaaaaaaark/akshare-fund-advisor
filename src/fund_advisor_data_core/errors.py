"""Typed data-core failures converted to ToolEnvelope errors at boundaries."""

from __future__ import annotations

from typing import Any

# 只有上游可恢复故障才允许重试；契约、歧义、未找到等语义错误重试没有意义。
RETRYABLE_CODES: frozenset[str] = frozenset(
    {
        "DATA_SOURCE_ERROR",
        "RATE_LIMITED",
        "UPSTREAM_TIMEOUT",
    }
)


class DataCoreError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

