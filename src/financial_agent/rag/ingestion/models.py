"""Typed artifacts produced by the document ingestion pipeline."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_url: HttpUrl
    source_domain: str
    trust_tier: str = "official"


class VersionDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str
    doc_type: str
    subject_code: str | None = None
    content_sha256: str
    version: str
    publish_date: date | None = None
    effective_date: date | None = None
    metadata: dict = Field(default_factory=dict)


class ParsedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    page: int | None = None
    section_path: list[str] = Field(default_factory=list)
    block_type: str = "paragraph"


class IngestionChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    chunk_index: int
    page_start: int | None = None
    page_end: int | None = None
    section_path: list[str] = Field(default_factory=list)
    content: str
    content_sha256: str
    embedding_model: str
    embedding: list[float] | None = None
    metadata: dict = Field(default_factory=dict)
