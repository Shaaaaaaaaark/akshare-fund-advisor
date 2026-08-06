"""Process-local complete-envelope cache."""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol

from fund_advisor_mcp.config import AppConfig


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


def build_envelope_cache(_config: AppConfig) -> EnvelopeCache:
    return MemoryEnvelopeCache()
