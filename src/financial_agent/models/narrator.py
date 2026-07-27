"""LLM narration constrained to an already validated structured report."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, ConfigDict, Field

from financial_agent.config import AppConfig, get_config
from financial_agent.evidence.models import ResearchReport

from .client import LLMClient, get_llm_client
from .messages import system, user

PROMPT_VERSION = "report-narrator-2026-07-01"


class NarrationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis: list[str] = Field(default_factory=list, max_length=8)


class ReportNarrator:
    def __init__(
        self,
        config: AppConfig | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._client = client or get_llm_client()

    async def enrich(self, report: ResearchReport) -> ResearchReport:
        payload = {
            "title": report.title,
            "summary": report.summary,
            "facts": [
                {
                    "label": item.label,
                    "display_value": item.display_value,
                    "as_of": (item.as_of.isoformat() if item.as_of is not None else None),
                    "evidence_id": str(item.evidence_id),
                }
                for item in report.facts
            ],
            "evidence_grade": report.evidence_grade,
            "warnings": report.warnings,
        }
        raw = await asyncio.to_thread(
            self._client.complete_json,
            [
                system(
                    f"prompt_version={PROMPT_VERSION}\n"
                    "你是金融研究报告叙述器，只能解释输入 facts。"
                    "不得增加、改写、推算任何数字，不得预测涨跌，不得使用"
                    "必买、必卖、稳赚、抄底、逃顶等措辞。"
                    '只返回 JSON：{"analysis": ["..."]}。'
                ),
                user(json.dumps(payload, ensure_ascii=False)),
            ],
            model=self._config.models.report_alias(),
            temperature=0.1,
            max_tokens=800,
        )
        narration = NarrationOutput.model_validate(raw)
        return report.model_copy(
            update={
                "analysis": [
                    *report.analysis,
                    *narration.analysis,
                ][:8]
            }
        )
