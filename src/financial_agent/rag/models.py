"""Contracts shared by all three RAG channels."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RetrievalChannel(StrEnum):
    KNOWLEDGE = "knowledge"
    DIRECT_DOCUMENT = "direct_document"
    WEB = "web"


class RetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    channel: RetrievalChannel
    url: HttpUrl | None = None
    subject_code: str | None = None
    doc_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)


class DocumentHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit_id: UUID = Field(default_factory=uuid4)
    channel: RetrievalChannel
    title: str
    url: str
    text: str
    score: float = Field(default=1.0, ge=0)
    page: int | None = None
    version: str | None = None
    subject_code: str | None = None
    doc_type: str | None = None
    metadata: dict = Field(default_factory=dict)
