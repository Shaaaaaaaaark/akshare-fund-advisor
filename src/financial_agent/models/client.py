"""LiteLLM 客户端封装。

职责边界（与 HLD 一致）：
  - 模型只做语言层：意图分类、查询改写、基于已验证证据生成文本。
  - 不做金融数值计算、不判断数据时效、不修复工具结果。

对外接口：
  - complete(...)        纯文本补全
  - complete_json(...)   要求模型返回 JSON 对象并解析为 dict

换模型 / 换供应商只需改 config/*.yaml，不改调用方代码。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import litellm

from ..config import AppConfig, get_config
from ..config.schemas import ModelEntry
from .messages import Message

logger = logging.getLogger("financial_agent.models")


class LLMError(RuntimeError):
    """模型调用失败的统一异常。"""


class LLMClient:
    """基于 LiteLLM 的模型客户端。

    一个实例持有一份配置；按别名解析出具体模型与参数后调用 LiteLLM。
    """

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or get_config()
        self._apply_global_litellm_settings()

    def _apply_global_litellm_settings(self) -> None:
        settings = self._config.models.litellm
        # drop_params: 丢弃目标模型不支持的参数，避免因兼容性报错
        litellm.drop_params = settings.drop_params
        litellm.set_verbose = settings.verbose

    def _build_call_kwargs(
        self,
        entry: ModelEntry,
        messages: List[Message],
        *,
        temperature: Optional[float],
        max_tokens: Optional[int],
        extra: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        provider = self._config.models.providers.get(entry.provider)
        if provider is None:
            raise LLMError(f"模型 '{entry.litellm_model}' 引用了未定义的供应商 '{entry.provider}'")

        call_kwargs: Dict[str, Any] = {
            "model": entry.litellm_model,
            "messages": messages,
            "api_key": provider.api_key,
            "api_base": provider.api_base,
            "temperature": (entry.temperature if temperature is None else temperature),
            "max_tokens": entry.max_tokens if max_tokens is None else max_tokens,
            "timeout": entry.timeout_seconds,
            "num_retries": self._config.models.litellm.num_retries,
        }
        if extra:
            call_kwargs.update(extra)
        return call_kwargs

    def _log_request(self, entry: ModelEntry, messages: List[Message]) -> None:
        if self._config.observability.log_prompts:
            logger.info("LLM 调用 model=%s messages=%s", entry.litellm_model, messages)
        else:
            logger.info(
                "LLM 调用 model=%s messages=%d 条（内容已省略）",
                entry.litellm_model,
                len(messages),
            )

    def complete(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """返回模型生成的纯文本内容。"""
        entry = self._config.models.resolve(model)
        self._log_request(entry, messages)
        call_kwargs = self._build_call_kwargs(
            entry,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra=extra,
        )
        try:
            response = litellm.completion(**call_kwargs)
        except Exception as exc:  # LiteLLM 会抛多种底层异常，统一收敛
            raise LLMError(f"模型调用失败：{exc}") from exc

        try:
            return response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"模型响应结构异常：{exc}") from exc

    def complete_json(
        self,
        messages: List[Message],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """要求模型返回 JSON 对象，解析为 dict。

        用于意图分类、结构化抽取等需要机器可读输出的场景。
        """
        extra = {"response_format": {"type": "json_object"}}
        raw = self.complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            extra=extra,
        )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError(f"模型未返回合法 JSON：{raw[:200]}") from exc
        if not isinstance(parsed, dict):
            raise LLMError("模型返回的 JSON 顶层不是对象")
        return parsed


_shared_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """进程内共享的 LLMClient 单例。"""
    global _shared_client
    if _shared_client is None:
        _shared_client = LLMClient()
    return _shared_client
