"""HTTP API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreated(BaseModel):
    conversation_id: UUID


class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str
    preview: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class ConversationMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime
    task_id: UUID
    report_id: UUID | None = None
    status: str
    clarification: dict[str, Any] | None = None
    report: dict[str, Any] | None = None


class ConversationDetail(BaseModel):
    conversation_id: UUID
    title: str
    created_at: datetime
    messages: list[ConversationMessage] = Field(default_factory=list)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)


class MessageAccepted(BaseModel):
    conversation_id: UUID
    task_id: UUID
    trace_id: str
    status: str
    clarification: dict[str, Any] | None = None
    report_id: UUID | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class TaskResponse(BaseModel):
    task_id: UUID
    conversation_id: UUID
    trace_id: str
    query: str
    status: str
    clarification: dict[str, Any] | None = None
    report_id: UUID | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok", "not_ready"]
    checks: dict[str, bool] = Field(default_factory=dict)
