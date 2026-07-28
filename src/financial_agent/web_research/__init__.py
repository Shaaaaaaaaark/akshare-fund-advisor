"""Reusable Web Research MCP service and clients."""

from .client import (
    HTTPWebResearchClient,
    InProcessWebResearchClient,
    StdioWebResearchClient,
    WebResearchClient,
    build_web_research_client,
)
from .schemas import (
    WebFetchData,
    WebSearchData,
    WebSearchResult,
    WebToolEnvelope,
    WebToolName,
)
from .service import WebResearchError, WebResearchService

__all__ = [
    "HTTPWebResearchClient",
    "InProcessWebResearchClient",
    "StdioWebResearchClient",
    "WebFetchData",
    "WebResearchClient",
    "WebResearchError",
    "WebResearchService",
    "WebSearchData",
    "WebSearchResult",
    "WebToolEnvelope",
    "WebToolName",
    "build_web_research_client",
]

