from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from conftest import valuation_envelope

from financial_agent.domain import Intent
from financial_agent.evidence import (
    EvidenceGate,
    ResponseValidator,
    build_claims,
    render_report,
    tool_envelope_to_evidence,
)
from financial_agent.models.narrator import ReportNarrator
from financial_agent.prompts import REPORT_NARRATOR_SYSTEM_PROMPT

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeLLM:
    def __init__(self) -> None:
        self.messages = None

    def complete_json(self, messages, **_kwargs):
        self.messages = messages
        return {"analysis": ["PE 与 PB 应分别理解，历史位置不预测未来。"]}


@pytest.mark.asyncio
async def test_narrator_only_extends_analysis(test_config) -> None:
    task_id = uuid4()
    evidence = tool_envelope_to_evidence(valuation_envelope(), task_id)
    decision = EvidenceGate().evaluate(Intent.INDEX_VALUATION, evidence)
    report = render_report(
        task_id=task_id,
        intent=Intent.INDEX_VALUATION,
        evidence=evidence,
        claims=build_claims(task_id, evidence, decision),
        decision=decision,
        generated_at=datetime.now(SHANGHAI),
    )
    fake = FakeLLM()
    narrator = ReportNarrator(test_config, fake)

    enriched = await narrator.enrich(report)

    assert enriched.facts == report.facts
    assert len(enriched.analysis) == len(report.analysis) + 1
    ResponseValidator().validate(enriched, evidence)
    assert "average_cost" not in str(fake.messages)
    assert fake.messages[0] == {
        "role": "system",
        "content": REPORT_NARRATOR_SYSTEM_PROMPT,
    }
