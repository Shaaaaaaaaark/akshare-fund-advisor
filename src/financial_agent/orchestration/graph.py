"""Controlled LangGraph implementation of the financial research workflow."""

from __future__ import annotations

import asyncio
import logging
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
from financial_agent.rag import (
    DocumentHit,
    RAGService,
    RetrievalAssessment,
    RetrievalPlan,
)

from .intent import IntentClassifier, contextualize_query, detect_policy_violation
from .planner import build_tool_plan
from .state import AgentState

logger = logging.getLogger("financial_agent.orchestration")
SHANGHAI = ZoneInfo("Asia/Shanghai")


class FinancialAgentGraph:
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        tool_client: FundToolClient | None = None,
        classifier: IntentClassifier | None = None,
        rag: RAGService | None = None,
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
        self.rag = rag or RAGService(self.config)
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
        builder.add_node("plan_retrieval", self._plan_retrieval)
        builder.add_node("retrieve_documents", self._retrieve_documents)
        builder.add_node("assess_retrieval", self._assess_retrieval)
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
                "continue": "plan_retrieval",
            },
        )
        builder.add_conditional_edges(
            "plan_retrieval",
            self._route_after_retrieval_plan,
            {
                "retrieve": "retrieve_documents",
                "complete": "build_evidence",
            },
        )
        builder.add_edge("retrieve_documents", "assess_retrieval")
        builder.add_conditional_edges(
            "assess_retrieval",
            self._route_after_retrieval_assessment,
            {
                "retry": "plan_retrieval",
                "complete": "build_evidence",
            },
        )
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
            "retrieval_round": 0,
            "retrieval_plan": {},
            "retrieval_assessment": {},
            "retrieval_trace": [],
            "retrieval_results": [],
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

    async def _plan_retrieval(self, state: AgentState) -> dict[str, Any]:
        round_number = state.get("retrieval_round", 0) + 1
        previous_assessment = (
            RetrievalAssessment.model_validate(state["retrieval_assessment"])
            if state.get("retrieval_assessment")
            else None
        )
        previous_queries = [
            str(query.get("query"))
            for entry in state.get("retrieval_trace", [])
            for query in (entry.get("plan") or {}).get("queries", [])
            if query.get("query")
        ]
        try:
            plan = await self.rag.plan(
                question=state.get("resolved_query") or state["user_query"],
                intent=state["intent"],
                entity_queries=[
                    item["query"] for item in state.get("entities", [])
                ],
                round_number=round_number,
                previous_queries=previous_queries,
                previous_hits=[
                    DocumentHit.model_validate(item)
                    for item in state.get("retrieval_results", [])
                ],
                previous_assessment=previous_assessment,
            )
        except Exception as exc:
            logger.warning("RAG planning failed: %s", exc)
            plan = RetrievalPlan(
                round_number=round_number,
                reason="检索规划失败，本次跳过文档检索",
            )
        trace = [
            *state.get("retrieval_trace", []),
            {
                "round_number": round_number,
                "plan": plan.model_dump(mode="json"),
            },
        ]
        return {
            "retrieval_round": round_number,
            "retrieval_plan": plan.model_dump(mode="json"),
            "retrieval_trace": trace,
        }

    @staticmethod
    def _route_after_retrieval_plan(state: AgentState) -> str:
        return "retrieve" if (state.get("retrieval_plan") or {}).get("queries") else "complete"

    async def _retrieve_documents(self, state: AgentState) -> dict[str, Any]:
        plan = RetrievalPlan.model_validate(state["retrieval_plan"])
        round_hits, query_errors = await self.rag.execute(plan)
        existing = [
            DocumentHit.model_validate(item)
            for item in state.get("retrieval_results", [])
        ]
        hits = _merge_document_hits(
            existing,
            round_hits,
            self.config.rag.max_chunks,
        )
        trace = list(state.get("retrieval_trace", []))
        if trace:
            trace[-1] = {
                **trace[-1],
                "execution": {
                    "new_hits": len(round_hits),
                    "total_hits": len(hits),
                    "errors": query_errors,
                },
            }
        errors = list(state.get("errors", []))
        warnings = list(state.get("warnings", []))
        if query_errors:
            errors = [
                *errors,
                AgentFailure(
                    category="retrieval",
                    code="RETRIEVAL_QUERY_FAILED",
                    message="部分文档检索查询失败，已保留成功结果",
                    retryable=True,
                    source="rag",
                    details={"errors": query_errors},
                ).model_dump(mode="json"),
            ]
            warnings.append("部分文档检索查询失败，本次仅使用成功返回的片段。")
        return {
            "retrieval_results": [
                item.model_dump(mode="json") for item in hits
            ],
            "retrieval_trace": trace,
            "errors": errors,
            "warnings": list(dict.fromkeys(warnings)),
        }

    async def _assess_retrieval(self, state: AgentState) -> dict[str, Any]:
        plan = RetrievalPlan.model_validate(state["retrieval_plan"])
        assessment = await self.rag.assess(
            question=state.get("resolved_query") or state["user_query"],
            plan=plan,
            hits=[
                DocumentHit.model_validate(item)
                for item in state.get("retrieval_results", [])
            ],
        )
        if (
            not assessment.sufficient
            and plan.round_number >= self.config.rag.max_rounds
        ):
            assessment = assessment.model_copy(
                update={
                    "retryable": False,
                    "reason": (
                        f"{assessment.reason}；已达到最大检索轮次 "
                        f"{self.config.rag.max_rounds}"
                    ),
                }
            )
        trace = list(state.get("retrieval_trace", []))
        if trace:
            trace[-1] = {
                **trace[-1],
                "assessment": assessment.model_dump(mode="json"),
            }
        warnings = list(state.get("warnings", []))
        if (
            not assessment.sufficient
            and not assessment.retryable
            and plan.queries
        ):
            warnings.append(
                "文档检索达到轮次上限或没有新的安全查询，结果可能不完整。"
            )
        return {
            "retrieval_assessment": assessment.model_dump(mode="json"),
            "retrieval_trace": trace,
            "warnings": list(dict.fromkeys(warnings)),
        }

    def _route_after_retrieval_assessment(self, state: AgentState) -> str:
        assessment = RetrievalAssessment.model_validate(
            state["retrieval_assessment"]
        )
        return (
            "retry"
            if (
                not assessment.sufficient
                and assessment.retryable
                and state.get("retrieval_round", 0) < self.config.rag.max_rounds
            )
            else "complete"
        )

    async def _build_evidence(self, state: AgentState) -> dict[str, Any]:
        task_id = UUID(state["task_id"])
        records: list[EvidenceRecord] = []
        warnings = list(state.get("warnings", []))
        for raw in state.get("tool_results", []):
            envelope = ToolEnvelope.model_validate(raw)
            records.extend(tool_envelope_to_evidence(envelope, task_id))
            warnings.extend(_warning_messages(envelope))

        subject = _subject_for_documents(state)
        for raw in state.get("retrieval_results", []):
            hit = DocumentHit.model_validate(raw)
            records.append(
                document_hit_to_evidence(
                    task_id=task_id,
                    subject=subject,
                    text=hit.text,
                    source_ref=str(hit.hit_id),
                    title=hit.title,
                    url=hit.url,
                    page=hit.page,
                    version=hit.version,
                    channel=hit.channel.value,
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


def _merge_document_hits(
    existing: list[DocumentHit],
    incoming: list[DocumentHit],
    limit: int,
) -> list[DocumentHit]:
    merged: list[DocumentHit] = []
    seen: set[str] = set()
    for hit in [*existing, *incoming]:
        key = str(
            hit.metadata.get("chunk_id")
            or f"{hit.channel.value}:{hit.url}:{hit.page}:{hit.text[:200]}"
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
        if len(merged) >= limit:
            break
    return merged


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
