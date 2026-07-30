"""Bounded three-channel retrieval service.

The knowledge channel starts with a local lexical implementation so the
product remains runnable without an embedding service. Pgvector and BM25 can
replace it behind the same interface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from financial_agent.config import AppConfig, get_config
from financial_agent.models import LLMClient, system, user
from financial_agent.prompts import (
    RAG_JUDGE_SYSTEM_PROMPT,
    RAG_PLANNER_SYSTEM_PROMPT,
)
from financial_agent.repositories import SQLRepository

from .direct_reader import DirectDocumentReader
from .models import (
    DocumentHit,
    RetrievalAssessment,
    RetrievalChannel,
    RetrievalPlan,
    RetrievalQuery,
    RetrievalRequest,
)
from .text import query_terms
from .web import MCPWebRetriever

logger = logging.getLogger("financial_agent.rag")

_DOCUMENT_INTENTS = {
    "document_qa",
    "web_research",
    "fund_analysis",
    "fund_compare",
    "dca_reference",
    "sell_or_rebalance",
}
_DOCUMENT_MARKERS = (
    "招募说明书",
    "基金合同",
    "投资范围",
    "费用",
    "编制方案",
    "编制规则",
    "成分",
    "公告",
    "定期报告",
    "监管规则",
)
_WEB_MARKERS = ("新闻", "近期", "最近", "政策", "事件", "舆情", "背景", "影响")
_ALLOWED_DOC_TYPES = {
    "fund_prospectus",
    "fund_contract",
    "periodic_report",
    "index_methodology",
    "company_announcement",
    "regulation",
}


class KnowledgeRetriever(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]: ...


class WebRetriever(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]: ...


class LocalKnowledgeRetriever:
    """Small-scale fallback over parsed text files in document_dir."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()

    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        root = Path(self._config.storage.document_dir)
        if not root.exists():
            return []
        return await asyncio.to_thread(self._search, root, request)

    @staticmethod
    def _search(root: Path, request: RetrievalRequest) -> list[DocumentHit]:
        terms = query_terms(request.question)
        hits: list[DocumentHit] = []
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for index, chunk in enumerate(_chunk_text(text)):
                lowered = chunk.lower()
                score = float(sum(1 for term in terms if term in lowered))
                if score <= 0:
                    continue
                hits.append(
                    DocumentHit(
                        channel=RetrievalChannel.KNOWLEDGE,
                        title=path.stem,
                        url=path.resolve().as_uri(),
                        text=chunk,
                        score=score,
                        version="local",
                        metadata={"chunk_index": index, "numeric_allowed": False},
                    )
                )
        hits.sort(key=lambda item: (-item.score, item.title))
        return hits[: request.limit]


class DisabledWebRetriever:
    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        return []


