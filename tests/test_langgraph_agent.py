from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from fund_advisor_agent.associations import RuleBasedAssociationModel
from fund_advisor_agent.graph import build_agent_graph, run_agent
from fund_advisor_agent.model_client import OpenAIAssociationModel
from fund_advisor_agent.nodes import AgentNodes
from fund_advisor_agent.policies import classify_question
from fund_advisor_agent.state import (
    AgentState,
    AgentStatus,
    AssociationDraft,
    Confidence,
    FactRef,
    Intent,
    IntentDecision,
    RegisteredTool,
    Relationship,
    ToolCallSpec,
    ToolExecution,
)
from fund_advisor_agent.validator import (
    validate_associations,
    validate_tool_results,
)
from fund_advisor_mcp.config import AppConfig, ModelConfig
from fund_advisor_mcp.fund.schemas import (
    ToolEnvelope,
    ToolError,
    ToolName,
)
from fund_advisor_mcp.web.schemas import (
    WebAuditRecord,
    WebDataPolicy,
    WebSearchData,
    WebSearchResult,
    WebSourceType,
    WebToolEnvelope,
    WebToolError,
    WebToolName,
)


class FakeFundClient:
    def __init__(self, envelope: ToolEnvelope) -> None:
        self.envelope = envelope
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> ToolEnvelope:
        self.calls.append((tool, arguments))
        return self.envelope

    async def healthcheck(self) -> bool:
        return True


class FakeWebClient:
    def __init__(self, envelope: WebToolEnvelope | None = None) -> None:
        self.envelope = envelope or _web_envelope()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(
        self,
        tool: str,
        arguments: dict[str, Any],
    ) -> WebToolEnvelope:
        self.calls.append((tool, arguments))
        envelope = self.envelope.model_copy(deep=True)
        if tool == "web_search" and isinstance(envelope.data, WebSearchData):
            envelope.data.query = str(arguments.get("query") or "")
        return envelope

    async def healthcheck(self) -> bool:
        return True


class FailingAssociationModel:
    async def build_associations(self, _facts, _question):
        raise TimeoutError("model timeout")


class InvalidAssociationModel:
    async def build_associations(self, _facts, _question):
        return [{"unexpected": "payload"}]


class EmptyAssociationModel:
    async def build_associations(self, _facts, _question):
        return []


class FakeAssociationModel:
    async def build_associations(self, facts, _question):
        market_facts = [
            fact for fact in facts if fact.source_kind == "market"
        ]
        return [
            AssociationDraft(
                evidence_refs=[
                    market_facts[0].fact_id,
                    market_facts[1].fact_id,
                ],
                relationship=Relationship.CONTRAST,
                explanation="PE 与 PB 应分别观察其历史位置。",
                confidence=Confidence.HIGH,
            )
        ]


class FakeIntentClassifier:
    async def classify(self, _question: str) -> IntentDecision:
        return IntentDecision(
            intent=Intent.FUND_ANALYSIS,
            entities=["000001"],
            confidence=0.9,
        )


def _config() -> AppConfig:
    return AppConfig().model_copy(
        update={
            "mcp": AppConfig().mcp.model_copy(update={"transport": "inprocess"}),
            "web_research": AppConfig().web_research.model_copy(
                update={"transport": "inprocess", "enabled": True}
            ),
        }
    )


def _stock_envelope() -> ToolEnvelope:
    return ToolEnvelope(
        tool=ToolName.STOCK_VALUATION,
        ok=True,
        queried_at=datetime.now(timezone.utc),
        data={
            "ok": True,
            "action": "stock_valuation",
            "stock": {"code": "600519", "name": "贵州茅台"},
            "lookback": {"latest_date": "2026-08-04"},
            "summary": {
                "pe_ttm": {
                    "current": 22.1,
                    "percentile": 61.0,
                    "level": "upper_middle",
                },
                "pb": {
                    "current": 7.2,
                    "percentile": 55.0,
                    "level": "middle",
                },
                "stock_price": {
                    "current": 1420.0,
                    "unit": "元",
                    "adjustment": "前复权",
                },
                "combined_percentile": None,
                "combined_percentile_policy": "禁止将 PE 与 PB 分位简单平均",
            },
        },
        data_audit=[
            {
                "interface": "stock_zh_valuation_baidu",
                "validation": "passed",
                "frame_sha256": "pe-audit",
                "parameters": {
                    "kwargs": {"indicator": "市盈率(TTM)"}
                },
            },
            {
                "interface": "stock_zh_valuation_baidu",
                "validation": "passed",
                "frame_sha256": "pb-audit",
                "parameters": {"kwargs": {"indicator": "市净率"}},
            },
            {
                "interface": "stock_zh_a_daily",
                "validation": "passed",
                "frame_sha256": "price-audit",
                "parameters": {"kwargs": {"adjust": "qfq"}},
            },
        ],
        data_policy={"ai_may_generate_market_data": False},
    )


