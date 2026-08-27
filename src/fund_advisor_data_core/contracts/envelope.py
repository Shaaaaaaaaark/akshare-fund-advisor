"""ToolEnvelope contract shared across product boundaries."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .tools import ToolName


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID = Field(default_factory=uuid4)
    tool: ToolName
    ok: bool
    data: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    data_audit: list[dict[str, Any]] = Field(default_factory=list)
    data_warnings: list[dict[str, Any] | str] = Field(default_factory=list)
    data_policy: dict[str, Any] = Field(default_factory=dict)
    queried_at: datetime
    error: ToolError | None = None

