"""Elasticsearch BM25 index as a rebuildable PostgreSQL projection."""

from __future__ import annotations

import asyncio
from typing import Any

from elasticsearch import Elasticsearch, helpers

from financial_agent.config import AppConfig, get_config
from financial_agent.rag.models import DocumentHit, RetrievalChannel, RetrievalRequest
from financial_agent.repositories import SQLRepository


class ElasticsearchChunkIndex:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        self._url = self._config.rag.elasticsearch_url
        self._index = self._config.rag.elasticsearch_index
        self._client = Elasticsearch(self._url) if self._url else None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def ensure_index(self) -> None:
        if self._client is None or self._client.indices.exists(index=self._index):
            return
        self._client.indices.create(
            index=self._index,
            mappings={
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "subject_code": {"type": "keyword"},
                    "doc_type": {"type": "keyword"},
                    "document_version_id": {"type": "keyword"},
                    "version": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "content": {"type": "text"},
                    "section_path": {"type": "text"},
                    "source_url": {"type": "keyword", "index": False},
                    "page_start": {"type": "integer"},
                    "page_end": {"type": "integer"},
                }
            },
        )

    def rebuild(self, repository: SQLRepository) -> int:
        if self._client is None:
            return 0
        self.ensure_index()
        chunks = repository.list_current_chunks()
        self._client.delete_by_query(
            index=self._index,
            query={"match_all": {}},
            conflicts="proceed",
            refresh=True,
        )
        if not chunks:
            return 0
        actions = [
            {
                "_index": self._index,
                "_id": item["chunk_id"],
                "_source": item,
            }
            for item in chunks
        ]
        success, _ = helpers.bulk(self._client, actions, refresh=True)
        return int(success)

    async def retrieve(self, request: RetrievalRequest) -> list[DocumentHit]:
        if self._client is None:
            return []
        return await asyncio.to_thread(self._search, request)

    def _search(self, request: RetrievalRequest) -> list[DocumentHit]:
        if self._client is None:
            return []
        self.ensure_index()
        filters: list[dict[str, Any]] = []
        if request.subject_code:
            filters.append({"term": {"subject_code": request.subject_code}})
        if request.doc_types:
            filters.append({"terms": {"doc_type": request.doc_types}})
        response = self._client.search(
            index=self._index,
            size=request.limit,
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": request.question,
                                "fields": ["title^2", "section_path^2", "content"],
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
        )
        return [
            DocumentHit(
                channel=RetrievalChannel.KNOWLEDGE,
                title=item["_source"]["title"],
                url=item["_source"]["source_url"],
                text=item["_source"]["content"],
                score=float(item.get("_score") or 0),
                page=item["_source"].get("page_start"),
                version=item["_source"].get("version"),
                subject_code=item["_source"].get("subject_code"),
                doc_type=item["_source"].get("doc_type"),
                metadata={
                    "document_version_id": item["_source"].get("document_version_id"),
                    "section_path": item["_source"].get("section_path", []),
                    "numeric_allowed": False,
                },
            )
            for item in response["hits"]["hits"]
        ]
