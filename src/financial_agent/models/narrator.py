"""LLM narration constrained to an already validated structured report."""

from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, ConfigDict, Field

from financial_agent.config import AppConfig, get_config
from financial_agent.evidence.models import ResearchReport
from financial_agent.prompts import (
    REPORT_NARRATOR_PROMPT_VERSION,
    REPORT_NARRATOR_SYSTEM_PROMPT,
)

from .client import LLMClient, get_llm_client
from .messages import system, user

PROMPT_VERSION = REPORT_NARRATOR_PROMPT_VERSION


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
                system(REPORT_NARRATOR_SYSTEM_PROMPT),
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
