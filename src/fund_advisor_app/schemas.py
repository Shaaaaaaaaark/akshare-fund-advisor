"""Contracts shared by the Agent API and web client."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{32}$",
    )

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("message must not be blank")
        return normalized


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SessionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: Literal["session", "status", "result", "error", "done"]
    data: dict[str, Any] = Field(default_factory=dict)
