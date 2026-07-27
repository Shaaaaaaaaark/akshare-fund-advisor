from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from financial_agent.rag import (
    DirectDocumentReader,
    DocumentSecurityError,
    LocalKnowledgeRetriever,
    RetrievalChannel,
    RetrievalRequest,
)
from financial_agent.rag.models import DocumentHit
from financial_agent.rag.retrieval import ElasticsearchChunkIndex, reciprocal_rank_fusion


@pytest.mark.asyncio
async def test_local_knowledge_returns_citable_chunk(
    test_config,
    tmp_path: Path,
) -> None:
    document_dir = Path(test_config.storage.document_dir)
    document_dir.mkdir(parents=True)
    (document_dir / "prospectus.md").write_text(
        "# 投资范围\n\n本基金主要跟踪沪深300指数，投资范围以招募说明书为准。",
        encoding="utf-8",
    )
    retriever = LocalKnowledgeRetriever(test_config)

    hits = await retriever.retrieve(
        RetrievalRequest(
            question="基金投资范围是什么",
            channel=RetrievalChannel.KNOWLEDGE,
        )
    )

    assert hits
    assert hits[0].url.startswith("file://")
    assert hits[0].metadata["numeric_allowed"] is False


@pytest.mark.asyncio
async def test_direct_reader_rejects_private_or_unapproved_url(test_config) -> None:
    reader = DirectDocumentReader(test_config)
    with pytest.raises(DocumentSecurityError):
        await reader._validate_url("http://127.0.0.1/private.pdf")


@pytest.mark.asyncio
async def test_direct_reader_stops_oversized_stream(test_config) -> None:
    limited = test_config.model_copy(
        update={"security": test_config.security.model_copy(update={"max_document_bytes": 5})}
    )
    reader = DirectDocumentReader(limited)
    response = httpx.Response(200, content=b"123456")

    with pytest.raises(DocumentSecurityError, match="超过"):
        await reader._read_limited(response)


def test_rrf_fuses_semantic_and_keyword_ranks_by_chunk_id() -> None:
    semantic = [
        DocumentHit(
            channel=RetrievalChannel.KNOWLEDGE,
            title="A",
            url="https://sse.com.cn/a",
            text="A",
            metadata={"chunk_id": "a"},
        ),
        DocumentHit(
            channel=RetrievalChannel.KNOWLEDGE,
            title="B",
            url="https://sse.com.cn/b",
            text="B",
            metadata={"chunk_id": "b"},
        ),
    ]
    keyword = [semantic[1], semantic[0]]

    fused = reciprocal_rank_fusion(semantic, keyword, limit=2)

    assert {item.metadata["chunk_id"] for item in fused} == {"a", "b"}
    assert fused[0].score == fused[1].score


def test_elasticsearch_retrieval_creates_empty_index_before_search() -> None:
    created: list[dict] = []
    retriever = ElasticsearchChunkIndex.__new__(ElasticsearchChunkIndex)
    retriever._index = "test-documents"
    retriever._client = SimpleNamespace(
        indices=SimpleNamespace(
            exists=lambda **_: False,
            create=lambda **kwargs: created.append(kwargs),
        ),
        search=lambda **_: {"hits": {"hits": []}},
    )

    hits = retriever._search(
        RetrievalRequest(
            question="基金投资范围",
            channel=RetrievalChannel.KNOWLEDGE,
        )
    )

    assert hits == []
    assert created[0]["index"] == "test-documents"