def _error_envelope(code: str) -> ToolEnvelope:
    return ToolEnvelope(
        tool=ToolName.STOCK_VALUATION,
        ok=False,
        queried_at=datetime.now(timezone.utc),
        data_policy={"ai_may_generate_market_data": False},
        error=ToolError(
            code=code,
            message="fake error",
            details={"candidates": [{"code": "600519"}]},
        ),
    )


def _web_envelope(
    *,
    title: str = "监管政策背景",
    url: str = "https://example.com/policy",
    source_type: WebSourceType = WebSourceType.OTHER,
    domain: str | None = "example.com",
) -> WebToolEnvelope:
    return WebToolEnvelope(
        tool=WebToolName.WEB_SEARCH,
        ok=True,
        queried_at=datetime.now(timezone.utc),
        data=WebSearchData(
            query="基金监管政策",
            provider="Fake",
            results=[
                WebSearchResult(
                    rank=1,
                    title=title,
                    url=url,
                    snippet="网页中包含历史数字 123，但不能作为市场事实。",
                    source_type=source_type,
                    domain=domain,
                )
            ],
        ),
        data_audit=[
            WebAuditRecord(
                operation=WebToolName.WEB_SEARCH,
                provider="Fake",
                request={"query": "基金监管政策"},
                validation="passed",
                response_sha256="web-audit",
                result_count=1,
            )
        ],
        data_policy=WebDataPolicy(),
    )


def _web_error_envelope() -> WebToolEnvelope:
    return WebToolEnvelope(
        tool=WebToolName.WEB_SEARCH,
        ok=False,
        queried_at=datetime.now(timezone.utc),
        error=WebToolError(
            code="WEB_SEARCH_ALL_PROVIDERS_FAILED",
            message="搜索供应商暂时不可用",
            retryable=True,
        ),
    )


@pytest.mark.asyncio
async def test_stock_graph_uses_registered_tool_and_audited_facts() -> None:
    fund = FakeFundClient(_stock_envelope())
    graph = build_agent_graph(
        config=_config(),
        fund_client=fund,
        web_client=FakeWebClient(),
        association_model=FakeAssociationModel(),
    )

    response = await run_agent("分析股票 600519 的 PE 和 PB", graph=graph)

    assert response.status is AgentStatus.COMPLETED
    assert fund.calls == [
        (
            "stock_valuation",
            {"stock": "600519", "years": 10, "max_points": 600},
        )
    ]
    assert response.associations
    assert response.associations[0].relationship is Relationship.CONTRAST
    audit_by_label = {
        fact.label: fact.audit_ref
        for fact in response.facts
    }
    assert audit_by_label["PE TTM 当前值"] == "pe-audit"
    assert audit_by_label["PB 当前值"] == "pb-audit"
    assert audit_by_label["前复权价格"] == "price-audit"
    assert "22.1" in response.answer
    assert "PE 与 PB" in response.answer
    assert {
        "status": response.status.value,
        "fact_labels": [fact.label for fact in response.facts],
        "association_count": len(response.associations),
        "warnings": response.warnings,
        "errors": response.errors,
        "sections": [
            heading
            for heading in ("## 事实", "## 关联说明", "## 限制", "## 条件式参考")
            if heading in response.answer
        ],
    } == {
        "status": "completed",
        "fact_labels": [
            "股票名称",
            "PE TTM 当前值",
            "PE TTM 历史分位",
            "PB 当前值",
            "PB 历史分位",
            "前复权价格",
            "监管政策背景",
            "监管政策背景",
        ],
        "association_count": 1,
        "warnings": [],
        "errors": [],
        "sections": ["## 事实", "## 关联说明", "## 限制", "## 条件式参考"],
    }


