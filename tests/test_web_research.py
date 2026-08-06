from __future__ import annotations

import httpx
import pytest

from fund_advisor_mcp.web import (
    WebFetchData,
    WebResearchError,
    WebResearchService,
    WebSearchData,
    WebSourceType,
)


def _web_config(test_config, **updates):
    return test_config.model_copy(
        update={
            "web_research": test_config.web_research.model_copy(
                update={
                    "enabled": True,
                    "api_key": "test-key",
                    **updates,
                }
            ),
        }
    )


@pytest.mark.asyncio
async def test_web_search_returns_non_numeric_audited_envelope(
    test_config,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Subscription-Token"] == "test-key"
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "监管政策背景",
                            "url": "https://example.com/policy",
                            "description": "用于研究政策背景的网页摘要。",
                            "page_age": "2 days ago",
                        },
                        {
                            "title": "公开博主的基金分享",
                            "url": "https://xueqiu.com/123456/789",
                            "description": "个人公开观点。",
                            "page_age": "1 day ago",
                        },
                        {
                            "title": "行业深度报告",
                            "url": "https://research.example.com/report",
                            "description": "公开研究报告入口。",
                        }
                    ]
                }
            },
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(
        query="近期基金监管政策",
        max_results=5,
        freshness_days=7,
    )

    assert envelope.ok
    assert isinstance(envelope.data, WebSearchData)
    assert envelope.data.results[0].title == "监管政策背景"
    assert envelope.data.results[1].source_type is WebSourceType.CREATOR
    assert envelope.data.results[1].domain == "xueqiu.com"
    assert envelope.data.results[2].source_type is WebSourceType.RESEARCH
    assert envelope.data_policy.numeric_allowed is False
    assert envelope.data_policy.may_override_market_tools is False
    assert envelope.data_audit[0].validation == "passed"
    assert envelope.data_audit[0].response_sha256


@pytest.mark.asyncio
async def test_web_search_filters_requested_source_types(test_config) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "财经媒体文章",
                            "url": "https://www.stcn.com/article",
                            "description": "媒体背景。",
                        },
                        {
                            "title": "公开博主观点",
                            "url": "https://xueqiu.com/123456/789",
                            "description": "个人公开观点。",
                        },
                    ]
                }
            },
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(
        query='"600519" site:xueqiu.com',
        max_results=5,
        source_types=["creator"],
    )

    assert envelope.ok
    assert isinstance(envelope.data, WebSearchData)
    assert [item.title for item in envelope.data.results] == ["公开博主观点"]
    assert envelope.data.results[0].rank == 1
    assert envelope.data_audit[0].request["source_types"] == ["creator"]


@pytest.mark.asyncio
async def test_web_fetch_cleans_html_and_hashes_selected_content(
    test_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>政策说明</title></head>"
                "<body><nav>导航</nav><article>这是可引用的政策背景。</article>"
                "<script>ignore()</script></body></html>"
            ),
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    async def allow_url(_url: str) -> None:
        return None

    monkeypatch.setattr(service, "_validate_public_url", allow_url)
    envelope = await service.web_fetch(
        url="https://example.com/policy",
        max_chars=1000,
    )

    assert envelope.ok
    assert isinstance(envelope.data, WebFetchData)
    assert envelope.data.title == "政策说明"
    assert "可引用的政策背景" in envelope.data.content
    assert "ignore" not in envelope.data.content
    assert "导航" not in envelope.data.content
    assert envelope.data.content_sha256


@pytest.mark.asyncio
async def test_web_fetch_rejects_private_address(test_config) -> None:
    service = WebResearchService(_web_config(test_config))

    envelope = await service.web_fetch(
        url="http://127.0.0.1/private",
        max_chars=1000,
    )

    assert not envelope.ok
    assert envelope.error is not None
    assert envelope.error.code == "WEB_FETCH_PRIVATE_ADDRESS"
    assert envelope.data is None


