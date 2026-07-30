from __future__ import annotations

import pytest

from financial_agent.domain import Intent
from financial_agent.orchestration import FinancialAgentGraph
from financial_agent.orchestration.intent import IntentClassifier
from financial_agent.prompts import (
    INTENT_CLASSIFIER_PROMPT_VERSION,
    INTENT_CLASSIFIER_SYSTEM_PROMPT,
    PROMPT_VERSIONS,
    REPORT_NARRATOR_PROMPT_VERSION,
    REPORT_NARRATOR_SYSTEM_PROMPT,
)


class FakeIntentLLM:
    def __init__(self) -> None:
        self.messages = None

    def complete_json(self, messages, **_kwargs):
        self.messages = messages
        return {
            "intent": "unsupported",
            "entities": [],
            "needs_clarification": True,
            "clarification_question": "请补充具体研究标的。",
            "confidence": 0.8,
        }


def test_prompt_catalog_has_versioned_financial_boundaries() -> None:
    assert PROMPT_VERSIONS["intent_classifier"] == INTENT_CLASSIFIER_PROMPT_VERSION
    assert PROMPT_VERSIONS["report_narrator"] == REPORT_NARRATOR_PROMPT_VERSION
    assert INTENT_CLASSIFIER_PROMPT_VERSION in INTENT_CLASSIFIER_SYSTEM_PROMPT
    assert REPORT_NARRATOR_PROMPT_VERSION in REPORT_NARRATOR_SYSTEM_PROMPT
    assert "候选" in INTENT_CLASSIFIER_SYSTEM_PROMPT
    assert "不得根据名称、代码格式" in INTENT_CLASSIFIER_SYSTEM_PROMPT
    assert "facts 是唯一可引用的金融事实集合" in REPORT_NARRATOR_SYSTEM_PROMPT
    assert "不得判断输入实体是否存在" in REPORT_NARRATOR_SYSTEM_PROMPT
    assert "PE 与 PB 必须分别解释" in REPORT_NARRATOR_SYSTEM_PROMPT
    assert FinancialAgentGraph.initial_state("测试")["prompt_versions"] == PROMPT_VERSIONS


@pytest.mark.asyncio
async def test_intent_classifier_uses_catalog_prompt(test_config) -> None:
    config = test_config.model_copy(
        update={
            "agent": test_config.agent.model_copy(
                update={"use_llm_for_intent": True}
            )
        }
    )
    fake = FakeIntentLLM()
    classifier = IntentClassifier(config, fake)

    decision = await classifier.classify("研究一个尚未说明的标的")

    assert decision.intent == Intent.UNSUPPORTED
    assert fake.messages[0] == {
        "role": "system",
        "content": INTENT_CLASSIFIER_SYSTEM_PROMPT,
    }