@pytest.mark.asyncio
async def test_asset_analysis_searches_articles_and_creator_posts() -> None:
    class CategorizedWebClient(FakeWebClient):
        async def call(
            self,
            tool: str,
            arguments: dict[str, Any],
        ) -> WebToolEnvelope:
            self.calls.append((tool, arguments))
            query = str(arguments["query"])
            if "site:xueqiu.com" in query:
                envelope = _web_envelope(
                    title="公开博主观点",
                    url="https://xueqiu.com/123456/789",
                    source_type=WebSourceType.CREATOR,
                    domain="xueqiu.com",
                )
            else:
                envelope = _web_envelope(
                    title="机构深度报告",
                    url="https://research.example.com/report",
                    source_type=WebSourceType.RESEARCH,
                    domain="research.example.com",
                )
            assert isinstance(envelope.data, WebSearchData)
            envelope.data.query = query
            return envelope

    web = CategorizedWebClient()
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=web,
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("分析股票 600519", graph=graph)

    assert response.status is AgentStatus.COMPLETED
    assert web.calls == [
        (
            "web_search",
            {
                "query": '"600519" 股票 深度分析 研究报告 财经媒体',
                "max_results": 5,
                "source_types": ["official", "research", "media"],
            },
        ),
        (
            "web_search",
            {
                "query": (
                    '"600519" 股票 观点 分享 '
                    "site:xueqiu.com OR site:zhihu.com"
                ),
                "max_results": 5,
                "source_types": ["creator"],
            },
        ),
    ]
    assert "机构深度报告：<https://research.example.com/report>" in response.answer
    assert "公开博主观点：<https://xueqiu.com/123456/789>" in response.answer
    assert "[机构研究]" in response.answer
    assert "[博主/社区]" in response.answer
    assert "不作为市场事实" in response.answer


@pytest.mark.asyncio
async def test_optional_asset_web_failure_keeps_market_analysis() -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=FakeWebClient(_web_error_envelope()),
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("分析股票 600519", graph=graph)

    assert response.status is AgentStatus.PARTIAL_RESULT
    assert "22.1" in response.answer
    assert any("可选背景工具 web_search" in item for item in response.warnings)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ENTITY_AMBIGUOUS", AgentStatus.NEED_CLARIFICATION),
        ("STOCK_NOT_FOUND", AgentStatus.NOT_FOUND),
        ("STOCK_MARKET_UNSUPPORTED", AgentStatus.UNSUPPORTED),
        ("STALE_OR_INVALID_DATA", AgentStatus.STALE_DATA),
        ("DATA_SOURCE_ERROR", AgentStatus.CANNOT_CONFIRM),
    ],
)
async def test_error_semantics_route_to_distinct_terminal_states(
    code: str,
    expected: AgentStatus,
) -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_error_envelope(code)),
        web_client=FakeWebClient(),
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("分析股票 600519 的 PE", graph=graph)

    assert response.status is expected
    assert response.associations == []


@pytest.mark.asyncio
async def test_web_numbers_are_not_rendered_as_market_facts() -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=FakeWebClient(),
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("搜索网页基金监管政策", graph=graph)

    assert response.status is AgentStatus.COMPLETED
    assert all(fact.source_kind == "background" for fact in response.facts)
    assert "123" not in response.answer
    assert "不作为市场事实" in response.answer


@pytest.mark.asyncio
async def test_missing_pb_is_not_replaced_by_pe() -> None:
    envelope = _stock_envelope()
    envelope.data["summary"]["pb"] = {
        "current": None,
        "percentile": None,
        "level": None,
    }
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(envelope),
        web_client=FakeWebClient(),
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("分析股票 600519 的估值", graph=graph)

    assert not any(fact.label.startswith("PB") for fact in response.facts)
    assert any(fact.label.startswith("PE") for fact in response.facts)


@pytest.mark.asyncio
async def test_model_failure_falls_back_to_deterministic_fact_report() -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=FakeWebClient(),
        association_model=FailingAssociationModel(),
    )

    response = await run_agent("分析股票 600519 的估值", graph=graph)

    assert response.status is AgentStatus.PARTIAL_RESULT
    assert response.associations == []
    assert "22.1" in response.answer
    assert any("回退为事实报告" in item for item in response.warnings)


@pytest.mark.asyncio
async def test_compare_without_two_codes_asks_for_clarification() -> None:
    fund = FakeFundClient(_stock_envelope())
    graph = build_agent_graph(
        config=_config(),
        fund_client=fund,
        web_client=FakeWebClient(),
        association_model=RuleBasedAssociationModel(),
    )

    response = await run_agent("比较基金 000001", graph=graph)

    assert response.status is AgentStatus.NEED_CLARIFICATION
    assert fund.calls == []


