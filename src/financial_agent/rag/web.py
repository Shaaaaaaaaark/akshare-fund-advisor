"""Brave Search + safe fetch channel for qualitative background only."""

from __future__ import annotations

import asyncio

import httpx
from bs4 import BeautifulSoup

from financial_agent.config import AppConfig, get_config

from .direct_reader import DirectDocumentReader
from .models import DocumentHit, RetrievalChannel, RetrievalRequest


class BraveWebRetriever:
    SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        unrestricted_security = self._config.security.model_copy(
            update={"allowed_document_domains": []}
        )
        unrestricted = self._config.model_copy(update={"security": unrestricted_security})
        self._validator = DirectDocumentReader(unrestricted)

    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        key = self._config.rag.web_search_api_key
        if not key or not self._config.rag.web_enabled:
            return []
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                self.SEARCH_URL,
                params={
                    "q": request.question,
                    "count": min(request.limit, 10),
                    "search_lang": "zh-hans",
                },
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": key,
                },
            )
            response.raise_for_status()
            results = response.json().get("web", {}).get("results", [])

        semaphore = asyncio.Semaphore(3)

        async def build(item: dict) -> DocumentHit | None:
            url = str(item.get("url") or "")
            if not url:
                return None
            text = str(item.get("description") or "")
            try:
                async with semaphore:
                    fetched = await self._fetch(url)
                if fetched:
                    text = fetched
            except Exception:
                pass
            if not text:
                return None
            return DocumentHit(
                channel=RetrievalChannel.WEB,
                title=str(item.get("title") or url),
                url=url,
                text=text[:5000],
                score=0.2,
                metadata={
                    "purpose": "background_only",
                    "numeric_allowed": False,
                },
            )

        built = await asyncio.gather(*(build(item) for item in results))
        return [item for item in built if item is not None][: request.limit]

    async def _fetch(self, url: str) -> str:
        await self._validator._validate_url(url)
        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": "FinancialResearchAgent/0.1"},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                await self._validator._validate_url(str(response.url))
                if "html" not in response.headers.get("content-type", "").lower():
                    return ""
                content = await self._validator._read_limited(response)
            soup = BeautifulSoup(
                content.decode("utf-8", errors="replace"),
                "html.parser",
            )
            for element in soup(["script", "style", "noscript", "form"]):
                element.decompose()
            return soup.get_text("\n", strip=True)