class RAGService:
    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        direct_reader: DirectDocumentReader | None = None,
        knowledge: KnowledgeRetriever | None = None,
        web: WebRetriever | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._direct = direct_reader or DirectDocumentReader(self._config)
        self._knowledge = knowledge or LocalKnowledgeRetriever(self._config)
        self._llm = llm
        self._web = web or (
            MCPWebRetriever(self._config)
            if self._config.web_research.enabled
            or self._config.rag.web_search_api_key
            else DisabledWebRetriever()
        )

    async def plan(
        self,
        *,
        question: str,
        intent: str,
        entity_queries: Sequence[str] = (),
        round_number: int,
        previous_queries: Sequence[str] = (),
        previous_hits: Sequence[DocumentHit] = (),
        previous_assessment: RetrievalAssessment | None = None,
    ) -> RetrievalPlan:
        fallback = self._deterministic_plan(
            question=question,
            intent=intent,
            entity_queries=entity_queries,
            round_number=round_number,
            previous_queries=previous_queries,
            previous_hits=previous_hits,
            previous_assessment=previous_assessment,
        )
        if (
            not self._config.rag.enabled
            or self._llm is None
            or not self._config.rag.use_llm_agent
            or _first_url(question)
            or not fallback.queries
        ):
            return fallback

        payload = {
            "question": question,
            "intent": intent,
            "entity_queries": list(entity_queries),
            "round_number": round_number,
            "previous_queries": list(previous_queries),
            "previous_hits": [
                {
                    "channel": item.channel.value,
                    "title": item.title,
                    "version": item.version,
                    "page": item.page,
                }
                for item in previous_hits[: self._config.rag.max_chunks]
            ],
            "previous_assessment": (
                previous_assessment.model_dump(mode="json")
                if previous_assessment is not None
                else None
            ),
            "limits": {
                "max_queries": self._config.rag.max_queries_per_round,
                "max_chunks": self._config.rag.max_chunks,
                "web_enabled": self._config.rag.web_enabled,
            },
        }
        try:
            raw = await asyncio.to_thread(
                self._llm.complete_json,
                [
                    system(RAG_PLANNER_SYSTEM_PROMPT),
                    user(json.dumps(payload, ensure_ascii=False)),
                ],
                model=self._config.models.rag_alias(),
                temperature=0,
                max_tokens=900,
            )
            candidate = RetrievalPlan.model_validate(raw)
            normalized = self._normalize_plan(
                candidate,
                question=question,
                entity_queries=entity_queries,
                round_number=round_number,
            )
            return normalized if normalized.queries or not fallback.queries else fallback
        except Exception as exc:
            logger.warning("RAG planner fallback round=%s: %s", round_number, exc)
            return fallback

    async def execute(
        self,
        plan: RetrievalPlan,
    ) -> tuple[list[DocumentHit], list[str]]:
        async def run(item: RetrievalQuery) -> list[DocumentHit]:
            request = RetrievalRequest(
                question=item.query,
                channel=item.channel,
                url=item.url,
                subject_code=item.subject_code,
                doc_types=item.doc_types,
                limit=item.limit,
            )
            if item.channel == RetrievalChannel.DIRECT_DOCUMENT:
                hits = await self._direct.read(request)
            elif item.channel == RetrievalChannel.WEB:
                hits = await self._web.retrieve(request)
            else:
                hits = await self._knowledge.retrieve(request)
            return [
                hit.model_copy(
                    update={
                        "metadata": {
                            **hit.metadata,
                            "retrieval_round": plan.round_number,
                            "retrieval_query": item.query,
                            "retrieval_reason": item.reason,
                        }
                    }
                )
                for hit in hits
            ]

        outcomes = await asyncio.gather(
            *(run(item) for item in plan.queries),
            return_exceptions=True,
        )
        hits: list[DocumentHit] = []
        errors: list[str] = []
        seen: set[str] = set()
        for item, outcome in zip(plan.queries, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                errors.append(f"{item.channel.value}: {outcome}")
                continue
            for hit in outcome:
                key = str(hit.metadata.get("chunk_id") or hit.hit_id)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(hit)
        return hits, errors

    async def assess(
        self,
        *,
        question: str,
        plan: RetrievalPlan,
        hits: Sequence[DocumentHit],
    ) -> RetrievalAssessment:
        fallback = self._deterministic_assessment(
            question=question,
            plan=plan,
            hits=hits,
        )
        if (
            self._llm is None
            or not self._config.rag.use_llm_agent
            or not hits
            or not plan.queries
        ):
            return fallback

        remaining = self._config.rag.max_context_chars
        snippets: list[dict[str, Any]] = []
        for hit in hits[: self._config.rag.max_chunks]:
            text = hit.text[:remaining]
            if not text:
                break
            snippets.append(
                {
                    "channel": hit.channel.value,
                    "title": hit.title,
                    "url": hit.url,
                    "page": hit.page,
                    "version": hit.version,
                    "text": text,
                }
            )
            remaining -= len(text)
            if remaining <= 0:
                break
        payload = {
            "question": question,
            "round_number": plan.round_number,
            "queries": [item.model_dump(mode="json") for item in plan.queries],
            "snippets": snippets,
        }
        try:
            raw = await asyncio.to_thread(
                self._llm.complete_json,
                [
                    system(RAG_JUDGE_SYSTEM_PROMPT),
                    user(json.dumps(payload, ensure_ascii=False)),
                ],
                model=self._config.models.rag_alias(),
                temperature=0,
                max_tokens=600,
            )
            candidate = RetrievalAssessment.model_validate(raw)
            sufficient = bool(candidate.sufficient and hits)
            retryable = bool(
                not sufficient
                and candidate.retryable
                and plan.round_number < self._config.rag.max_rounds
            )
            return candidate.model_copy(
                update={
                    "sufficient": sufficient,
                    "retryable": retryable,
                    "missing_aspects": candidate.missing_aspects[
                        : self._config.rag.max_queries_per_round
                    ],
                }
            )
        except Exception as exc:
            logger.warning("RAG sufficiency fallback round=%s: %s", plan.round_number, exc)
            return fallback

    async def retrieve(
        self,
        question: str,
        entity_queries: Sequence[str] = (),
        intent: str = "document_qa",
    ) -> list[DocumentHit]:
        hits: list[DocumentHit] = []
        queries: list[str] = []
        assessment: RetrievalAssessment | None = None
        for round_number in range(1, self._config.rag.max_rounds + 1):
            plan = await self.plan(
                question=question,
                intent=intent,
                entity_queries=entity_queries,
                round_number=round_number,
                previous_queries=queries,
                previous_hits=hits,
                previous_assessment=assessment,
            )
            if not plan.queries:
                break
            round_hits, _ = await self.execute(plan)
            hits = _merge_hits(hits, round_hits, self._config.rag.max_chunks)
            queries.extend(item.query for item in plan.queries)
            assessment = await self.assess(
                question=question,
                plan=plan,
                hits=hits,
            )
            if assessment.sufficient or not assessment.retryable:
                break
        return hits

    def _deterministic_plan(
        self,
        *,
        question: str,
        intent: str,
        entity_queries: Sequence[str],
        round_number: int,
        previous_queries: Sequence[str],
        previous_hits: Sequence[DocumentHit],
        previous_assessment: RetrievalAssessment | None,
    ) -> RetrievalPlan:
        if not self._config.rag.enabled:
            return RetrievalPlan(
                round_number=round_number,
                reason="RAG 未启用，本次跳过文档检索",
            )
        url = _first_url(question)
        if url:
            return RetrievalPlan(
                round_number=round_number,
                queries=[
                    RetrievalQuery(
                        query=question,
                        channel=RetrievalChannel.DIRECT_DOCUMENT,
                        reason="用户明确提供文档 URL，优先精确读取",
                        url=url,
                        limit=self._config.rag.max_chunks,
                    )
                ]
                if round_number == 1
                else [],
                reason="指定文档采用 JIT 读取，不进行无边界扩展",
            )
        if not _needs_retrieval(question, intent):
            return RetrievalPlan(
                round_number=round_number,
                reason="当前问题只需要市场工具事实，JIT 跳过文档检索",
            )
        if intent == "web_research":
            if (
                self._config.rag.web_enabled
                and _web_search_configured(self._config)
            ):
                return RetrievalPlan(
                    round_number=round_number,
                    queries=[
                        RetrievalQuery(
                            query=question,
                            channel=RetrievalChannel.WEB,
                            reason="用户明确要求检索公开网页背景",
                            limit=self._config.rag.max_chunks,
                        )
                    ],
                    reason="显式网页研究请求只使用受控 Web 通道",
                )
            return RetrievalPlan(
                round_number=round_number,
                reason="网页研究通道未启用或未配置",
            )

        subject_code = _subject_code(entity_queries)
        candidates: list[RetrievalQuery] = []
        knowledge_on = self._config.rag.knowledge_enabled
        if round_number == 1 and knowledge_on:
            variants = _query_variants(question, entity_queries)
            for query in variants[: self._config.rag.max_queries_per_round]:
                candidates.append(
                    RetrievalQuery(
                        query=query,
                        channel=RetrievalChannel.KNOWLEDGE,
                        reason="检索官方文档中与问题直接相关的条款和说明",
                        subject_code=subject_code,
                        limit=self._config.rag.max_chunks,
                    )
                )
        elif knowledge_on:
            aspects = list((previous_assessment or _empty_assessment()).missing_aspects)
            if not aspects:
                aspects = ["与问题直接相关的官方资料"]
            entity = next(iter(entity_queries), "").strip()
            for aspect in aspects[: self._config.rag.max_queries_per_round]:
                query = f"{entity} {aspect}".strip()
                if query and query not in previous_queries:
                    candidates.append(
                        RetrievalQuery(
                            query=query,
                            channel=RetrievalChannel.KNOWLEDGE,
                            reason="根据上一轮缺口改写查询",
                            subject_code=subject_code,
                            limit=self._config.rag.max_chunks,
                        )
                    )
        if (
            self._config.rag.web_enabled
            and _web_search_configured(self._config)
            and _needs_web(question)
            and not any(item.channel == RetrievalChannel.WEB for item in candidates)
        ):
            candidates = candidates[
                : max(0, self._config.rag.max_queries_per_round - 1)
            ]
            candidates.append(
                RetrievalQuery(
                    query=question,
                    channel=RetrievalChannel.WEB,
                    reason="补充近期政策或事件的非数值背景",
                    limit=self._config.rag.max_chunks,
                )
            )
        if not candidates and not previous_hits:
            return RetrievalPlan(
                round_number=round_number,
                reason="没有新的安全查询可执行",
            )
        return RetrievalPlan(
            round_number=round_number,
            queries=candidates[: self._config.rag.max_queries_per_round],
            reason="使用受控规则生成本轮检索计划",
        )

    def _normalize_plan(
        self,
        plan: RetrievalPlan,
        *,
        question: str,
        entity_queries: Sequence[str],
        round_number: int,
    ) -> RetrievalPlan:
        direct_url = _first_url(question)
        subject_code = _subject_code(entity_queries)
        queries: list[RetrievalQuery] = []
        seen: set[tuple[str, str]] = set()
        for item in plan.queries:
            if item.channel == RetrievalChannel.WEB and not self._config.rag.web_enabled:
                continue
            if (
                item.channel == RetrievalChannel.KNOWLEDGE
                and not self._config.rag.knowledge_enabled
            ):
                # 通道一默认关闭：即便模型规划了知识检索也一律丢弃，
                # 产品事实交给实时工具，条款走 JIT，避免固定语料库幻觉。
                continue
            if item.channel == RetrievalChannel.DIRECT_DOCUMENT and direct_url is None:
                continue
            key = (item.channel.value, item.query.strip())
            if key in seen:
                continue
            seen.add(key)
            queries.append(
                item.model_copy(
                    update={
                        "url": direct_url
                        if item.channel == RetrievalChannel.DIRECT_DOCUMENT
                        else None,
                        "subject_code": (
                            subject_code
                            if item.channel == RetrievalChannel.KNOWLEDGE
                            else None
                        ),
                        "doc_types": [
                            value
                            for value in item.doc_types
                            if value in _ALLOWED_DOC_TYPES
                        ],
                        "limit": min(item.limit, self._config.rag.max_chunks),
                    }
                )
            )
            if len(queries) >= self._config.rag.max_queries_per_round:
                break
        return RetrievalPlan(
            round_number=round_number,
            queries=queries,
            reason=plan.reason,
        )

    def _deterministic_assessment(
        self,
        *,
        question: str,
        plan: RetrievalPlan,
        hits: Sequence[DocumentHit],
    ) -> RetrievalAssessment:
        if not plan.queries:
            return RetrievalAssessment(
                sufficient=True,
                retryable=False,
                reason="JIT 规划判定当前问题不需要文档检索",
            )
        if not hits:
            retryable = plan.round_number < self._config.rag.max_rounds
            return RetrievalAssessment(
                sufficient=False,
                retryable=retryable,
                reason="本轮没有召回可引用片段",
                missing_aspects=["与问题直接相关的官方资料"] if retryable else [],
            )
        terms = query_terms(question)
        corpus = "\n".join(item.text.lower() for item in hits)
        covered = sum(1 for term in terms if term in corpus)
        coverage = covered / max(len(terms), 1)
        sufficient = any(
            item.channel == RetrievalChannel.DIRECT_DOCUMENT for item in hits
        ) or len(hits) >= 2 or coverage >= 0.2
        retryable = bool(
            not sufficient and plan.round_number < self._config.rag.max_rounds
        )
        return RetrievalAssessment(
            sufficient=sufficient,
            retryable=retryable,
            reason=(
                "召回片段已覆盖问题并包含可引用来源"
                if sufficient
                else "召回内容与问题的词项覆盖仍不足"
            ),
            missing_aspects=["问题中尚未覆盖的主题"] if retryable else [],
        )


def _first_url(text: str) -> str | None:
    matched = re.search(r"https?://[^\s<>\"]+", text)
    return matched.group(0).rstrip("。），,)") if matched else None


def _chunk_text(text: str, maximum_chars: int = 1800) -> list[str]:
    chunks: list[str] = []
    current = ""
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if current and len(current) + len(paragraph) + 1 > maximum_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def _query_variants(
    question: str,
    entity_queries: Sequence[str],
) -> list[str]:
    variants = [question.strip()]
    compact = re.sub(
        r"(请问|请|帮我|一下|是什么|怎么样|如何|为什么|吗)",
        " ",
        question,
    )
    compact = re.sub(r"\s+", " ", compact).strip()
    if compact and compact not in variants:
        variants.append(compact)
    entity = next(iter(entity_queries), "").strip()
    if entity and entity not in compact:
        variants.append(f"{entity} {compact}".strip())
    return variants


def _needs_retrieval(question: str, intent: str) -> bool:
    return (
        intent in _DOCUMENT_INTENTS
        or any(marker in question for marker in _DOCUMENT_MARKERS)
        or _needs_web(question)
    )


def _needs_web(question: str) -> bool:
    return any(marker in question for marker in _WEB_MARKERS)


def _web_search_configured(config: AppConfig) -> bool:
    # 只要搜索兜底链里有任一凭证齐全的供应商即视为已配置。
    if config.web_research.enabled and config.web_research.resolved_chain():
        return True
    return bool(config.rag.web_search_api_key)


def _subject_code(entity_queries: Sequence[str]) -> str | None:
    for value in entity_queries:
        normalized = value.strip()
        if re.fullmatch(r"\d{6}", normalized):
            return normalized
    return None


def _empty_assessment() -> RetrievalAssessment:
    return RetrievalAssessment(
        sufficient=False,
        retryable=True,
        reason="尚未执行充分性判断",
    )


def _merge_hits(
    existing: Sequence[DocumentHit],
    incoming: Sequence[DocumentHit],
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


def build_rag_service(
    config: AppConfig,
    repository: SQLRepository,
) -> RAGService:
    from financial_agent.rag.retrieval import ElasticsearchChunkIndex

    llm = (
        LLMClient(config)
        if config.rag.enabled and config.rag.use_llm_agent
        else None
    )
    keyword = ElasticsearchChunkIndex(config)
    if (
        config.rag.enabled
        and repository.engine.dialect.name == "postgresql"
        and config.rag.embedding_api_base
    ):
        from financial_agent.rag.ingestion.embedder import LiteLLMEmbedder
        from financial_agent.rag.retrieval import PgVectorKnowledgeRetriever

        knowledge = PgVectorKnowledgeRetriever(
            repository,
            LiteLLMEmbedder(config),
            keyword_index=keyword,
        )
        return RAGService(config, knowledge=knowledge, llm=llm)
    if config.rag.enabled and keyword.enabled:
        return RAGService(config, knowledge=keyword, llm=llm)
    return RAGService(config, llm=llm)
