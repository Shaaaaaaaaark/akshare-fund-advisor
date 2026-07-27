from __future__ import annotations

import pytest
from conftest import FakeFundToolClient

from financial_agent.orchestration import FinancialAgentGraph
from financial_agent.rag import (
    DocumentHit,
    RetrievalAssessment,
    RetrievalChannel,
    RetrievalPlan,
    RetrievalQuery,
)


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
async def test_agentic_rag_replans_until_evidence_is_sufficient(test_config) -> None:
    class LoopRAG:
        async def plan(self, **kwargs):
            round_number = kwargs["round_number"]
            return RetrievalPlan(
                round_number=round_number,
                queries=[
                    RetrievalQuery(
                        query=(
                            "510300 投资范围"
                            if round_number == 1
                            else "510300 费用"
                        ),
                        channel=RetrievalChannel.KNOWLEDGE,
                        reason="覆盖产品研究问题",
                    )
                ],
                reason="测试多轮规划",
            )

        async def execute(self, plan):
            topic = "投资范围" if plan.round_number == 1 else "费用"
            return (
                [
                    DocumentHit(
                        channel=RetrievalChannel.KNOWLEDGE,
                        title="示例基金招募说明书",
                        url="https://sse.com.cn/example.pdf",
                        text=f"本段为{topic}相关的官方文档内容，用于测试充分性判断。",
                        page=plan.round_number,
                        version="2026-01",
                        metadata={"chunk_id": f"chunk-{plan.round_number}"},
                    )
                ],
                [],
            )

        async def assess(self, *, plan, **_kwargs):
            return RetrievalAssessment(
                sufficient=plan.round_number == 2,
                retryable=plan.round_number == 1,
                reason=(
                    "仍缺少费用信息"
                    if plan.round_number == 1
                    else "投资范围和费用均已覆盖"
                ),
                missing_aspects=(
                    ["费用"] if plan.round_number == 1 else []
                ),
            )

    graph = FinancialAgentGraph(
        test_config,
        tool_client=FakeFundToolClient(),
        rag=LoopRAG(),
    )

    result = await graph.ainvoke(
        graph.initial_state("分析基金510300的投资范围和费用")
    )

    assert result["status"] == "completed"
    assert result["retrieval_round"] == 2
    assert len(result["retrieval_trace"]) == 2
    assert result["retrieval_trace"][0]["assessment"]["sufficient"] is False
    assert result["retrieval_trace"][1]["assessment"]["sufficient"] is True
    assert len(result["retrieval_results"]) == 2


@pytest.mark.asyncio
async def test_agentic_rag_hard_stops_at_configured_round_limit(test_config) -> None:
    class EndlessRAG:
        async def plan(self, **kwargs):
            return RetrievalPlan(
                round_number=kwargs["round_number"],
                queries=[
                    RetrievalQuery(
                        query="继续检索",
                        channel=RetrievalChannel.KNOWLEDGE,
                        reason="测试轮次硬限制",
                    )
                ],
                reason="持续请求下一轮",
            )

        async def execute(self, _plan):
            return [], []

        async def assess(self, **_kwargs):
            return RetrievalAssessment(
                sufficient=False,
                retryable=True,
                reason="模型持续要求重试",
                missing_aspects=["更多资料"],
            )

    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={"max_rounds": 2}
            )
        }
    )
    graph = FinancialAgentGraph(
        config,
        tool_client=FakeFundToolClient(),
        rag=EndlessRAG(),
    )

    result = await graph.ainvoke(graph.initial_state("分析基金510300"))

    assert result["retrieval_round"] == 2
    assert len(result["retrieval_trace"]) == 2
    assert result["retrieval_assessment"]["retryable"] is False
    assert "最大检索轮次" in result["retrieval_assessment"]["reason"]