@pytest.mark.asyncio
async def test_web_fetch_validates_redirect_before_following(
    test_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    async def validate(url: str) -> None:
        if "127.0.0.1" in url:
            raise WebResearchError(
                "WEB_FETCH_PRIVATE_ADDRESS",
                "禁止访问私网地址",
            )

    monkeypatch.setattr(service, "_validate_public_url", validate)
    envelope = await service.web_fetch(
        url="https://example.com/redirect",
        max_chars=1000,
    )

    assert not envelope.ok
    assert envelope.error is not None
    assert envelope.error.code == "WEB_FETCH_PRIVATE_ADDRESS"
    assert requested_urls == ["https://example.com/redirect"]


def _chain_config(test_config, chain, providers):
    return test_config.model_copy(
        update={
            "web_research": test_config.web_research.model_copy(
                update={
                    "enabled": True,
                    "api_key": "",
                    "search_chain": chain,
                    "providers": providers,
                }
            ),
        }
    )


@pytest.mark.asyncio
async def test_search_chain_falls_back_to_next_provider(test_config) -> None:
    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host)
        # 第一个供应商（serper）报 429 超额，触发降级
        if request.url.host == "google.serper.dev":
            return httpx.Response(429, json={"message": "quota"})
        # 第二个供应商（tavily）正常返回
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "政策解读",
                        "url": "https://example.com/policy",
                        "content": "来自 Tavily 的政策背景摘要。",
                    }
                ]
            },
        )

    service = WebResearchService(
        _chain_config(
            test_config,
            ["serper", "tavily"],
            {
                "serper": {"api_key": "serper-key"},
                "tavily": {"api_key": "tavily-key"},
            },
        ),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(query="基金监管政策", max_results=3)

    assert envelope.ok
    assert isinstance(envelope.data, WebSearchData)
    assert envelope.data.provider == "Tavily"
    assert envelope.data.results[0].title == "政策解读"
    # serper 先被尝试且失败，随后降级到 tavily
    assert called_hosts == ["google.serper.dev", "api.tavily.com"]
    audit_request = envelope.data_audit[0].request
    assert audit_request["provider"] == "tavily"
    assert audit_request["attempts"] == [
        {"provider": "serper", "error_code": "WEB_SEARCH_RATE_LIMITED"},
        {"provider": "tavily", "error_code": None},
    ]


@pytest.mark.asyncio
async def test_search_chain_skips_providers_without_credentials(
    test_config,
) -> None:
    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host)
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "title": "Serper 命中",
                        "link": "https://example.com/a",
                        "snippet": "摘要",
                    }
                ]
            },
        )

    # 链条含 tavily 但未配置 Key，应被跳过，直接调用 serper。
    service = WebResearchService(
        _chain_config(
            test_config,
            ["tavily", "serper"],
            {"serper": {"api_key": "serper-key"}},
        ),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(query="基金政策", max_results=2)

    assert envelope.ok
    assert called_hosts == ["google.serper.dev"]
    assert envelope.data.provider == "Serper (Google)"


@pytest.mark.asyncio
async def test_search_chain_reports_not_configured_when_empty(
    test_config,
) -> None:
    service = WebResearchService(
        _chain_config(test_config, ["serper", "tavily"], {}),
    )

    envelope = await service.web_search(query="基金政策", max_results=2)

    assert not envelope.ok
    assert envelope.error is not None
    assert envelope.error.code == "WEB_SEARCH_NOT_CONFIGURED"
    assert envelope.data is None


@pytest.mark.asyncio
async def test_search_chain_all_providers_failed(test_config) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid key"})

    service = WebResearchService(
        _chain_config(
            test_config,
            ["serper", "brave"],
            {
                "serper": {"api_key": "bad-1"},
                "brave": {"api_key": "bad-2"},
            },
        ),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(query="基金政策", max_results=2)

    assert not envelope.ok
    assert envelope.error is not None
    assert envelope.error.code == "WEB_SEARCH_ALL_PROVIDERS_FAILED"
    assert envelope.data_policy.numeric_allowed is False


def test_resolved_chain_orders_and_filters(test_config) -> None:
    settings = test_config.web_research.model_copy(
        update={
            "enabled": True,
            "search_chain": ["google_cse", "serper", "unknown", "tavily"],
            "providers": {
                # google_cse 缺 cx，凭证不全应被过滤
                "google_cse": {"api_key": "k"},
                "serper": {"api_key": "serper-key"},
                # tavily 显式禁用
                "tavily": {"api_key": "t", "enabled": False},
            },
        }
    )
    resolved = [name for name, _ in settings.resolved_chain()]
    assert resolved == ["serper"]


@pytest.mark.asyncio
async def test_search_chain_falls_back_on_network_error(test_config) -> None:
    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host)
        # serper 抛传输层异常（模拟代理不可用），必须降级而非击穿
        if request.url.host == "google.serper.dev":
            raise httpx.ConnectError("proxy unreachable", request=request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "备选来源",
                        "url": "https://example.com/x",
                        "content": "Tavily 兜底返回的正文。",
                    }
                ]
            },
        )

    service = WebResearchService(
        _chain_config(
            test_config,
            ["serper", "tavily"],
            {
                "serper": {"api_key": "serper-key"},
                "tavily": {"api_key": "tavily-key"},
            },
        ),
        transport=httpx.MockTransport(handler),
    )

    envelope = await service.web_search(query="基金政策", max_results=2)

    assert envelope.ok
    assert envelope.data.provider == "Tavily"
    assert called_hosts == ["google.serper.dev", "api.tavily.com"]
    attempts = envelope.data_audit[0].request["attempts"]
    assert attempts[0] == {
        "provider": "serper",
        "error_code": "WEB_SEARCH_UPSTREAM_ERROR",
    }


