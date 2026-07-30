"""Controlled LangGraph implementation of the financial research workflow."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, Callable
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from financial_agent.config import AppConfig, get_config
from financial_agent.domain import (
    AgentFailure,
    Clarification,
    EntityCandidate,
    Intent,
    TaskStatus,
)
from financial_agent.evidence import (
    EvidenceGate,
    EvidenceRecord,
    GateDecision,
    ResearchReport,
    ResponseValidationError,
    ResponseValidator,
    build_claims,
    document_hit_to_evidence,
    render_report,
    tool_envelope_to_evidence,
)
from financial_agent.evidence.models import EvidenceSubject
from financial_agent.mcp_client import FundToolClient, build_fund_tool_client
from financial_agent.mcp_server.schemas import ToolEnvelope
from financial_agent.models import ReportNarrator, get_llm_client
from financial_agent.policies import SuitabilityDecision, check_suitability
from financial_agent.prompts import PROMPT_VERSIONS
from financial_agent.web_research import (
    WebFetchData,
    WebResearchClient,
    WebSearchData,
    WebToolEnvelope,
    build_web_research_client,
)

from .intent import IntentClassifier, contextualize_query, detect_policy_violation
from .planner import build_tool_plan
from .state import AgentState

logger = logging.getLogger("financial_agent.orchestration")
SHANGHAI = ZoneInfo("Asia/Shanghai")

# 需要外部网页/文档背景的意图；其余意图只用市场工具事实。
_EXTERNAL_CONTEXT_INTENTS = {Intent.WEB_RESEARCH, Intent.DOCUMENT_QA}
_URL_RE = re.compile(r"https?://\S+")


class FinancialAgentGraph:
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        tool_client: FundToolClient | None = None,
        classifier: IntentClassifier | None = None,
        web_client: WebResearchClient | None = None,
        gate: EvidenceGate | None = None,
        response_validator: ResponseValidator | None = None,
        user_context_loader: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or get_config()
        self.tool_client = tool_client or build_fund_tool_client(self.config)
        llm = (
            get_llm_client()
            if (self.config.agent.use_llm_for_intent or self.config.agent.use_llm_for_report)
            else None
        )
        self.classifier = classifier or IntentClassifier(self.config, llm)
        self.narrator = (
            ReportNarrator(self.config, llm)
            if self.config.agent.use_llm_for_report and llm is not None
            else None
        )
        self.web_client = web_client or (
            build_web_research_client(self.config)
            if self.config.web_research.enabled
            else None
        )
        self.gate = gate or EvidenceGate()
        self.response_validator = response_validator or ResponseValidator()
        self.user_context_loader = user_context_loader
        self.compiled = self._build()

    def _build(self) -> Any:
        builder = StateGraph(AgentState)
        builder.add_node("classify_intent", self._classify_intent)
        builder.add_node("need_clarification", self._need_clarification)
        builder.add_node("load_user_context", self._load_user_context)
        builder.add_node("plan_tools", self._plan_tools)
        builder.add_node("collect_tool_facts", self._collect_tool_facts)
        builder.add_node("gather_external_context", self._gather_external_context)
        builder.add_node("build_evidence", self._build_evidence)
        builder.add_node("validate_evidence", self._validate_evidence)
        builder.add_node("check_suitability", self._check_suitability)
        builder.add_node("build_claims", self._build_claims)
        builder.add_node("compose_report", self._compose_report)
        builder.add_node("validate_response", self._validate_response)

        builder.add_edge(START, "classify_intent")
        builder.add_conditional_edges(
            "classify_intent",
            self._route_after_classification,
            {
                "clarify": "need_clarification",
                "policy": "build_evidence",
                "continue": "load_user_context",
            },
        )
        builder.add_edge("need_clarification", END)
        builder.add_edge("load_user_context", "plan_tools")
        builder.add_edge("plan_tools", "collect_tool_facts")
        builder.add_conditional_edges(
            "collect_tool_facts",
            self._route_after_tools,
            {
                "clarify": "need_clarification",
                "continue": "gather_external_context",
            },
        )
        builder.add_edge("gather_external_context", "build_evidence")
        builder.add_edge("build_evidence", "validate_evidence")
        builder.add_edge("validate_evidence", "check_suitability")
        builder.add_edge("check_suitability", "build_claims")
        builder.add_edge("build_claims", "compose_report")
        builder.add_edge("compose_report", "validate_response")
        builder.add_edge("validate_response", END)
        return builder.compile(checkpointer=InMemorySaver())

    @staticmethod
    def initial_state(
        query: str,
        *,
        conversation_id: UUID | None = None,
        task_id: UUID | None = None,
        trace_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> AgentState:
        return {
            "schema_version": "1.0",
            "task_id": str(task_id or uuid4()),
            "conversation_id": str(conversation_id or uuid4()),
            "trace_id": trace_id or str(uuid4()),
            "user_query": query,
            "resolved_query": query,
            "conversation_history": conversation_history or [],
            "status": TaskStatus.RECEIVED.value,
            "prompt_versions": dict(PROMPT_VERSIONS),
            "warnings": [],
            "errors": [],
            "tool_results": [],
            "external_context": [],
            "evidence": [],
            "claims": [],
        }

    async def ainvoke(self, state: AgentState) -> AgentState:
        config = {"configurable": {"thread_id": state["task_id"]}}
        return await self.compiled.ainvoke(state, config=config)

    async def _classify_intent(self, state: AgentState) -> dict[str, Any]:
        resolved_query = contextualize_query(
            state["user_query"],
            state.get("conversation_history", []),
        )
        decision = await self.classifier.classify(resolved_query)
        return {
            "resolved_query": resolved_query,
            "intent": decision.intent.value,
            "intent_confidence": decision.confidence,
            "entities": [item.model_dump(mode="json") for item in decision.entities],
            "policy_violation": detect_policy_violation(state["user_query"]),
            "clarification": (
                Clarification(
                    reason="意图或实体信息不足",
                    question=decision.clarification_question or "请补充具体基金或指数。",
                ).model_dump(mode="json")
                if decision.needs_clarification
                else None
            ),
            "status": TaskStatus.RUNNING.value,
        }

    @staticmethod
    def _route_after_classification(state: AgentState) -> str:
        if state.get("clarification"):
            return "clarify"
        if state.get("policy_violation"):
            return "policy"
        return "continue"

    @staticmethod
    async def _need_clarification(state: AgentState) -> dict[str, Any]:
        return {"status": TaskStatus.NEED_CLARIFICATION.value}

    async def _load_user_context(self, state: AgentState) -> dict[str, Any]:
        if self.user_context_loader is None:
            return {"user_context": {}}
        context = await asyncio.to_thread(self.user_context_loader)
        return {"user_context": context}

    @staticmethod
    async def _plan_tools(state: AgentState) -> dict[str, Any]:
        intent = Intent(state["intent"])
        entities = [EntityCandidate.model_validate(item) for item in state.get("entities", [])]
        try:
            plan = build_tool_plan(intent, entities)
        except ValueError as exc:
            return {
                "tool_plan": [],
                "clarification": Clarification(
                    reason="工具规划缺少唯一实体",
                    question=str(exc),
                ).model_dump(mode="json"),
            }
        return {"tool_plan": [item.model_dump(mode="json") for item in plan]}

    async def _collect_tool_facts(self, state: AgentState) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors = list(state.get("errors", []))
        clarification = state.get("clarification")
        follow_up_indexes: list[str] = []
        for item in state.get("tool_plan", []):
            envelope = await self.tool_client.call(item["tool"], item["arguments"])
            results.append(envelope.model_dump(mode="json"))
            if (
                item["tool"] == "fund_analyze"
                and envelope.ok
                and envelope.data is not None
            ):
                valuation = envelope.data.get("index_valuation") or {}
                if valuation.get("available") and valuation.get("index_name"):
                    follow_up_indexes.append(str(valuation["index_name"]))
            if envelope.ok or envelope.error is None:
                continue
            if envelope.error.code in {"AMBIGUOUS_FUND", "ENTITY_AMBIGUOUS"}:
                clarification = Clarification(
                    reason=envelope.error.code,
                    question=envelope.error.message,
                    candidates=envelope.error.details.get("candidates", []),
                ).model_dump(mode="json")
            else:
                errors.append(
                    AgentFailure(
                        category="upstream",
                        code=envelope.error.code,
                        message=envelope.error.message,
                        retryable=envelope.error.retryable,
                        source=item["tool"],
                        details=envelope.error.details,
                    ).model_dump(mode="json")
                )

        for index_name in dict.fromkeys(follow_up_indexes):
            envelope = await self.tool_client.call(
                "index_valuation",
                {
                    "index": index_name,
                    "years": 10,
                    "max_points": 600,
                },
            )
            results.append(envelope.model_dump(mode="json"))
            if not envelope.ok and envelope.error is not None:
                errors.append(
                    AgentFailure(
                        category="upstream",
                        code=envelope.error.code,
                        message=envelope.error.message,
                        retryable=envelope.error.retryable,
                        source="index_valuation",
                        details=envelope.error.details,
                    ).model_dump(mode="json")
                )
        return {
            "tool_results": results,
            "errors": errors,
            "clarification": clarification,
        }

    @staticmethod
    def _route_after_tools(state: AgentState) -> str:
        return "clarify" if state.get("clarification") else "continue"

    async def _gather_external_context(self, state: AgentState) -> dict[str, Any]:
        """仅对网页研究/读文档意图调用 web-research MCP 获取非数值背景。

        其余意图直接跳过——市场事实全部来自 fund-advisor 工具。网页/文档命中
        统一标记为低置信度、numeric_allowed=false，不能覆盖市场数值。
        """
        intent = Intent(state["intent"])
        if intent not in _EXTERNAL_CONTEXT_INTENTS or self.web_client is None:
            return {"external_context": []}

        question = state.get("resolved_query") or state["user_query"]
        warnings = list(state.get("warnings", []))
        errors = list(state.get("errors", []))
        hits: list[dict[str, Any]] = []
        try:
            if intent == Intent.DOCUMENT_QA:
                hits = await self._read_document_context(question)
            else:
                hits = await self._search_web_context(question)
        except Exception as exc:  # noqa: BLE001 - 外部通道失败不阻断主流程
            logger.warning("external context gathering failed: %s", exc)
            errors.append(
                AgentFailure(
                    category="retrieval",
                    code="EXTERNAL_CONTEXT_FAILED",
                    message="外部网页或文档检索失败，仅保留已确认事实",
                    retryable=True,
                    source="web_research",
                    details={"reason": str(exc)},
                ).model_dump(mode="json")
            )
            warnings.append("外部网页或文档检索失败，本次未附带外部背景。")
        if not hits:
            warnings.append("未获得可引用的外部网页或文档背景。")
        return {
            "external_context": hits,
            "warnings": list(dict.fromkeys(warnings)),
            "errors": errors,
        }

    async def _read_document_context(self, question: str) -> list[dict[str, Any]]:
        match = _URL_RE.search(question)
        if not match:
            return []
        envelope = await self.web_client.call(
            "document_read",
            {"url": match.group(0), "max_chars": self.config.web_research.max_content_chars},
        )
        if not envelope.ok or not isinstance(envelope.data, WebFetchData):
            detail = envelope.error.message if envelope.error else "未返回文档正文"
            raise RuntimeError(f"读取指定文档失败：{detail}")
        data = envelope.data
        return [
            {
                "channel": "direct_document",
                "title": data.title,
                "url": data.final_url,
                "text": data.content,
                "page": None,
                "version": None,
                "audit_hashes": _web_audit_hashes(envelope),
            }
        ]

    async def _search_web_context(self, question: str) -> list[dict[str, Any]]:
        search = await self.web_client.call(
            "web_search",
            {"query": question, "max_results": 5},
        )
        if not search.ok or not isinstance(search.data, WebSearchData):
            detail = search.error.message if search.error else "未返回搜索结果"
            raise RuntimeError(f"网页搜索失败：{detail}")
        hits: list[dict[str, Any]] = []
        for result in search.data.results[:5]:
            text = result.snippet
            title = result.title
            final_url = result.url
            try:
                fetched = await self.web_client.call(
                    "web_fetch",
                    {"url": result.url, "max_chars": self.config.web_research.max_content_chars},
                )
                if fetched.ok and isinstance(fetched.data, WebFetchData):
                    text = fetched.data.content or text
                    title = fetched.data.title or title
                    final_url = fetched.data.final_url
            except Exception as exc:  # noqa: BLE001 - 单条抓取失败保留摘要
                logger.debug("web_fetch failed for %s: %s", result.url, exc)
            if not text:
                continue
            hits.append(
                {
                    "channel": "web",
                    "title": title,
                    "url": final_url,
                    "text": text,
                    "page": None,
                    "version": None,
                    "audit_hashes": _web_audit_hashes(search),
                }
            )
        return hits

    async def _build_evidence(self, state: AgentState) -> dict[str, Any]:
        task_id = UUID(state["task_id"])
        records: list[EvidenceRecord] = []
        warnings = list(state.get("warnings", []))
        for raw in state.get("tool_results", []):
            envelope = ToolEnvelope.model_validate(raw)
            records.extend(tool_envelope_to_evidence(envelope, task_id))
            warnings.extend(_warning_messages(envelope))

        subject = _subject_for_documents(state)
        for index, raw in enumerate(state.get("external_context", [])):
            text = str(raw.get("text") or "")
            if not text:
                continue
            records.append(
                document_hit_to_evidence(
                    task_id=task_id,
                    subject=subject,
                    text=text,
                    source_ref=f"{raw.get('channel', 'web')}:{index}",
                    title=str(raw.get("title") or raw.get("url") or "外部背景"),
                    url=str(raw.get("url") or ""),
                    page=raw.get("page"),
                    version=raw.get("version"),
                    channel=str(raw.get("channel") or "web"),
                )
            )
        return {
            "evidence": [item.model_dump(mode="json") for item in records],
            "warnings": list(dict.fromkeys(warnings)),
        }

    async def _validate_evidence(self, state: AgentState) -> dict[str, Any]:
        records = [EvidenceRecord.model_validate(item) for item in state.get("evidence", [])]
        decision = self.gate.evaluate(
            Intent(state["intent"]),
            records,
            state.get("warnings", []),
            policy_violation=state.get("policy_violation"),
        )
        return {"gate_decision": decision.model_dump(mode="json")}

    @staticmethod
    async def _check_suitability(state: AgentState) -> dict[str, Any]:
        decision = check_suitability(
            Intent(state["intent"]),
            state.get("user_context", {}),
            datetime.now(SHANGHAI),
        )
        return {
            "suitability": decision.model_dump(mode="json"),
            "warnings": list(dict.fromkeys([*state.get("warnings", []), *decision.warnings])),
        }

    async def _build_claims(self, state: AgentState) -> dict[str, Any]:
        decision = GateDecision.model_validate(state["gate_decision"])
        evidence = [EvidenceRecord.model_validate(item) for item in state.get("evidence", [])]
        claims = build_claims(
            UUID(state["task_id"]),
            evidence,
            decision,
            maximum=self.config.agent.maximum_report_facts,
        )
        return {"claims": [item.model_dump(mode="json") for item in claims]}

    async def _compose_report(self, state: AgentState) -> dict[str, Any]:
        from financial_agent.evidence.models import ClaimRecord

        report = render_report(
            task_id=UUID(state["task_id"]),
            intent=Intent(state["intent"]),
            evidence=[EvidenceRecord.model_validate(item) for item in state.get("evidence", [])],
            claims=[ClaimRecord.model_validate(item) for item in state.get("claims", [])],
            decision=GateDecision.model_validate(state["gate_decision"]),
            generated_at=datetime.now(SHANGHAI),
            extra_warnings=state.get("warnings", []),
        )
        suitability = SuitabilityDecision.model_validate(state.get("suitability", {}))
        report.missing_information = list(
            dict.fromkeys(
                [
                    *report.missing_information,
                    *suitability.missing_information,
                ]
            )
        )
        if self.narrator is not None and report.evidence_grade in {"A", "B", "C"}:
            deterministic_analysis = list(report.analysis)
            try:
                enriched = await self.narrator.enrich(report)
                self.response_validator.validate(
                    enriched,
                    [EvidenceRecord.model_validate(item) for item in state.get("evidence", [])],
                )
                report = enriched
            except Exception as exc:
                logger.warning("LLM report narration rejected: %s", exc)
                report.analysis = deterministic_analysis
                report.warnings = list(
                    dict.fromkeys(
                        [
                            *report.warnings,
                            "模型叙述不可用，已回退确定性模板。",
                        ]
                    )
                )
        return {"final_report": report.model_dump(mode="json")}

    async def _validate_response(self, state: AgentState) -> dict[str, Any]:
        report = ResearchReport.model_validate(state["final_report"])
        evidence = [EvidenceRecord.model_validate(item) for item in state.get("evidence", [])]
        try:
            self.response_validator.validate(report, evidence)
        except ResponseValidationError as exc:
            return {
                "status": TaskStatus.FAILED.value,
                "final_report": {},
                "errors": [
                    *state.get("errors", []),
                    AgentFailure(
                        category="validation",
                        code="RESPONSE_VALIDATION_FAILED",
                        message=str(exc),
                        source="response_validator",
                    ).model_dump(mode="json"),
                ],
            }
        return {"status": report.status}


def _web_audit_hashes(envelope: WebToolEnvelope) -> list[str]:
    return [
        str(item.response_sha256)
        for item in envelope.data_audit
        if item.validation == "passed" and item.response_sha256
    ]


def _warning_messages(envelope: ToolEnvelope) -> list[str]:
    messages: list[str] = []
    for item in envelope.data_warnings:
        if isinstance(item, str):
            messages.append(item)
        elif item.get("message"):
            messages.append(str(item["message"]))
    return messages


def _subject_for_documents(state: AgentState) -> EvidenceSubject:
    entities = state.get("entities", [])
    if entities:
        first = entities[0]
        return EvidenceSubject(
            type=str(first.get("entity_type", "query")),
            id=str(first.get("code") or first.get("query") or "unknown"),
            name=first.get("name"),
        )
    return EvidenceSubject(type="query", id=state["task_id"])
