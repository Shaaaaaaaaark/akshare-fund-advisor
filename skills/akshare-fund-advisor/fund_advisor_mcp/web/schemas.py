"""Strongly typed contracts for the Web Research MCP boundary."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class WebToolName(StrEnum):
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    DOCUMENT_READ = "document_read"


class WebSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    max_results: int = Field(default=5, ge=1, le=20)
    freshness_days: int | None = Field(default=None, ge=1, le=365)


class WebFetchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl
    max_chars: int = Field(default=12000, ge=1000, le=100000)


class DocumentReadInput(BaseModel):
    """读取用户给定的官方文档 URL（HTML/纯文本/PDF）。"""

    model_config = ConfigDict(extra="forbid")

    url: AnyHttpUrl
    max_chars: int = Field(default=20000, ge=1000, le=200000)


class WebSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    title: str
    url: str
    snippet: str
    published_at: str | None = None
    language: str | None = None


class WebSearchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    provider: str
    results: list[WebSearchResult] = Field(default_factory=list)


class WebFetchData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_url: str
    final_url: str
    title: str
    content: str
    content_type: str
    truncated: bool
    content_sha256: str


class WebToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: bool = False
    details: dict = Field(default_factory=dict)


class WebAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: WebToolName
    provider: str
    request: dict
    validation: Literal["passed", "failed"]
    response_sha256: str | None = None
    result_count: int | None = None


class WebDataPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["background_only"] = "background_only"
    numeric_allowed: Literal[False] = False
    ai_may_generate_market_data: Literal[False] = False
    may_override_market_tools: Literal[False] = False


class WebToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID = Field(default_factory=uuid4)
    tool: WebToolName
    ok: bool
    data: WebSearchData | WebFetchData | None = None
    sources: list[dict] = Field(default_factory=list)
    data_audit: list[WebAuditRecord] = Field(default_factory=list)
    data_policy: WebDataPolicy = Field(default_factory=WebDataPolicy)
    queried_at: datetime
    error: WebToolError | None = None

