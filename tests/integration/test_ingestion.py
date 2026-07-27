from datetime import date
from pathlib import Path

import pytest

from financial_agent.rag.ingestion import DocumentIngestionPipeline
from financial_agent.repositories import SQLRepository


@pytest.mark.asyncio
async def test_ingestion_publishes_citable_chunks(
    test_config,
    tmp_path: Path,
) -> None:
    repository = SQLRepository(test_config)
    repository.initialize()
    document = tmp_path / "prospectus.md"
    document.write_text(
        "# 基金的投资\n\n## 投资范围\n\n本基金主要投资于沪深300指数成份证券。",
        encoding="utf-8",
    )
    pipeline = DocumentIngestionPipeline(repository, test_config)

    descriptor = await pipeline.ingest(
        path=document,
        source_url="https://sse.com.cn/example/prospectus.pdf",
        title="示例基金招募说明书",
        doc_type="fund_prospectus",
        version="2026-01",
        subject_code="510300",
        publish_date=date(2026, 7, 1),
    )
    chunks = repository.list_current_chunks()

    assert descriptor.subject_code == "510300"
    assert len(chunks) == 1
    assert chunks[0]["section_path"] == ["基金的投资", "投资范围"]
    assert chunks[0]["source_url"].startswith("https://sse.com.cn/")


@pytest.mark.asyncio
async def test_ingestion_rejects_unapproved_domain(
    test_config,
    tmp_path: Path,
) -> None:
    repository = SQLRepository(test_config)
    repository.initialize()
    document = tmp_path / "bad.md"
    document.write_text("不可信内容", encoding="utf-8")
    pipeline = DocumentIngestionPipeline(repository, test_config)

    with pytest.raises(ValueError, match="allowlist"):
        await pipeline.ingest(
            path=document,
            source_url="https://untrusted.example/doc.pdf",
            title="不可信文档",
            doc_type="unknown",
            version="1",
        )
