from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from financial_agent.rag import (
    DirectDocumentReader,
    DocumentSecurityError,
    LocalKnowledgeRetriever,
    RAGService,
    RetrievalChannel,
    RetrievalRequest,
)
from financial_agent.rag.models import DocumentHit
from financial_agent.rag.retrieval import ElasticsearchChunkIndex, reciprocal_rank_fusion


class FakeRAGLLM:
    def __init__(self) -> None:
        self.messages = None

    def complete_json(self, messages, **_kwargs):
        self.messages = messages
        return {
            "round_number": 3,
            "queries": [
                {
                    "query": "近期背景",
                    "channel": "web",
                    "reason": "尝试未授权 Web",
                    "url": None,
                    "subject_code": None,
                    "doc_types": [],
                    "limit": 20,
                },
                {
                    "query": "读取其他地址",
                    "channel": "direct_document",
                    "reason": "尝试编造 URL",
                    "url": "https://example.com/invented",
                    "subject_code": None,
                    "doc_types": [],
                    "limit": 20,
                },
                {
                    "query": "基金投资范围",
                    "channel": "knowledge",
                    "reason": "查询官方产品条款",
                    "url": None,
                    "subject_code": "999999",
                    "doc_types": ["fund_prospectus", "unknown"],
                    "limit": 20,
                },
                {
                    "query": "基金费用",
                    "channel": "knowledge",
                    "reason": "查询官方费用条款",
                    "url": None,
                    "subject_code": "999999",
                    "doc_types": ["fund_contract"],
                    "limit": 20,
                },
            ],
            "reason": "模型候选计划",
        }


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


@pytest.mark.asyncio
async def test_agentic_rag_jit_skips_simple_market_question(test_config) -> None:
    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={"enabled": True, "use_llm_agent": True}
            )
        }
    )
    fake = FakeRAGLLM()
    service = RAGService(config, llm=fake)

    plan = await service.plan(
        question="沪深300现在估值高吗",
        intent="index_valuation",
        entity_queries=["沪深300"],
        round_number=1,
    )

    assert plan.queries == []
    assert "JIT" in plan.reason
    assert fake.messages is None


@pytest.mark.asyncio
async def test_llm_retrieval_plan_is_constrained_by_code(test_config) -> None:
    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={
                    "enabled": True,
                    "web_enabled": False,
                    "knowledge_enabled": True,
                    "use_llm_agent": True,
                    "max_queries_per_round": 2,
                    "max_chunks": 8,
                }
            )
        }
    )
    fake = FakeRAGLLM()
    service = RAGService(config, llm=fake)

    plan = await service.plan(
        question="分析基金510300的投资范围和费用",
        intent="fund_analysis",
        entity_queries=["510300"],
        round_number=1,
    )

    assert [item.channel for item in plan.queries] == [
        RetrievalChannel.KNOWLEDGE,
        RetrievalChannel.KNOWLEDGE,
    ]
    assert [item.subject_code for item in plan.queries] == ["510300", "510300"]
    assert plan.queries[0].doc_types == ["fund_prospectus"]
    assert all(item.limit == 8 for item in plan.queries)
    assert "RAG 的检索规划器" in fake.messages[0]["content"]


@pytest.mark.asyncio
async def test_knowledge_channel_disabled_by_default(test_config) -> None:
    """通道一默认关闭：即便模型规划知识检索也被丢弃，不查固定语料库。"""
    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={
                    "enabled": True,
                    "web_enabled": False,
                    "use_llm_agent": True,
                }
            )
        }
    )
    assert config.rag.knowledge_enabled is False
    fake = FakeRAGLLM()
    service = RAGService(config, llm=fake)

    plan = await service.plan(
        question="分析基金510300的投资范围和费用",
        intent="fund_analysis",
        entity_queries=["510300"],
        round_number=1,
    )

    assert all(
        item.channel != RetrievalChannel.KNOWLEDGE for item in plan.queries
    )


@pytest.mark.asyncio
async def test_explicit_web_intent_plans_only_web_channel(test_config) -> None:
    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={
                    "enabled": True,
                    "web_enabled": True,
                    "use_llm_agent": False,
                }
            ),
            "web_research": test_config.web_research.model_copy(
                update={"enabled": True, "api_key": "test-key"}
            ),
        }
    )
    service = RAGService(config)

    plan = await service.plan(
        question="网页搜索一下最近的基金监管政策",
        intent="web_research",
        entity_queries=["网页搜索一下最近的基金监管政策"],
        round_number=1,
    )

    assert len(plan.queries) == 1
    assert plan.queries[0].channel == RetrievalChannel.WEB


@pytest.mark.asyncio
async def test_explicit_web_intent_skips_when_provider_is_not_configured(
    test_config,
) -> None:
    config = test_config.model_copy(
        update={
            "rag": test_config.rag.model_copy(
                update={"enabled": True, "web_enabled": True}
            ),
            "web_research": test_config.web_research.model_copy(
                update={"enabled": True, "api_key": ""}
            ),
        }
    )
    service = RAGService(config)

    plan = await service.plan(
        question="网页搜索一下最近的基金监管政策",
        intent="web_research",
        entity_queries=[],
        round_number=1,
    )

    assert plan.queries == []
    assert "未启用或未配置" in plan.reason
