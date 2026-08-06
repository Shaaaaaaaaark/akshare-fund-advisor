"""Search provider and safe public-web fetch implementation."""

from __future__ import annotations

import asyncio
import hashlib
import io
import ipaddress
import json
import logging
import socket
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from financial_agent.config import AppConfig, get_config

from .schemas import (
    DocumentReadInput,
    WebAuditRecord,
    WebFetchData,
    WebFetchInput,
    WebSearchData,
    WebSearchInput,
    WebSearchResult,
    WebToolEnvelope,
    WebToolError,
    WebToolName,
)

logger = logging.getLogger("financial_agent.web_research")


class WebResearchError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class WebResearchService:
    """Multi-provider search chain and SSRF-safe page fetching.

    搜索走"兜底链"：按配置顺序依次尝试 serper / tavily / google_cse /
    brave / serpapi，前一个供应商认证失败、限流、超额或上游报错时自动
    降级到下一个；任一供应商成功（HTTP 正常）即返回其结果。无论命中哪个
    供应商，网页内容始终是非数值背景，不能覆盖 AKShare 市场事实。
    """

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config or get_config()
        self._settings = self._config.web_research
        self._transport = transport

    async def web_search(self, **kwargs: Any) -> WebToolEnvelope:
        request = WebSearchInput.model_validate(kwargs)
        now = datetime.now(timezone.utc)
        try:
            self._ensure_enabled()
            data, provider_name, attempts = await self._search_chain(request)
            digest = _sha256(data.model_dump(mode="json"))
            return WebToolEnvelope(
                tool=WebToolName.WEB_SEARCH,
                ok=True,
                data=data,
                sources=[
                    {
                        "provider": data.provider,
                        "provider_key": provider_name,
                    }
                ],
                data_audit=[
                    WebAuditRecord(
                        operation=WebToolName.WEB_SEARCH,
                        provider=data.provider,
                        request={
                            "query": request.query,
                            "max_results": request.max_results,
                            "freshness_days": request.freshness_days,
                            "provider": provider_name,
                            "attempts": attempts,
                        },
                        validation="passed",
                        response_sha256=digest,
                        result_count=len(data.results),
                    )
                ],
                queried_at=now,
            )
        except Exception as exc:
            return self._error_envelope(WebToolName.WEB_SEARCH, exc, now)

    async def web_fetch(self, **kwargs: Any) -> WebToolEnvelope:
        request = WebFetchInput.model_validate(kwargs)
        now = datetime.now(timezone.utc)
        try:
            self._ensure_enabled()
            data = await self._fetch_page(
                str(request.url),
                min(request.max_chars, self._settings.max_content_chars),
            )
            return WebToolEnvelope(
                tool=WebToolName.WEB_FETCH,
                ok=True,
                data=data,
                sources=[
                    {
                        "provider": "Public Web",
                        "url": data.final_url,
                    }
                ],
                data_audit=[
                    WebAuditRecord(
                        operation=WebToolName.WEB_FETCH,
                        provider="Public Web",
                        request={
                            "url": str(request.url),
                            "max_chars": request.max_chars,
                        },
                        validation="passed",
                        response_sha256=data.content_sha256,
                        result_count=1,
                    )
                ],
                queried_at=now,
            )
        except Exception as exc:
            return self._error_envelope(WebToolName.WEB_FETCH, exc, now)

    async def document_read(self, **kwargs: Any) -> WebToolEnvelope:
        """读取用户给定的官方文档 URL，支持 HTML/纯文本/PDF。

        与 web_fetch 共享 SSRF 校验和逐跳重定向；额外支持 PDF 正文抽取。
        返回的正文固定 numeric_allowed=false：文档只提供条款文本，任何市场
        数值仍只能来自 AKShare 工具。
        """
        request = DocumentReadInput.model_validate(kwargs)
        now = datetime.now(timezone.utc)
        try:
            self._ensure_enabled()
            data = await self._read_document(
                str(request.url),
                min(request.max_chars, self._settings.max_content_chars),
            )
            return WebToolEnvelope(
                tool=WebToolName.DOCUMENT_READ,
                ok=True,
                data=data,
                sources=[{"provider": "Official Document", "url": data.final_url}],
                data_audit=[
                    WebAuditRecord(
                        operation=WebToolName.DOCUMENT_READ,
                        provider="Official Document",
                        request={
                            "url": str(request.url),
                            "max_chars": request.max_chars,
                        },
                        validation="passed",
                        response_sha256=data.content_sha256,
                        result_count=1,
                    )
                ],
                queried_at=now,
            )
        except Exception as exc:
            return self._error_envelope(WebToolName.DOCUMENT_READ, exc, now)

    async def _search_chain(
        self,
        request: WebSearchInput,
    ) -> tuple[WebSearchData, str, list[dict[str, Any]]]:
        """按配置顺序尝试各搜索供应商，返回首个成功的结果。

        每个供应商的 HTTP 层失败（认证、限流、超额、5xx、无效响应）都会被
        记录到 attempts 并降级到下一个；全部失败才抛出聚合错误。空结果视为
        成功（返回 0 条），不再降级——这代表供应商正常但没有匹配网页。
        """
        chain = self._settings.resolved_chain()
        if not chain:
            raise WebResearchError(
                "WEB_SEARCH_NOT_CONFIGURED",
                "网页搜索尚未配置任何可用供应商（缺少 API Key）",
            )
        adapters = {
            "serper": self._search_serper,
            "tavily": self._search_tavily,
            "google_cse": self._search_google_cse,
            "brave": self._search_brave,
            "serpapi": self._search_serpapi,
        }
        attempts: list[dict[str, Any]] = []
        last_error: WebResearchError | None = None
        for name, provider_cfg in chain:
            adapter = adapters.get(name)
            if adapter is None:
                continue
            try:
                data = await adapter(request, provider_cfg)
            except WebResearchError as exc:
                attempts.append({"provider": name, "error_code": exc.code})
                last_error = exc
                logger.warning(
                    "搜索供应商 %s 失败(%s)，尝试降级到下一个", name, exc.code
                )
                continue
            except httpx.HTTPError as exc:
                # 传输层异常（连接失败、超时、代理不可用等）不是 WebResearchError，
                # 这里统一包装为可重试错误，保证降级链继续尝试下一个供应商。
                wrapped = WebResearchError(
                    "WEB_SEARCH_UPSTREAM_ERROR",
                    f"{name} 搜索请求网络失败",
                    retryable=True,
                    details={"reason": type(exc).__name__},
                )
                attempts.append({"provider": name, "error_code": wrapped.code})
                last_error = wrapped
                logger.warning(
                    "搜索供应商 %s 网络失败(%s)，尝试降级到下一个",
                    name,
                    type(exc).__name__,
                )
                continue
            attempts.append({"provider": name, "error_code": None})
            return data, name, attempts
        raise WebResearchError(
            "WEB_SEARCH_ALL_PROVIDERS_FAILED",
            "所有已配置的搜索供应商均调用失败",
            retryable=bool(last_error and last_error.retryable),
            details={
                "attempts": attempts,
                "last_error": last_error.code if last_error else None,
            },
        )

    async def _search_serper(
        self,
        request: WebSearchInput,
        provider_cfg: Any,
    ) -> WebSearchData:
        count = min(request.max_results, self._settings.max_results)
        url = provider_cfg.api_url or "https://google.serper.dev/search"
        payload: dict[str, Any] = {"q": request.query, "num": count}
        if self._settings.search_language:
            payload["hl"] = self._settings.search_language.split("-", 1)[0]
        if request.freshness_days:
            payload["tbs"] = _google_freshness(request.freshness_days)
        async with self._http_client() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "X-API-KEY": provider_cfg.api_key,
                    "Content-Type": "application/json",
                },
            )
        body = self._decode_search_response("Serper", response)
        raw_results = body.get("organic") or []
        return self._collect_results(
            request.query,
            "Serper (Google)",
            raw_results[:count],
            title_key="title",
            url_key="link",
            snippet_key="snippet",
            date_key="date",
        )

    async def _search_tavily(
        self,
        request: WebSearchInput,
        provider_cfg: Any,
    ) -> WebSearchData:
        count = min(request.max_results, self._settings.max_results)
        url = provider_cfg.api_url or "https://api.tavily.com/search"
        payload: dict[str, Any] = {
            "api_key": provider_cfg.api_key,
            "query": request.query,
            "max_results": count,
            "search_depth": "basic",
        }
        if request.freshness_days:
            payload["days"] = request.freshness_days
        async with self._http_client() as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {provider_cfg.api_key}",
                    "Content-Type": "application/json",
                },
            )
        body = self._decode_search_response("Tavily", response)
        raw_results = body.get("results") or []
        return self._collect_results(
            request.query,
            "Tavily",
            raw_results[:count],
            title_key="title",
            url_key="url",
            snippet_key="content",
            date_key="published_date",
        )

    async def _search_google_cse(
        self,
        request: WebSearchInput,
        provider_cfg: Any,
    ) -> WebSearchData:
        count = min(request.max_results, self._settings.max_results, 10)
        url = provider_cfg.api_url or "https://www.googleapis.com/customsearch/v1"
        params: dict[str, Any] = {
            "key": provider_cfg.api_key,
            "cx": provider_cfg.cx,
            "q": request.query,
            "num": count,
        }
        if self._settings.search_language:
            params["hl"] = self._settings.search_language.split("-", 1)[0]
        if request.freshness_days:
            params["dateRestrict"] = f"d{request.freshness_days}"
        async with self._http_client() as client:
            response = await client.get(url, params=params)
        body = self._decode_search_response("Google Custom Search", response)
        raw_results = body.get("items") or []
        return self._collect_results(
            request.query,
            "Google Custom Search",
            raw_results[:count],
            title_key="title",
            url_key="link",
            snippet_key="snippet",
            date_key=None,
        )

    async def _search_serpapi(
        self,
        request: WebSearchInput,
        provider_cfg: Any,
    ) -> WebSearchData:
        count = min(request.max_results, self._settings.max_results)
        url = provider_cfg.api_url or "https://serpapi.com/search.json"
        params: dict[str, Any] = {
            "engine": "google",
            "api_key": provider_cfg.api_key,
            "q": request.query,
            "num": count,
        }
        if self._settings.search_language:
            params["hl"] = self._settings.search_language.split("-", 1)[0]
        if request.freshness_days:
            params["tbs"] = _google_freshness(request.freshness_days)
        async with self._http_client() as client:
            response = await client.get(url, params=params)
        body = self._decode_search_response("SerpAPI", response)
        raw_results = body.get("organic_results") or []
        return self._collect_results(
            request.query,
            "SerpAPI (Google)",
            raw_results[:count],
            title_key="title",
            url_key="link",
            snippet_key="snippet",
            date_key="date",
        )

    async def _search_brave(
        self,
        request: WebSearchInput,
        provider_cfg: Any,
    ) -> WebSearchData:
        count = min(request.max_results, self._settings.max_results)
        url = (
            provider_cfg.api_url
            or self._settings.search_api_url
            or "https://api.search.brave.com/res/v1/web/search"
        )
        params: dict[str, Any] = {
            "q": request.query,
            "count": count,
            "search_lang": self._settings.search_language,
        }
        freshness = _brave_freshness(request.freshness_days)
        if freshness:
            params["freshness"] = freshness
        async with self._http_client() as client:
            response = await client.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": provider_cfg.api_key,
                },
            )
        body = self._decode_search_response("Brave Search", response)
        raw_results = (body.get("web") or {}).get("results") or []
        results: list[WebSearchResult] = []
        for raw in raw_results[:count]:
            url_value = str(raw.get("url") or "").strip()
            title = str(raw.get("title") or "").strip()
            snippet = str(raw.get("description") or "").strip()
            if not url_value or not title:
                continue
            results.append(
                WebSearchResult(
                    rank=len(results) + 1,
                    title=title,
                    url=url_value,
                    snippet=snippet,
                    published_at=_optional_text(
                        raw.get("page_age") or raw.get("age")
                    ),
                    language=_optional_text(raw.get("language")),
                )
            )
        return WebSearchData(
            query=request.query,
            provider="Brave Search",
            results=results,
        )

    def _http_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(
            self._settings.timeout_seconds,
            connect=min(self._settings.timeout_seconds, 10),
        )
        return httpx.AsyncClient(timeout=timeout, transport=self._transport)

    @staticmethod
    def _decode_search_response(
        provider_label: str,
        response: httpx.Response,
    ) -> dict[str, Any]:
        """把搜索供应商响应统一成 dict，并把状态码映射为标准错误码。"""
        if response.status_code in {401, 403}:
            raise WebResearchError(
                "WEB_SEARCH_AUTH_FAILED",
                f"{provider_label} API Key 无效或权限不足",
            )
        if response.status_code in {402, 429}:
            raise WebResearchError(
                "WEB_SEARCH_RATE_LIMITED",
                f"{provider_label} 达到限流或免费额度上限",
                retryable=True,
                details={"status_code": response.status_code},
            )
        if response.status_code >= 500:
            raise WebResearchError(
                "WEB_SEARCH_UPSTREAM_ERROR",
                f"{provider_label} 服务暂时不可用",
                retryable=True,
                details={"status_code": response.status_code},
            )
        try:
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise WebResearchError(
                "WEB_SEARCH_INVALID_RESPONSE",
                f"{provider_label} 返回了无效响应",
                retryable=isinstance(exc, httpx.HTTPError),
                details={"status_code": response.status_code},
            ) from exc
        if not isinstance(body, dict):
            raise WebResearchError(
                "WEB_SEARCH_INVALID_RESPONSE",
                f"{provider_label} 返回了非对象响应",
            )
        return body

    @staticmethod
    def _collect_results(
        query: str,
        provider_label: str,
        raw_results: list[Any],
        *,
        title_key: str,
        url_key: str,
        snippet_key: str,
        date_key: str | None,
    ) -> WebSearchData:
        """把不同供应商的原始结果收敛成统一的 WebSearchResult 列表。"""
        results: list[WebSearchResult] = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url_value = str(raw.get(url_key) or "").strip()
            title = str(raw.get(title_key) or "").strip()
            snippet = str(raw.get(snippet_key) or "").strip()
            if not url_value or not title:
                continue
            published = (
                _optional_text(raw.get(date_key)) if date_key else None
            )
            results.append(
                WebSearchResult(
                    rank=len(results) + 1,
                    title=title,
                    url=url_value,
                    snippet=snippet,
                    published_at=published,
                    language=None,
                )
            )
        return WebSearchData(
            query=query,
            provider=provider_label,
            results=results,
        )

    async def _fetch_page(self, requested_url: str, max_chars: int) -> WebFetchData:
        timeout = httpx.Timeout(
            self._settings.timeout_seconds,
            connect=min(self._settings.timeout_seconds, 10),
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "FinancialResearchAgent/0.1"},
            transport=self._transport,
        ) as client:
            final_url, content_type, content = await self._fetch_with_redirects(
                client,
                requested_url,
            )

        decoded = content.decode("utf-8", errors="replace")
        if "html" in content_type:
            soup = BeautifulSoup(decoded, "html.parser")
            for element in soup(
                ["script", "style", "noscript", "form", "nav", "footer"]
            ):
                element.decompose()
            title = (
                soup.title.get_text(" ", strip=True)
                if soup.title
                else urlparse(final_url).netloc
            )
            text = soup.get_text("\n", strip=True)
        else:
            title = urlparse(final_url).path.rsplit("/", 1)[-1] or "网页文档"
            text = decoded.strip()
        normalized = _normalize_text(text)
        truncated = len(normalized) > max_chars
        selected = normalized[:max_chars]
        return WebFetchData(
            requested_url=requested_url,
            final_url=final_url,
            title=title[:500],
            content=selected,
            content_type=content_type.split(";", 1)[0],
            truncated=truncated,
            content_sha256=hashlib.sha256(selected.encode("utf-8")).hexdigest(),
        )

    async def _read_document(
        self,
        requested_url: str,
        max_chars: int,
    ) -> WebFetchData:
        timeout = httpx.Timeout(
            self._settings.timeout_seconds,
            connect=min(self._settings.timeout_seconds, 10),
        )
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={"User-Agent": "FinancialResearchAgent/0.1"},
            transport=self._transport,
        ) as client:
            final_url, content_type, content = await self._fetch_with_redirects(
                client,
                requested_url,
                allowed_content=(
                    "text/html",
                    "text/plain",
                    "text/markdown",
                    "application/pdf",
                ),
            )

        if "pdf" in content_type or final_url.lower().endswith(".pdf"):
            text = await asyncio.to_thread(_extract_pdf_text, content)
            title = final_url.rsplit("/", 1)[-1] or "PDF 文档"
        elif "html" in content_type:
            soup = BeautifulSoup(content.decode("utf-8", errors="replace"), "html.parser")
            for element in soup(["script", "style", "noscript", "form", "nav", "footer"]):
                element.decompose()
            title = (
                soup.title.get_text(" ", strip=True)
                if soup.title
                else urlparse(final_url).netloc
            )
            text = soup.get_text("\n", strip=True)
        else:
            title = urlparse(final_url).path.rsplit("/", 1)[-1] or "指定文档"
            text = content.decode("utf-8", errors="replace").strip()

        normalized = _normalize_text(text)
        truncated = len(normalized) > max_chars
        selected = normalized[:max_chars]
        if not selected:
            raise WebResearchError(
                "DOCUMENT_EMPTY",
                "目标文档没有可抽取的正文",
                details={"final_url": final_url},
            )
        return WebFetchData(
            requested_url=requested_url,
            final_url=final_url,
            title=title[:500],
            content=selected,
            content_type=content_type.split(";", 1)[0],
            truncated=truncated,
            content_sha256=hashlib.sha256(selected.encode("utf-8")).hexdigest(),
        )

    async def _fetch_with_redirects(
        self,
        client: httpx.AsyncClient,
        requested_url: str,
        *,
        allowed_content: tuple[str, ...] = (
            "text/html",
            "text/plain",
            "text/markdown",
        ),
    ) -> tuple[str, str, bytes]:
        current_url = requested_url
        for redirect_count in range(4):
            await self._validate_public_url(current_url)
            response = await client.send(
                client.build_request("GET", current_url),
                stream=True,
            )
            try:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise WebResearchError(
                            "WEB_FETCH_INVALID_REDIRECT",
                            "目标网页返回了缺少 Location 的重定向",
                        )
                    if redirect_count >= 3:
                        raise WebResearchError(
                            "WEB_FETCH_TOO_MANY_REDIRECTS",
                            "目标网页重定向次数超过限制",
                        )
                    next_url = urljoin(current_url, location)
                    await self._validate_public_url(next_url)
                    current_url = next_url
                    continue
                if response.status_code >= 500:
                    raise WebResearchError(
                        "WEB_FETCH_UPSTREAM_ERROR",
                        "目标网页暂时不可用",
                        retryable=True,
                        details={"status_code": response.status_code},
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise WebResearchError(
                        "WEB_FETCH_HTTP_ERROR",
                        "目标网页请求失败",
                        details={"status_code": response.status_code},
                    ) from exc
                final_url = str(response.url)
                await self._validate_public_url(final_url)
                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()
                if not any(marker in content_type for marker in allowed_content):
                    raise WebResearchError(
                        "WEB_FETCH_UNSUPPORTED_CONTENT",
                        "目标内容类型不受支持",
                        details={"content_type": content_type or "unknown"},
                    )
                content = await self._read_limited(response)
                return final_url, content_type, content
            finally:
                await response.aclose()
        raise WebResearchError(
            "WEB_FETCH_TOO_MANY_REDIRECTS",
            "目标网页重定向次数超过限制",
        )

    async def _read_limited(self, response: httpx.Response) -> bytes:
        maximum = self._settings.max_fetch_bytes
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > maximum:
            raise WebResearchError(
                "WEB_FETCH_TOO_LARGE",
                "目标网页超过允许大小",
            )
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > maximum:
                raise WebResearchError(
                    "WEB_FETCH_TOO_LARGE",
                    "目标网页超过允许大小",
                )
            chunks.append(chunk)
        return b"".join(chunks)

    async def _validate_public_url(self, url: str) -> None:
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise WebResearchError(
                "WEB_FETCH_INVALID_URL",
                "只允许不含用户凭证的公网 http/https URL",
            )
        host = parsed.hostname.lower().rstrip(".")
        allowed = [
            item.lower().rstrip(".")
            for item in self._settings.allowed_domains
        ]
        if allowed and not any(
            host == item or host.endswith(f".{item}") for item in allowed
        ):
            raise WebResearchError(
                "WEB_FETCH_DOMAIN_BLOCKED",
                "目标域名不在网页抓取 allowlist",
                details={"host": host},
            )
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
            )
        except socket.gaierror as exc:
            raise WebResearchError(
                "WEB_FETCH_DNS_FAILED",
                "目标网页域名解析失败",
                retryable=True,
                details={"host": host},
            ) from exc
        for item in addresses:
            address = ipaddress.ip_address(item[4][0])
            if not address.is_global:
                raise WebResearchError(
                    "WEB_FETCH_PRIVATE_ADDRESS",
                    "禁止访问本机、私网或保留地址",
                    details={"host": host},
                )

    def _ensure_enabled(self) -> None:
        if not self._settings.enabled:
            raise WebResearchError(
                "WEB_RESEARCH_DISABLED",
                "网页研究 MCP 当前未启用",
            )

    @staticmethod
    def _error_envelope(
        tool: WebToolName,
        exc: Exception,
        queried_at: datetime,
    ) -> WebToolEnvelope:
        if isinstance(exc, WebResearchError):
            error = WebToolError(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
        else:
            error = WebToolError(
                code="WEB_RESEARCH_INTERNAL_ERROR",
                message="网页研究工具执行失败",
                details={"reason": str(exc)},
            )
        return WebToolEnvelope(
            tool=tool,
            ok=False,
            queried_at=queried_at,
            error=error,
        )


def _brave_freshness(days: int | None) -> str | None:
    if days is None:
        return None
    if days <= 1:
        return "pd"
    if days <= 7:
        return "pw"
    if days <= 31:
        return "pm"
    return "py"


def _google_freshness(days: int | None) -> str | None:
    """Google/Serper/SerpAPI 通用的 tbs 时间过滤（qdr:d/w/m/y）。"""
    if days is None:
        return None
    if days <= 1:
        return "qdr:d"
    if days <= 7:
        return "qdr:w"
    if days <= 31:
        return "qdr:m"
    return "qdr:y"


def _sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_text(value: str) -> str:
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_pdf_text(content: bytes) -> str:
    """抽取 PDF 全部页面的文本；解析失败时抛出可控错误。"""
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # noqa: BLE001 - 统一转成可控错误
        raise WebResearchError(
            "DOCUMENT_PARSE_FAILED",
            "无法解析 PDF 文档",
            details={"reason": str(exc)},
        ) from exc
