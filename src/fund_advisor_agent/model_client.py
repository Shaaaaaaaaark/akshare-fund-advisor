"""Optional OpenAI-compatible structured association client."""

from __future__ import annotations

import json
from typing import Protocol

from fund_advisor_mcp.config import ModelConfig

from .associations import AssociationModel, RuleBasedAssociationModel
from .prompts import (
    ASSOCIATION_PROMPT_VERSION,
    ASSOCIATION_SYSTEM_PROMPT,
    INTENT_PROMPT_VERSION,
    INTENT_SYSTEM_PROMPT,
)
from .state import (
    AssociationBatch,
    AssociationDraft,
    FactRef,
    IntentDecision,
)


class IntentClassifier(Protocol):
    async def classify(self, question: str) -> IntentDecision: ...


class OpenAIAssociationModel:
    def __init__(self, config: ModelConfig) -> None:
        from openai import AsyncOpenAI

        self._config = config
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.resolved_base_url,
            timeout=config.timeout_seconds,
        )

    async def build_associations(
        self,
        facts: list[FactRef],
        question: str,
    ) -> list[AssociationDraft]:
        payload = [
            {
                "fact_id": fact.fact_id,
                "tool": fact.tool.value,
                "field_path": fact.field_path,
                "label": fact.label,
                "value": fact.value,
                "unit": fact.unit,
                "as_of": fact.as_of,
                "source_kind": fact.source_kind,
            }
            for fact in facts
        ]
        completion = await self._client.beta.chat.completions.parse(
            model=self._config.model,
            temperature=self._config.temperature,
            max_tokens=self._config.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{ASSOCIATION_SYSTEM_PROMPT}\n"
                        f"prompt_version={ASSOCIATION_PROMPT_VERSION}"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "facts": payload},
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format=AssociationBatch,
            **_extra_request_options(self._config),
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("模型未返回结构化关联说明")
        return parsed.associations


class OpenAIIntentClassifier:
    def __init__(self, config: ModelConfig) -> None:
        from openai import AsyncOpenAI

        self._config = config
        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.resolved_base_url,
            timeout=config.timeout_seconds,
        )

    async def classify(self, question: str) -> IntentDecision:
        completion = await self._client.beta.chat.completions.parse(
            model=self._config.model,
            temperature=0,
            max_tokens=min(self._config.max_tokens, 500),
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{INTENT_SYSTEM_PROMPT}\n"
                        f"prompt_version={INTENT_PROMPT_VERSION}"
                    ),
                },
                {"role": "user", "content": question},
            ],
            response_format=IntentDecision,
            **_extra_request_options(self._config),
        )
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise RuntimeError("模型未返回结构化意图")
        return parsed


def build_association_model(config: ModelConfig) -> AssociationModel:
    if config.enabled and config.api_key and config.model:
        return OpenAIAssociationModel(config)
    return RuleBasedAssociationModel()


def build_intent_classifier(
    config: ModelConfig,
    *,
    enabled: bool,
) -> IntentClassifier | None:
    if enabled and config.enabled and config.api_key and config.model:
        return OpenAIIntentClassifier(config)
    return None


def _extra_request_options(config: ModelConfig) -> dict[str, object]:
    if not config.extra_body:
        return {}
    return {"extra_body": config.extra_body}