def test_schema_rejects_unknown_tool_and_causal_claim() -> None:
    with pytest.raises(ValidationError):
        ToolCallSpec(
            tool="unknown_tool",
            source="fund",
            arguments={},
        )
    with pytest.raises(ValidationError):
        AssociationDraft(
            evidence_refs=["a", "b"],
            relationship=Relationship.CO_OCCURRENCE,
            explanation="错误因果",
            causal_claim=True,
            confidence=Confidence.HIGH,
        )


def test_ark_model_config_accepts_thinking_and_long_timeout() -> None:
    config = ModelConfig(
        enabled=True,
        provider="ark",
        base_url="https://ark.example/api/v3",
        api_key="test-key",
        model="ep-test",
        temperature=0,
        timeout_seconds=1800,
        extra_body={"thinking": {"type": "enabled"}},
    )

    assert config.resolved_base_url == "https://ark.example/api/v3"
    assert config.timeout_seconds == 1800
    assert config.extra_body == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_association_model_forwards_extra_body() -> None:
    captured: dict[str, Any] = {}

    class FakeCompletions:
        async def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=SimpleNamespace(associations=[])
                        )
                    )
                ]
            )

    model = OpenAIAssociationModel.__new__(OpenAIAssociationModel)
    model._config = ModelConfig(
        enabled=True,
        base_url="https://ark.example/api/v3",
        api_key="test-key",
        model="ep-test",
        extra_body={"thinking": {"type": "enabled"}},
    )
    model._client = SimpleNamespace(
        beta=SimpleNamespace(
            chat=SimpleNamespace(completions=FakeCompletions())
        )
    )

    result = await model.build_associations([], "测试结构化输出")

    assert result == []
    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (AgentState, {"question": "分析 600519"}),
        (
            ToolCallSpec,
            {
                "tool": RegisteredTool.STOCK_VALUATION,
                "source": "fund",
                "arguments": {},
            },
        ),
        (
            FactRef,
            {
                "fact_id": "fact_a",
                "tool": RegisteredTool.STOCK_VALUATION,
                "field_path": "data.summary.pe_ttm.current",
                "label": "PE TTM 当前值",
                "value": 1,
            },
        ),
        (
            AssociationDraft,
            {
                "evidence_refs": ["fact_a", "fact_b"],
                "relationship": Relationship.CONTRAST,
                "explanation": "两个口径应分别观察。",
                "confidence": Confidence.HIGH,
            },
        ),
    ],
)
def test_core_agent_schemas_forbid_extra_fields(model, payload) -> None:
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "unexpected": True})


def test_response_validator_removes_numbers_and_causal_language() -> None:
    facts = []
    associations = [
        AssociationDraft(
            evidence_refs=["a", "b"],
            relationship=Relationship.CO_OCCURRENCE,
            explanation="数值 123 同时出现",
            confidence=Confidence.LOW,
        )
    ]

    valid, warnings = validate_associations(associations, facts)

    assert valid == []
    assert warnings


def test_response_validator_blocks_causality_trading_and_nav_valuation() -> None:
    facts = [
        FactRef(
            fact_id="fact_a",
            tool=RegisteredTool.FUND_ANALYZE,
            field_path="data.analysis.performance.max_drawdown_pct",
            label="最大回撤",
            value=-10,
            unit="%",
            audit_ref="audit-a",
        ),
        FactRef(
            fact_id="fact_b",
            tool=RegisteredTool.FUND_ANALYZE,
            field_path="data.analysis.performance.history_position_percentile",
            label="历史位置分位",
            value=20,
            unit="%",
            audit_ref="audit-b",
        ),
    ]
    associations = [
        AssociationDraft(
            evidence_refs=["fact_a", "fact_b"],
            relationship=Relationship.CO_OCCURRENCE,
            explanation="因为回撤较大所以后续必然下跌。",
            confidence=Confidence.LOW,
        ),
        AssociationDraft(
            evidence_refs=["fact_a", "fact_b"],
            relationship=Relationship.CONSISTENCY,
            explanation="当前必须买入。",
            confidence=Confidence.LOW,
        ),
        AssociationDraft(
            evidence_refs=["fact_a", "fact_b"],
            relationship=Relationship.CONTRAST,
            explanation="净值处于低位，说明产品低估。",
            confidence=Confidence.LOW,
        ),
    ]

    valid, warnings = validate_associations(associations, facts)

    assert valid == []
    assert len(warnings) == 3


