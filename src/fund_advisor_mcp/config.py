"""Strongly typed configuration for MCP services and the LangGraph agent."""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

_ENV_PREFIX = "FINAGENT__"
_ENV_SEPARATOR = "__"
_SUPPORTED_SEARCH_PROVIDERS = (
    "serper",
    "tavily",
    "google_cse",
    "brave",
    "serpapi",
)
_DEFAULT_SEARCH_CHAIN = list(_SUPPORTED_SEARCH_PROVIDERS)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class MCPConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["inprocess", "stdio", "http"] = "stdio"
    server_command: str = ""
    server_url: str = "http://127.0.0.1:8001/mcp"
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    concurrency: int = Field(default=2, ge=1, le=16)


class WebSearchProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    api_key: str = ""
    cx: str = ""
    api_url: str = ""

    def has_credentials(self, name: str) -> bool:
        if not self.api_key:
            return False
        return name != "google_cse" or bool(self.cx)


class WebResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    search_chain: list[str] = Field(default_factory=list)
    providers: dict[str, WebSearchProviderConfig] = Field(default_factory=dict)
    provider: str = "brave"
    api_key: str = ""
    search_api_url: str = "https://api.search.brave.com/res/v1/web/search"
    search_language: str = "zh-hans"
    transport: Literal["inprocess", "stdio", "http"] = "stdio"
    server_command: str = ""
    server_url: str = "http://127.0.0.1:8002/mcp"
    host: str = "127.0.0.1"
    port: int = Field(default=8002, ge=1, le=65535)
    timeout_seconds: int = Field(default=20, ge=1, le=120)
    max_results: int = Field(default=10, ge=1, le=20)
    max_content_chars: int = Field(default=12000, ge=1000, le=200000)
    max_fetch_bytes: int = Field(default=2 * 1024 * 1024, ge=1024)
    fetch_concurrency: int = Field(default=3, ge=1, le=10)
    allowed_domains: list[str] = Field(default_factory=list)

    def resolved_chain(self) -> list[tuple[str, WebSearchProviderConfig]]:
        chain_names = self.search_chain or _DEFAULT_SEARCH_CHAIN
        legacy: WebSearchProviderConfig | None = None
        if self.api_key:
            legacy = WebSearchProviderConfig(
                api_key=self.api_key,
                api_url=self.search_api_url if self.provider == "brave" else "",
            )

        resolved: list[tuple[str, WebSearchProviderConfig]] = []
        seen: set[str] = set()
        for name in chain_names:
            if name in seen or name not in _SUPPORTED_SEARCH_PROVIDERS:
                continue
            seen.add(name)
            provider = _as_provider_config(self.providers.get(name))
            if (
                provider is None or not provider.has_credentials(name)
            ) and name == self.provider:
                provider = legacy
            if provider is None or not provider.enabled:
                continue
            if provider.has_credentials(name):
                resolved.append((name, provider))
        return resolved


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "openai"
    api_base: str = "https://api.deepseek.com"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1500, ge=128, le=8192)
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    extra_body: dict[str, Any] = Field(default_factory=dict)

    @property
    def resolved_base_url(self) -> str:
        return self.base_url or self.api_base


class AgentConfig(BaseModel):
    # Ignore fields from the deleted Agent configuration during local migration.
    model_config = ConfigDict(extra="ignore")

    use_llm_for_intent: bool = False
    use_llm_for_associations: bool = False
    maximum_facts: int = Field(default=20, ge=2, le=100)
    maximum_tool_calls: int = Field(default=4, ge=1, le=12)


class AppConfig(BaseModel):
    # Old local files may still contain removed server/storage sections.
    model_config = ConfigDict(extra="ignore")

    mcp: MCPConfig = Field(default_factory=MCPConfig)
    web_research: WebResearchConfig = Field(default_factory=WebResearchConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)


def _as_provider_config(value: object) -> WebSearchProviderConfig | None:
    if value is None:
        return None
    if isinstance(value, WebSearchProviderConfig):
        return value
    if isinstance(value, dict):
        return WebSearchProviderConfig.model_validate(value)
    return None


def _default_config_dir() -> Path:
    configured = os.environ.get("FINAGENT_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (Path.cwd() / "config", _REPO_ROOT / "config")
    for candidate in candidates:
        if (candidate / "config.example.yaml").is_file():
            return candidate
    return candidates[0]


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"配置文件 {path} 顶层必须是映射")
    return value


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _coerce_scalar(value: str) -> Any:
    try:
        return yaml.safe_load(value)
    except yaml.YAMLError:
        return value


def _environment_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for key, value in os.environ.items():
        if not key.startswith(_ENV_PREFIX):
            continue
        path = key[len(_ENV_PREFIX) :].split(_ENV_SEPARATOR)
        if not all(path):
            continue
        cursor = overrides
        for part in path[:-1]:
            child = cursor.setdefault(part.lower(), {})
            if not isinstance(child, dict):
                break
            cursor = child
        else:
            cursor[path[-1].lower()] = _coerce_scalar(value)
    return overrides


def load_config(
    config_dir: Path | None = None,
    *,
    include_env: bool = True,
) -> AppConfig:
    directory = config_dir or _default_config_dir()
    merged = _read_yaml(directory / "config.example.yaml")
    merged = _deep_merge(merged, _read_yaml(directory / "config.local.yaml"))
    if include_env:
        merged = _deep_merge(merged, _environment_overrides())
    return AppConfig.model_validate(merged)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    return load_config()
