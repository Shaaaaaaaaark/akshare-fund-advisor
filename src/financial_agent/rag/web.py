"""Web Research MCP adapter for the qualitative RAG channel."""

from __future__ import annotations

import asyncio
from typing import Any

from financial_agent.config import AppConfig, get_config
from financial_agent.web_research import (
    WebFetchData,
    WebResearchClient,
    WebSearchData,
    build_web_research_client,
)

from .models import DocumentHit, RetrievalChannel, RetrievalRequest


class MCPWebRetriever:
    """Use web_search and web_fetch through the shared MCP boundary."""

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        client: WebResearchClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._client = client or build_web_research_client(self._config)

    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        if (
            not self._config.rag.web_enabled
            or not (
                self._config.web_research.enabled
                or self._config.rag.web_search_api_key
            )
        ):
            return []
        search = await self._client.call(
            "web_search",
            {
                "query": request.question,
                "max_results": request.limit,
            },
        )
        if not search.ok or not isinstance(search.data, WebSearchData):
            detail = search.error.message if search.error else "未返回搜索结果"
            raise RuntimeError(f"网页搜索失败：{detail}")

        semaphore = asyncio.Semaphore(
            self._config.web_research.fetch_concurrency
        )

        async def build(result: Any) -> DocumentHit | None:
            content = result.snippet
            title = result.title
            final_url = result.url
            fetch_hashes: list[str] = []
            fetch_error: str | None = None
            try:
                async with semaphore:
                    fetched = await self._client.call(
                        "web_fetch",
                        {
                            "url": result.url,
                            "max_chars": min(
                                self._config.web_research.max_content_chars,
                                self._config.rag.max_context_chars,
                            ),
                        },
                    )
                if fetched.ok and isinstance(fetched.data, WebFetchData):
                    content = fetched.data.content or content
                    title = fetched.data.title or title
                    final_url = fetched.data.final_url
                    fetch_hashes = _audit_hashes(fetched.data_audit)
                elif fetched.error is not None:
                    fetch_error = fetched.error.code
            except Exception as exc:
                fetch_error = type(exc).__name__
            if not content:
                return None
            return DocumentHit(
                channel=RetrievalChannel.WEB,
                title=title,
                url=final_url,
                text=content,
                score=max(0.01, 1.0 / (result.rank + 4)),
                metadata={
                    "purpose": "background_only",
                    "numeric_allowed": False,
                    "provider": search.data.provider,
                    "search_rank": result.rank,
                    "published_at": result.published_at,
                    "search_audit_hashes": _audit_hashes(search.data_audit),
                    "fetch_audit_hashes": fetch_hashes,
                    "fetch_error": fetch_error,
                },
            )

        built = await asyncio.gather(
            *(build(item) for item in search.data.results)
        )
        return [
            item for item in built if item is not None
        ][: request.limit]


def _audit_hashes(items: list[Any]) -> list[str]:
    return [
        str(item.response_sha256)
        for item in items
        if item.validation == "passed" and item.response_sha256
    ]


BraveWebRetriever = MCPWebRetriever
