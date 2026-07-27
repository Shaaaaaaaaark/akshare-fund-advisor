"""Ingest one official document into PostgreSQL/pgvector and Elasticsearch."""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from pathlib import Path

from financial_agent.config import get_config
from financial_agent.rag.ingestion import (
    DocumentIngestionPipeline,
    LiteLLMEmbedder,
)
from financial_agent.rag.retrieval import ElasticsearchChunkIndex
from financial_agent.repositories import SQLRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="摄取一份官方金融文档")
    parser.add_argument("path", type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--doc-type", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--subject-code")
    parser.add_argument("--publish-date", type=date.fromisoformat)
    parser.add_argument("--effective-date", type=date.fromisoformat)
    parser.add_argument(
        "--without-embeddings",
        action="store_true",
        help="只发布文本，跳过 BGE-M3；该文档只能走 BM25/本地检索",
    )
    return parser


async def run(args: argparse.Namespace) -> None:
    config = get_config()
    repository = SQLRepository(config)
    repository.initialize()
    embedder = None if args.without_embeddings else LiteLLMEmbedder(config)
    elasticsearch = ElasticsearchChunkIndex(config)
    pipeline = DocumentIngestionPipeline(
        repository,
        config,
        embedder=embedder,
        keyword_index=elasticsearch,
    )
    descriptor = await pipeline.ingest(
        path=args.path,
        source_url=args.source_url,
        title=args.title,
        doc_type=args.doc_type,
        version=args.version,
        subject_code=args.subject_code,
        publish_date=args.publish_date,
        effective_date=args.effective_date,
    )
    print(descriptor.model_dump_json(indent=2))


def main() -> None:
    asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
