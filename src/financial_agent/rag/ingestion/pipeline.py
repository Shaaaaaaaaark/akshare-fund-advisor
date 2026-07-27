"""Document ingestion pipeline with atomic version publication."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from financial_agent.config import AppConfig, get_config
from financial_agent.rag.retrieval.elasticsearch import ElasticsearchChunkIndex
from financial_agent.repositories import SQLRepository

from .chunker import chunk_blocks
from .embedder import Embedder
from .models import IngestionChunk, SourceDescriptor, VersionDescriptor
from .parser import DocumentParser, LightweightParser, MinerUParser

SHANGHAI = ZoneInfo("Asia/Shanghai")


class DocumentIngestionPipeline:
    def __init__(
        self,
        repository: SQLRepository,
        config: AppConfig | None = None,
        *,
        parser: DocumentParser | None = None,
        embedder: Embedder | None = None,
        keyword_index: ElasticsearchChunkIndex | None = None,
    ) -> None:
        self._config = config or get_config()
        self._repository = repository
        self._parser = parser or self._default_parser()
        self._embedder = embedder
        self._keyword = keyword_index

    def _default_parser(self) -> DocumentParser:
        command = self._config.rag.mineru_command.strip()
        return MinerUParser(command) if command else LightweightParser()

    async def ingest(
        self,
        *,
        path: Path,
        source_url: str,
        title: str,
        doc_type: str,
        version: str,
        subject_code: str | None = None,
        publish_date: date | None = None,
        effective_date: date | None = None,
    ) -> VersionDescriptor:
        if not path.is_file():
            raise FileNotFoundError(path)
        parsed_url = urlparse(source_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("source_url 必须是官方 http/https 地址")
        host = parsed_url.hostname.lower().rstrip(".")
        allowed = [
            item.lower().rstrip(".") for item in self._config.security.allowed_document_domains
        ]
        if allowed and not any(host == item or host.endswith(f".{item}") for item in allowed):
            raise ValueError(f"source_url 域名不在官方 allowlist：{host}")

        content = path.read_bytes()
        content_sha256 = hashlib.sha256(content).hexdigest()
        source = SourceDescriptor(
            id=uuid5(NAMESPACE_URL, source_url),
            source_url=source_url,
            source_domain=host,
        )
        descriptor = VersionDescriptor(
            id=uuid5(source.id, content_sha256),
            title=title,
            doc_type=doc_type,
            subject_code=subject_code,
            content_sha256=content_sha256,
            version=version,
            publish_date=publish_date,
            effective_date=effective_date,
            metadata={
                "parser": type(self._parser).__name__,
                "source_filename": path.name,
            },
        )

        blocks = await self._parser.parse(path)
        parsed_chunks = chunk_blocks(blocks)
        if not parsed_chunks:
            raise ValueError("文档解析后没有可发布文本")
        embeddings = (
            await self._embedder.embed_documents([item.text for item in parsed_chunks])
            if self._embedder is not None
            else [None] * len(parsed_chunks)
        )
        if len(embeddings) != len(parsed_chunks):
            raise ValueError("Embedding 数量与文档分块数量不一致")

        chunks: list[IngestionChunk] = []
        for index, (block, embedding) in enumerate(zip(parsed_chunks, embeddings, strict=True)):
            chunk_hash = hashlib.sha256(block.text.encode("utf-8")).hexdigest()
            chunks.append(
                IngestionChunk(
                    id=uuid5(descriptor.id, f"{index}:{chunk_hash}"),
                    chunk_index=index,
                    page_start=block.page,
                    page_end=block.page,
                    section_path=block.section_path,
                    content=block.text,
                    content_sha256=chunk_hash,
                    embedding_model=self._config.rag.embedding_model,
                    embedding=embedding,
                    metadata={"numeric_allowed": False},
                )
            )

        now = datetime.now(SHANGHAI)
        self._repository.publish_document(
            source=source.model_dump(mode="python"),
            version=descriptor.model_dump(mode="python"),
            chunks=[item.model_dump(mode="python") for item in chunks],
            now=now,
        )
        if self._keyword is not None and self._keyword.enabled:
            self._keyword.rebuild(self._repository)
        return descriptor
