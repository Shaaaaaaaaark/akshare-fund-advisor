"""Reusable Web Research MCP service and clients."""

from .client import (
    HTTPWebResearchClient,
    InProcessWebResearchClient,
    StdioWebResearchClient,
    WebResearchClient,
    build_web_research_client,
)
from .schemas import (
    DocumentReadInput,
    WebFetchData,
    WebSearchData,
    WebSearchResult,
    WebSourceType,
    WebToolEnvelope,
    WebToolName,
)
from .service import WebResearchError, WebResearchService

__all__ = [
    "DocumentReadInput",
    "HTTPWebResearchClient",
    "InProcessWebResearchClient",
    "StdioWebResearchClient",
    "WebFetchData",
    "WebResearchClient",
    "WebResearchError",
    "WebResearchService",
    "WebSearchData",
    "WebSearchResult",
    "WebSourceType",
    "WebToolEnvelope",
    "WebToolName",
    "build_web_research_client",
]
