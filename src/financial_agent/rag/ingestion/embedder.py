"""BGE-M3 embedding adapter through LiteLLM/OpenAI-compatible APIs."""

from __future__ import annotations

import asyncio
from typing import Protocol

import litellm

from financial_agent.config import AppConfig, get_config


class Embedder(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class LiteLLMEmbedder:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        if not self._config.rag.embedding_api_base:
            raise ValueError("未配置 rag.embedding_api_base")

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        batch_size = 16
        for offset in range(0, len(texts), batch_size):
            vectors.extend(
                await asyncio.to_thread(
                    self._embed_batch,
                    texts[offset : offset + batch_size],
                )
            )
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = litellm.embedding(
            model=self._config.rag.embedding_model,
            input=texts,
            api_base=self._config.rag.embedding_api_base,
            api_key=self._config.rag.embedding_api_key or None,
        )
        data = sorted(response["data"], key=lambda item: item["index"])
        vectors = [list(map(float, item["embedding"])) for item in data]
        expected = self._config.rag.embedding_dimension
        if any(len(vector) != expected for vector in vectors):
            dimensions = sorted({len(vector) for vector in vectors})
            raise ValueError(f"Embedding 维度不符合配置：expected={expected}, actual={dimensions}")
        return vectors
