"""配置加载：合并 example / local / 环境变量三层来源。

加载优先级（后者覆盖前者）：
  1. config/config.example.yaml   —— 结构与默认值的基线（提交到 Git）
  2. config/config.local.yaml     —— 本地实配含密钥（被 .gitignore 忽略）
  3. 环境变量 FINAGENT__<SECTION>__<KEY>  —— 部署/CI 覆盖

设计目标：项目所有需要自定义的参数都集中在 YAML 里，代码不硬编码。
"""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field

from .schemas import (
    AgentConfig,
    MCPConfig,
    ModelsConfig,
    ObservabilityConfig,
    RAGConfig,
    RedisConfig,
    SecurityConfig,
    ServerConfig,
    StorageConfig,
    WebResearchConfig,
)

# 环境变量前缀与层级分隔符：FINAGENT__MODELS__DEFAULT=xxx
_ENV_PREFIX = "FINAGENT__"
_ENV_SEP = "__"

# 源码模式的仓库根；wheel 安装后优先使用工作目录或显式配置目录。
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _default_config_dir() -> Path:
    explicit = os.environ.get("FINAGENT_CONFIG_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = (
        Path.cwd() / "config",
        _REPO_ROOT / "config",
    )
    for candidate in candidates:
        if (candidate / "config.example.yaml").exists():
            return candidate
    return candidates[0]


class AppConfig(BaseModel):
    """应用级配置聚合。"""

    models: ModelsConfig
    server: ServerConfig = Field(default_factory=ServerConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    web_research: WebResearchConfig = Field(default_factory=WebResearchConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件 {path} 顶层必须是映射（key: value）")
    return data


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并两个字典，override 优先；不修改入参。"""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _coerce_scalar(text: str) -> Any:
    """把环境变量字符串按 YAML 规则解析成 bool/int/float/null 等。"""
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return text


def _env_overrides() -> Dict[str, Any]:
    """收集 FINAGENT__ 前缀的环境变量，展开成嵌套 dict。"""
    overrides: Dict[str, Any] = {}
    for env_key, env_value in os.environ.items():
        if not env_key.startswith(_ENV_PREFIX):
            continue
        path = env_key[len(_ENV_PREFIX) :].split(_ENV_SEP)
        if not all(path):
            continue
        cursor = overrides
        for part in path[:-1]:
            cursor = cursor.setdefault(part.lower(), {})
            if not isinstance(cursor, dict):
                break
        else:
            cursor[path[-1].lower()] = _coerce_scalar(env_value)
    return overrides


def load_config(
    config_dir: Optional[Path] = None,
    *,
    include_env: bool = True,
) -> AppConfig:
    """加载并合并配置，返回强类型 AppConfig。"""
    directory = config_dir or _default_config_dir()
    merged = _read_yaml(directory / "config.example.yaml")
    merged = _deep_merge(merged, _read_yaml(directory / "config.local.yaml"))
    if include_env:
        merged = _deep_merge(merged, _env_overrides())

    if not merged:
        raise FileNotFoundError(
            f"未找到任何配置。请在 {directory} 下由 config.example.yaml "
            "复制出 config.local.yaml 并填写。"
        )
    return AppConfig.model_validate(merged)


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """进程内单例配置（首次调用时加载并缓存）。"""
    return load_config()
