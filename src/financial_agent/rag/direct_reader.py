"""Safe JIT reader for a user-supplied official document URL."""

from __future__ import annotations

import asyncio
import io
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from financial_agent.config import AppConfig, get_config

from .models import DocumentHit, RetrievalChannel, RetrievalRequest
from .text import query_terms


class DocumentSecurityError(ValueError):
    pass


class DirectDocumentReader:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    async def read(self, request: RetrievalRequest) -> list[DocumentHit]:
        if request.url is None:
            raise ValueError("指定文档读取需要 URL")
        url = str(request.url)
        await self._validate_url(url)

        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": "FinancialResearchAgent/0.1"},
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                final_url = str(response.url)
                await self._validate_url(final_url)
                content_type = response.headers.get("content-type", "").lower()
                content = await self._read_limited(response)

        if "pdf" in content_type or final_url.lower().endswith(".pdf"):
            pages = await asyncio.to_thread(self._read_pdf, content)
            title = final_url.rsplit("/", 1)[-1] or "PDF 文档"
        elif any(item in content_type for item in ("html", "text/plain", "markdown")):
            text, title = self._read_text(content, content_type)
            pages = [(None, text)]
        else:
            raise DocumentSecurityError(f"不支持的文档类型：{content_type or 'unknown'}")

        return self._select_hits(
            pages=pages,
            question=request.question,
            title=title,
            url=final_url,
            limit=request.limit,
        )

    async def _read_limited(self, response: httpx.Response) -> bytes:
        maximum = self._config.security.max_document_bytes
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > maximum:
            raise DocumentSecurityError("文档超过允许大小")
        parts: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > maximum:
                raise DocumentSecurityError("文档超过允许大小")
            parts.append(chunk)
        return b"".join(parts)

    async def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DocumentSecurityError("只允许 http/https 公网文档")

        host = parsed.hostname.lower().rstrip(".")
        allowed = [
            item.lower().rstrip(".") for item in self._config.security.allowed_document_domains
        ]
        if allowed and not any(host == item or host.endswith(f".{item}") for item in allowed):
            raise DocumentSecurityError(f"文档域名不在 allowlist：{host}")

        addresses = await asyncio.to_thread(socket.getaddrinfo, host, None)
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
            ):
                raise DocumentSecurityError("禁止访问本机、私网或保留地址")

    @staticmethod
    def _read_pdf(content: bytes) -> list[tuple[int | None, str]]:
        reader = PdfReader(io.BytesIO(content))
        return [
            (index, page.extract_text() or "") for index, page in enumerate(reader.pages, start=1)
        ]

    @staticmethod
    def _read_text(content: bytes, content_type: str) -> tuple[str, str]:
        decoded = content.decode("utf-8", errors="replace")
        if "html" not in content_type:
            return decoded, "指定文档"
        soup = BeautifulSoup(decoded, "html.parser")
        for element in soup(["script", "style", "noscript", "form"]):
            element.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else "网页文档"
        return soup.get_text("\n", strip=True), title

    @staticmethod
    def _select_hits(
        *,
        pages: list[tuple[int | None, str]],
        question: str,
        title: str,
        url: str,
        limit: int,
    ) -> list[DocumentHit]:
        terms = query_terms(question)
        candidates: list[tuple[float, int | None, str]] = []
        for page, text in pages:
            paragraphs = [
                item.strip()
                for item in re.split(r"\n{2,}|(?<=[。！？])\s*", text)
                if len(item.strip()) >= 20
            ]
            for paragraph in paragraphs:
                lowered = paragraph.lower()
                score = float(sum(1 for term in terms if term in lowered))
                if score > 0 or not terms:
                    candidates.append((score, page, paragraph[:4000]))

        candidates.sort(key=lambda item: (-item[0], item[1] or 0))
        selected = candidates[:limit]
        if not selected:
            selected = [(0.1, page, text[:4000]) for page, text in pages if text.strip()][:limit]
        return [
            DocumentHit(
                channel=RetrievalChannel.DIRECT_DOCUMENT,
                title=title,
                url=url,
                text=text,
                score=max(score, 0.1),
                page=page,
                metadata={"numeric_allowed": False},
            )
            for score, page, text in selected
        ]
