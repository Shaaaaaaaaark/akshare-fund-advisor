"""Bounded three-channel retrieval service.

The knowledge channel starts with a local lexical implementation so the
product remains runnable without an embedding service. Pgvector and BM25 can
replace it behind the same interface.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from financial_agent.config import AppConfig, get_config
from financial_agent.repositories import SQLRepository

from .direct_reader import DirectDocumentReader
from .models import DocumentHit, RetrievalChannel, RetrievalRequest
from .text import query_terms
from .web import BraveWebRetriever


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
    ) -> None:
        self._config = config or get_config()
        self._direct = direct_reader or DirectDocumentReader(self._config)
        self._knowledge = knowledge or LocalKnowledgeRetriever(self._config)
        self._web = web or (
            BraveWebRetriever(self._config)
            if self._config.rag.web_search_api_key
            else DisabledWebRetriever()
        )

    async def retrieve(
        self,
        question: str,
        entity_queries: Sequence[str] = (),
    ) -> list[DocumentHit]:
        if not self._config.rag.enabled:
            return []
        url = _first_url(question)
        if url:
            return await self._direct.read(
                RetrievalRequest(
                    question=question,
                    channel=RetrievalChannel.DIRECT_DOCUMENT,
                    url=url,
                    limit=self._config.rag.max_chunks,
                )
            )

        request = RetrievalRequest(
            question=question,
            channel=RetrievalChannel.KNOWLEDGE,
            subject_code=next(iter(entity_queries), None),
            limit=self._config.rag.max_chunks,
        )
        hits: list[DocumentHit] = []
        seen: set[str] = set()
        for round_number, query in enumerate(
            _query_variants(question, entity_queries),
            start=1,
        ):
            if round_number > self._config.rag.max_rounds:
                break
            round_hits = await self._knowledge.retrieve(
                request.model_copy(update={"question": query})
            )
            for hit in round_hits:
                key = str(hit.metadata.get("chunk_id") or hit.hit_id)
                if key in seen:
                    continue
                seen.add(key)
                hits.append(
                    hit.model_copy(
                        update={
                            "metadata": {
                                **hit.metadata,
                                "retrieval_round": round_number,
                                "retrieval_query": query,
                            }
                        }
                    )
                )
            if len(hits) >= self._config.rag.max_chunks:
                break
        hits = hits[: self._config.rag.max_chunks]
        if hits or not self._config.rag.web_enabled:
            return hits
        return await self._web.retrieve(
            request.model_copy(update={"channel": RetrievalChannel.WEB})
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


def build_rag_service(
    config: AppConfig,
    repository: SQLRepository,
) -> RAGService:
    from financial_agent.rag.retrieval import ElasticsearchChunkIndex

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
        return RAGService(config, knowledge=knowledge)
    if config.rag.enabled and keyword.enabled:
        return RAGService(config, knowledge=keyword)
    return RAGService(config)
