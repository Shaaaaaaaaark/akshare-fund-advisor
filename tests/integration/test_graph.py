from __future__ import annotations

import pytest
from conftest import FakeFundToolClient

from financial_agent.orchestration import FinancialAgentGraph


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