def test_market_envelope_without_audit_is_blocked() -> None:
    envelope = _stock_envelope().model_dump(mode="json")
    envelope["data_audit"] = []
    status, facts, _, _, errors = validate_tool_results(
        [
            ToolExecution(
                tool=RegisteredTool.STOCK_VALUATION,
                source="fund",
                arguments={"stock": "600519"},
                envelope=envelope,
            )
        ],
        maximum_facts=20,
    )

    assert status is AgentStatus.FAILED
    assert facts == []
    assert errors[0].code == "MISSING_DATA_AUDIT"


def test_intent_policy_rejects_prediction_request() -> None:
    intent, _ = classify_question("预测涨跌并自动下单")
    assert intent is Intent.UNSUPPORTED
    stock_intent, _ = classify_question("贵州茅台PE")
    assert stock_intent is Intent.STOCK_VALUATION


@pytest.mark.asyncio
async def test_low_confidence_rule_path_can_use_structured_intent_model() -> None:
    nodes = AgentNodes(
        FakeFundClient(_stock_envelope()),
        FakeWebClient(),
        RuleBasedAssociationModel(),
        FakeIntentClassifier(),
        _config(),
    )

    update = await nodes.classify(AgentState(question="帮我看看这个"))

    assert update["intent"] is Intent.FUND_ANALYSIS
    assert update["entities"] == ["000001"]


@pytest.mark.asyncio
async def test_each_node_returns_only_declared_state_fields() -> None:
    nodes = AgentNodes(
        FakeFundClient(_stock_envelope()),
        FakeWebClient(),
        RuleBasedAssociationModel(),
        None,
        _config(),
    )
    state = AgentState(question="分析股票 600519 的 PE 和 PB")

    for node in (
        nodes.classify,
        nodes.plan_registered_tools,
        nodes.call_mcp,
        nodes.validate_tool_envelopes,
        nodes.build_associations,
        nodes.validate_response,
        nodes.render_answer,
    ):
        update = await node(state)
        assert set(update).issubset(AgentState.model_fields)
        state = AgentState.model_validate(
            {**state.model_dump(mode="python"), **update}
        )

    assert state.status is AgentStatus.COMPLETED
    assert state.final_answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("association_model", "expected_status", "warning_fragment"),
    [
        (
            InvalidAssociationModel(),
            AgentStatus.PARTIAL_RESULT,
            "回退为事实报告",
        ),
        (EmptyAssociationModel(), AgentStatus.COMPLETED, None),
    ],
)
async def test_invalid_or_empty_model_output_falls_back_to_facts(
    association_model,
    expected_status: AgentStatus,
    warning_fragment: str | None,
) -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=FakeWebClient(),
        association_model=association_model,
    )

    response = await run_agent("分析股票 600519 的估值", graph=graph)

    assert response.status is expected_status
    assert response.associations == []
    assert response.facts
    if warning_fragment is not None:
        assert any(warning_fragment in item for item in response.warnings)


def test_graph_is_compiled_without_checkpoint() -> None:
    graph = build_agent_graph(
        config=_config(),
        fund_client=FakeFundClient(_stock_envelope()),
        web_client=FakeWebClient(),
        association_model=RuleBasedAssociationModel(),
    )

    assert graph.checkpointer is None
    assert {
        "CLASSIFY",
        "PLAN_REGISTERED_TOOLS",
        "CALL_MCP",
        "VALIDATE_TOOL_ENVELOPES",
        "BUILD_ASSOCIATIONS",
        "VALIDATE_RESPONSE",
        "RENDER_ANSWER",
    }.issubset(graph.get_graph().nodes)
    assert RegisteredTool.STOCK_VALUATION.value == "stock_valuation"

    rank = {
        "__start__": 0,
        "CLASSIFY": 1,
        "PLAN_REGISTERED_TOOLS": 2,
        "CALL_MCP": 3,
        "VALIDATE_TOOL_ENVELOPES": 4,
        "BUILD_ASSOCIATIONS": 5,
        "VALIDATE_RESPONSE": 6,
        "RENDER_ANSWER": 7,
        "__end__": 8,
    }
    for edge in graph.get_graph().edges:
        assert rank[edge.source] < rank[edge.target]
