"""Complete-envelope cache with an optional Redis backend."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Protocol

from redis import Redis
from redis.exceptions import RedisError

from financial_agent.config import AppConfig


class EnvelopeCache(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None: ...


class MemoryEnvelopeCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= time.monotonic():
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + ttl, value)


class RedisEnvelopeCache:
    """Redis primary with a safe process-local fallback."""

    def __init__(self, url: str, prefix: str) -> None:
        self._client = Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        self._prefix = prefix
        self._fallback = MemoryEnvelopeCache()

    def _key(self, key: str) -> str:
        return f"{self._prefix}:tool:v1:{key}"

    def get(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._key(key))
            if raw:
                value = json.loads(raw)
                if isinstance(value, dict):
                    return value
        except (RedisError, json.JSONDecodeError):
            pass
        return self._fallback.get(key)

    def set(self, key: str, value: dict[str, Any], ttl: int) -> None:
        self._fallback.set(key, value, ttl)
        try:
            self._client.set(
                self._key(key),
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                ex=ttl,
            )
        except RedisError:
            pass


def build_envelope_cache(config: AppConfig) -> EnvelopeCache:
    if config.redis.url:
        return RedisEnvelopeCache(config.redis.url, config.redis.key_prefix)
    return MemoryEnvelopeCache()
