"""Pgvector semantic retrieval with optional Elasticsearch BM25 fusion."""

from __future__ import annotations

import asyncio

from financial_agent.rag.ingestion.embedder import Embedder
from financial_agent.rag.models import DocumentHit, RetrievalChannel, RetrievalRequest
from financial_agent.repositories import SQLRepository

from .elasticsearch import ElasticsearchChunkIndex


class PgVectorKnowledgeRetriever:
    def __init__(
        self,
        repository: SQLRepository,
        embedder: Embedder,
        *,
        keyword_index: ElasticsearchChunkIndex | None = None,
        rrf_k: int = 60,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._keyword = keyword_index
        self._rrf_k = rrf_k

    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        query_embedding = await self._embedder.embed_query(request.question)
        semantic_rows = await asyncio.to_thread(
            self._repository.semantic_search,
            query_embedding=query_embedding,
            subject_code=request.subject_code,
            doc_types=request.doc_types,
            limit=max(request.limit * 3, 20),
        )
        semantic = [
            DocumentHit(
                channel=RetrievalChannel.KNOWLEDGE,
                title=item["title"],
                url=item["url"],
                text=item["text"],
                score=item["score"],
                page=item["page"],
                version=item["version"],
                subject_code=item["subject_code"],
                doc_type=item["doc_type"],
                metadata={
                    **item["metadata"],
                    "chunk_id": item["chunk_id"],
                    "numeric_allowed": False,
                },
            )
            for item in semantic_rows
        ]
        if self._keyword is None or not self._keyword.enabled:
            return semantic[: request.limit]
        keyword = await self._keyword.retrieve(
            request.model_copy(update={"limit": max(request.limit * 3, 20)})
        )
        return reciprocal_rank_fusion(
            semantic,
            keyword,
            limit=request.limit,
            k=self._rrf_k,
        )


def reciprocal_rank_fusion(
    semantic: list[DocumentHit],
    keyword: list[DocumentHit],
    *,
    limit: int,
    k: int = 60,
) -> list[DocumentHit]:
    scores: dict[str, float] = {}
    values: dict[str, DocumentHit] = {}
    for results in (semantic, keyword):
        for rank, hit in enumerate(results, start=1):
            key = str(hit.metadata.get("chunk_id") or hit.hit_id)
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            values[key] = hit
    ordered = sorted(scores, key=lambda key: (-scores[key], key))
    return [values[key].model_copy(update={"score": scores[key]}) for key in ordered[:limit]]
