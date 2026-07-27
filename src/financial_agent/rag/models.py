"""Contracts shared by all three RAG channels."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


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


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    channel: RetrievalChannel
    reason: str = Field(min_length=1, max_length=300)
    url: HttpUrl | None = None
    subject_code: str | None = None
    doc_types: list[str] = Field(default_factory=list, max_length=8)
    limit: int = Field(default=8, ge=1, le=20)

    @model_validator(mode="after")
    def direct_document_requires_url(self) -> RetrievalQuery:
        if self.channel == RetrievalChannel.DIRECT_DOCUMENT and self.url is None:
            raise ValueError("指定文档检索必须提供 URL")
        return self


class RetrievalPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=5)
    queries: list[RetrievalQuery] = Field(default_factory=list, max_length=5)
    reason: str = Field(min_length=1, max_length=500)


class RetrievalAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    retryable: bool
    reason: str = Field(min_length=1, max_length=500)
    missing_aspects: list[str] = Field(default_factory=list, max_length=5)


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
