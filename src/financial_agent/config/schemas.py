"""配置的强类型模型（Pydantic）。

用 Pydantic 描述配置结构，既能校验字段、给默认值，也让 IDE 有补全。
所有可自定义项都集中在这里定义，与 config/*.yaml 一一对应。
"""

from __future__ import annotations

from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ProviderConfig(BaseModel):
    """一个模型供应商的凭证与端点。"""

    api_base: str = Field(..., description="OpenAI 兼容 API 的 base_url")
    api_key: str = Field(..., description="供应商 API Key（只应出现在本地配置）")


class ModelEntry(BaseModel):
    """模型注册表中的一项：别名对应的具体模型与默认调用参数。"""

    litellm_model: str = Field(
        ...,
        description="LiteLLM 模型标识，如 openai/deepseek-v4-flash",
    )
    provider: str = Field(..., description="引用 providers 中的供应商名")
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout_seconds: int = 60
    rpm_limit: Optional[int] = None


class LiteLLMConfig(BaseModel):
    """LiteLLM 的全局行为。"""

    num_retries: int = 2
    verbose: bool = False
    drop_params: bool = True


class ModelsConfig(BaseModel):
    """模型层配置。"""

    default: str = Field(..., description="默认模型别名")
    report: str = Field("", description="报告场景模型别名；空则回退 default")
    rag: str = Field("", description="RAG 规划和充分性判断模型别名；空则回退 default")
    providers: Dict[str, ProviderConfig]
    registry: Dict[str, ModelEntry]
    litellm: LiteLLMConfig = Field(default_factory=LiteLLMConfig)

    @field_validator("registry")
    @classmethod
    def _registry_not_empty(cls, value: Dict[str, ModelEntry]) -> Dict[str, ModelEntry]:
        if not value:
            raise ValueError("models.registry 不能为空")
        return value

    def resolve(self, alias: Optional[str] = None) -> ModelEntry:
        """按别名取模型配置；alias 为空时用 default。"""
        name = alias or self.default
        if name not in self.registry:
            raise KeyError(f"模型别名 '{name}' 不在 registry 中，可用：{sorted(self.registry)}")
        return self.registry[name]

    def report_alias(self) -> str:
        """报告场景的模型别名：配置了 report 就用它，否则用 default。"""
        return self.report or self.default

    def rag_alias(self) -> str:
        """RAG 场景的模型别名：配置了 rag 就用它，否则用 default。"""
        return self.rag or self.default


class ObservabilityConfig(BaseModel):
    """可观测性配置。"""

    log_level: str = "INFO"
    log_prompts: bool = False
    elasticsearch_url: str = ""
    audit_index: str = "finagent-audit-v1"
    report_index: str = "finagent-reports-v1"


class ServerConfig(BaseModel):
    """HTTP server settings."""

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False
    api_token: str = ""


class AgentConfig(BaseModel):
    """Controlled graph limits."""

    use_llm_for_intent: bool = False
    use_llm_for_report: bool = True
    maximum_report_facts: int = Field(default=20, ge=1, le=100)
    checkpoint: Literal["memory", "postgres"] = "memory"


class MCPConfig(BaseModel):
    """Fund Advisor tool transport and runtime controls."""

    transport: Literal["inprocess", "stdio", "http"] = "inprocess"
    server_command: str = ""
    server_url: str = "http://127.0.0.1:8001/mcp"
    host: str = "127.0.0.1"
    port: int = Field(default=8001, ge=1, le=65535)
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    concurrency: int = Field(default=2, ge=1, le=16)


class StorageConfig(BaseModel):
    """Transaction store and local document location."""

    database_url: str = "sqlite:///./data/financial_agent.db"
    create_schema: bool = True
    document_dir: str = "./data/documents"


class RedisConfig(BaseModel):
    """Optional cache settings. Empty URL disables Redis."""

    url: str = ""
    key_prefix: str = "finagent"
    default_ttl_seconds: int = Field(default=900, ge=1)


class RAGConfig(BaseModel):
    """Bounded Agentic RAG settings."""

    enabled: bool = False
    web_enabled: bool = False
    use_llm_agent: bool = True
    max_rounds: int = Field(default=3, ge=1, le=5)
    max_queries_per_round: int = Field(default=2, ge=1, le=5)
    max_chunks: int = Field(default=8, ge=1, le=20)
    max_context_chars: int = Field(default=24000, ge=1000, le=100000)
    embedding_model: str = "BAAI/bge-m3"
    embedding_dimension: int = Field(default=1024, ge=1)
    embedding_api_base: str = ""
    embedding_api_key: str = ""
    mineru_command: str = ""
    elasticsearch_url: str = ""
    elasticsearch_index: str = "finagent-doc-chunks-v1"
    web_search_api_key: str = ""


class SecurityConfig(BaseModel):
    """Outbound and prompt privacy controls."""

    allowed_document_domains: list[str] = Field(default_factory=list)
    max_document_bytes: int = Field(default=20 * 1024 * 1024, ge=1024)
    redact_portfolio_values: bool = True
