from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import FakeFundToolClient

from financial_agent.orchestration import FinancialAgentGraph
from financial_agent.web_research import (
    WebFetchData,
    WebSearchData,
    WebSearchResult,
    WebToolEnvelope,
    WebToolName,
)
from financial_agent.web_research.schemas import WebAuditRecord


@pytest.mark.asyncio
async def test_graph_completes_audited_valuation(test_config) -> None:
    client = FakeFundToolClient()
    graph = FinancialAgentGraph(test_config, tool_client=client)

    result = await graph.ainvoke(graph.initial_state("沪深300现在贵吗"))

    assert result["status"] == "completed"
    assert result["gate_decision"]["grade"] == "A"
    assert result["final_report"]["facts"]
    assert client.calls[0][0] == "index_valuation"


@pytest.mark.asyncio
async def test_graph_stops_on_entity_ambiguity(test_config) -> None:
    client = FakeFundToolClient(
        error_code="AMBIGUOUS_FUND",
        error_details={
            "candidates": [
                {"code": "000001", "name": "示例 A"},
                {"code": "000002", "name": "示例 C"},
            ]
        },
    )
    graph = FinancialAgentGraph(test_config, tool_client=client)

    result = await graph.ainvoke(graph.initial_state("分析示例基金"))

    assert result["status"] == "need_clarification"
    assert len(result["clarification"]["candidates"]) == 2
    assert "final_report" not in result


@pytest.mark.asyncio
async def test_policy_block_does_not_call_tool(test_config) -> None:
    client = FakeFundToolClient()
    graph = FinancialAgentGraph(test_config, tool_client=client)

    result = await graph.ainvoke(graph.initial_state("沪深300保证收益，直接帮我买"))

    assert result["status"] == "policy_blocked"
    assert result["gate_decision"]["grade"] == "E"
    assert client.calls == []
    assert result["final_report"]["facts"] == []


@pytest.mark.asyncio
async def test_etf_analysis_fetches_full_tracking_index_chart(test_config) -> None:
    class ETFClient(FakeFundToolClient):
        async def call(self, tool, arguments):
            envelope = await super().call(tool, arguments)
            if tool == "fund_analyze" and envelope.data is not None:
                envelope.data["index_valuation"] = {
                    "available": True,
                    "index_name": "沪深300",
                }
            return envelope

    client = ETFClient()
    graph = FinancialAgentGraph(test_config, tool_client=client)

    result = await graph.ainvoke(graph.initial_state("分析基金510300"))

    assert result["status"] == "completed"
    assert [item[0] for item in client.calls] == [
        "fund_analyze",
        "index_valuation",
    ]
    assert client.calls[1][1]["index"] == "沪深300"


@pytest.mark.asyncio
async def test_web_research_intent_gathers_external_context(test_config) -> None:
    """网页研究意图应调用 web-research MCP，并把命中转成低置信度背景证据。"""
    now = datetime.now(timezone.utc)

    class FakeWebClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def call(self, tool, arguments):
            self.calls.append((tool, arguments))
            if tool == "web_search":
                return WebToolEnvelope(
                    tool=WebToolName.WEB_SEARCH,
                    ok=True,
                    queried_at=now,
                    data=WebSearchData(
                        query=arguments["query"],
                        provider="Serper (Google)",
                        results=[
                            WebSearchResult(
                                rank=1,
                                title="监管政策解读",
                                url="https://csrc.gov.cn/policy",
                                snippet="政策背景摘要。",
                            )
                        ],
                    ),
                    data_audit=[
                        WebAuditRecord(
                            operation=WebToolName.WEB_SEARCH,
                            provider="Serper (Google)",
                            request={"query": arguments["query"]},
                            validation="passed",
                            response_sha256="search-hash",
                            result_count=1,
                        )
                    ],
                )
            return WebToolEnvelope(
                tool=WebToolName.WEB_FETCH,
                ok=True,
                queried_at=now,
                data=WebFetchData(
                    requested_url=arguments["url"],
                    final_url=arguments["url"],
                    title="监管政策解读",
                    content="抓取后的政策背景正文，仅作定性参考。",
                    content_type="text/html",
                    truncated=False,
                    content_sha256="fetch-hash",
                ),
                data_audit=[
                    WebAuditRecord(
                        operation=WebToolName.WEB_FETCH,
                        provider="Public Web",
                        request={"url": arguments["url"]},
                        validation="passed",
                        response_sha256="fetch-hash",
                        result_count=1,
                    )
                ],
            )

        async def healthcheck(self):
            return True

    fake = FakeWebClient()
    graph = FinancialAgentGraph(
        test_config,
        tool_client=FakeFundToolClient(),
        web_client=fake,
    )

    result = await graph.ainvoke(
        graph.initial_state("帮我查新闻：近期基金监管政策背景")
    )

    assert result["intent"] == "web_research"
    assert [item[0] for item in fake.calls] == ["web_search", "web_fetch"]
    assert result["external_context"]
    hit = result["external_context"][0]
    assert hit["channel"] == "web"
    assert hit["text"] == "抓取后的政策背景正文，仅作定性参考。"
    # 网页背景证据必须是低置信度、不可覆盖市场数值。
    web_evidence = [
        item
        for item in result["evidence"]
        if item.get("field") == "document_excerpt"
    ]
    assert web_evidence
    assert all(item["numeric_allowed"] is False for item in web_evidence)


@pytest.mark.asyncio
async def test_web_research_survives_channel_failure(test_config) -> None:
    """外部通道失败不应阻断主流程，只记录降级警告与错误。"""

    class BrokenWebClient:
        async def call(self, tool, arguments):
            raise RuntimeError("proxy unreachable")

        async def healthcheck(self):
            return True

    graph = FinancialAgentGraph(
        test_config,
        tool_client=FakeFundToolClient(),
        web_client=BrokenWebClient(),
    )

    result = await graph.ainvoke(
        graph.initial_state("帮我查新闻：近期基金监管政策背景")
    )

    assert result["intent"] == "web_research"
    assert result["external_context"] == []
    assert any(
        item.get("code") == "EXTERNAL_CONTEXT_FAILED"
        for item in result.get("errors", [])
    )
