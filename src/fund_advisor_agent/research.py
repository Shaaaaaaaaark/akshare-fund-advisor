"""Research synthesis protocol and deterministic fallback."""

from __future__ import annotations

from typing import Protocol

from .associations import build_rule_based_associations
from .state import (
    FactRef,
    ResearchNextStep,
    ResearchQuestion,
    ResearchSynthesis,
)


class ResearchModel(Protocol):
    async def build_research(
        self,
        facts: list[FactRef],
        question: str,
    ) -> ResearchSynthesis: ...


class RuleBasedResearchModel:
    async def build_research(
        self,
        facts: list[FactRef],
        question: str,
    ) -> ResearchSynthesis:
        del question
        return ResearchSynthesis(
            research_questions=[
                ResearchQuestion(
                    question_id="rq_primary",
                    question="现有事实反映了哪些风险、估值差异和数据限制？",
                )
            ],
            associations=build_rule_based_associations(facts),
            next_steps=[
                ResearchNextStep(
                    question_id="rq_primary",
                    action="核对当前未覆盖的数据和来源限制。",
                    reason="现有结论仅基于已返回并通过校验的事实。",
                )
            ],
        )
