"""Typed data-core failures converted to ToolEnvelope errors at boundaries."""

from __future__ import annotations

from typing import Any


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