@pytest.mark.asyncio
async def test_serper_adapter_parses_organic_results(test_config) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["host"] = request.url.host
        captured["auth"] = request.headers.get("X-API-KEY")
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "title": "证监会发布新规",
                        "link": "https://csrc.gov.cn/a",
                        "snippet": "政策摘要。",
                        "date": "2026-07-01",
                    },
                    {"title": "", "link": "https://x.com", "snippet": "无标题跳过"},
                ]
            },
        )

    service = WebResearchService(
        _chain_config(test_config, ["serper"], {"serper": {"api_key": "sk"}}),
        transport=httpx.MockTransport(handler),
    )
    envelope = await service.web_search(query="基金新规", max_results=5)

    assert captured["host"] == "google.serper.dev"
    assert captured["auth"] == "sk"
    assert envelope.data.provider == "Serper (Google)"
    assert len(envelope.data.results) == 1
    assert envelope.data.results[0].url == "https://csrc.gov.cn/a"
    assert envelope.data.results[0].published_at == "2026-07-01"


@pytest.mark.asyncio
async def test_google_cse_adapter_requires_cx_and_parses_items(
    test_config,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["cx"] = request.url.params.get("cx")
        captured["key"] = request.url.params.get("key")
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "title": "政策解读",
                        "link": "https://example.gov.cn/p",
                        "snippet": "官方解读。",
                    }
                ]
            },
        )

    service = WebResearchService(
        _chain_config(
            test_config,
            ["google_cse"],
            {"google_cse": {"api_key": "gk", "cx": "engine-1"}},
        ),
        transport=httpx.MockTransport(handler),
    )
    envelope = await service.web_search(query="基金监管", max_results=5)

    assert captured["cx"] == "engine-1"
    assert captured["key"] == "gk"
    assert envelope.data.provider == "Google Custom Search"
    assert envelope.data.results[0].url == "https://example.gov.cn/p"


@pytest.mark.asyncio
async def test_search_returns_empty_without_falling_back(test_config) -> None:
    """供应商正常但零结果应视为成功，不再降级到下一个。"""
    called_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        called_hosts.append(request.url.host)
        return httpx.Response(200, json={"organic": []})

    service = WebResearchService(
        _chain_config(
            test_config,
            ["serper", "tavily"],
            {
                "serper": {"api_key": "sk"},
                "tavily": {"api_key": "tk"},
            },
        ),
        transport=httpx.MockTransport(handler),
    )
    envelope = await service.web_search(query="不存在的主题", max_results=3)

    assert envelope.ok
    assert envelope.data.results == []
    assert called_hosts == ["google.serper.dev"]


@pytest.mark.asyncio
async def test_document_read_extracts_html_body(
    test_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """document_read 读取 HTML 官方文档，正文清洗且标记 numeric_allowed=false。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><title>基金合同</title></head>"
                "<body><nav>导航</nav>"
                "<article>本基金的申购赎回条款如下所述。</article>"
                "<script>track()</script></body></html>"
            ),
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    async def allow_url(_url: str) -> None:
        return None

    monkeypatch.setattr(service, "_validate_public_url", allow_url)
    envelope = await service.document_read(
        url="https://sse.com.cn/contract.html",
        max_chars=5000,
    )

    assert envelope.ok
    assert isinstance(envelope.data, WebFetchData)
    assert envelope.data.title == "基金合同"
    assert "申购赎回条款" in envelope.data.content
    assert "track" not in envelope.data.content
    assert "导航" not in envelope.data.content
    assert envelope.data_policy.numeric_allowed is False
    assert envelope.data_audit[0].operation.value == "document_read"
    assert envelope.data_audit[0].response_sha256


@pytest.mark.asyncio
async def test_document_read_accepts_pdf_content(
    test_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF 是 document_read 相对 web_fetch 的关键差异：允许 application/pdf。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF-1.4 fake bytes",
        )

    service = WebResearchService(
        _web_config(test_config),
        transport=httpx.MockTransport(handler),
    )

    async def allow_url(_url: str) -> None:
        return None

    monkeypatch.setattr(service, "_validate_public_url", allow_url)
    # 用桩替换真实 pypdf 解析，保持测试无外部依赖。
    monkeypatch.setattr(
        "fund_advisor_mcp.web.service._extract_pdf_text",
        lambda _content: "招募说明书 PDF 正文段落。",
    )

    envelope = await service.document_read(
        url="https://sse.com.cn/prospectus.pdf",
        max_chars=5000,
    )

    assert envelope.ok
    assert isinstance(envelope.data, WebFetchData)
    assert envelope.data.content_type == "application/pdf"
    assert "招募说明书" in envelope.data.content


@pytest.mark.asyncio
async def test_document_read_rejects_private_address(test_config) -> None:
    """document_read 复用 SSRF 校验，私网地址必须被拦截。"""
    service = WebResearchService(_web_config(test_config))

    envelope = await service.document_read(
        url="http://127.0.0.1/internal.pdf",
        max_chars=5000,
    )

    assert not envelope.ok
    assert envelope.error is not None
    assert envelope.error.code == "WEB_FETCH_PRIVATE_ADDRESS"
    assert envelope.data is None
