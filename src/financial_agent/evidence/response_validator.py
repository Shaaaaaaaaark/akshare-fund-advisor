"""Final response validation before a report leaves the API boundary."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .models import EvidenceRecord, ResearchReport

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?%?")
_FORBIDDEN_EXPRESSIONS = {
    "稳赚",
    "必涨",
    "必买",
    "必卖",
    "无风险",
    "保证收益",
    "抄底",
    "逃顶",
}


class ResponseValidationError(ValueError):
    pass


class ResponseValidator:
    def validate(
        self,
        report: ResearchReport,
        evidence: Sequence[EvidenceRecord],
    ) -> None:
        evidence_map = {item.evidence_id: item for item in evidence}
        allowed_number_tokens: set[str] = set()

        for fact in report.facts:
            record = evidence_map.get(fact.evidence_id)
            if record is None:
                raise ResponseValidationError(
                    f"报告事实引用了不存在的 Evidence：{fact.evidence_id}"
                )
            if fact.value != record.value:
                raise ResponseValidationError(f"报告事实改写了 Evidence 值：{record.field}")
            if fact.display_value != (record.display_value or str(record.value)):
                raise ResponseValidationError(f"报告展示值与 Evidence 不一致：{record.field}")
            if isinstance(fact.value, (int, float)) and not isinstance(fact.value, bool):
                if not record.numeric_allowed:
                    raise ResponseValidationError(f"未授权数值进入报告：{record.field}")
            allowed_number_tokens.update(_NUMBER_RE.findall(fact.display_value))

        for citation in report.citations:
            record = evidence_map.get(citation.evidence_id)
            if record is None or record.metadata.get("url") != citation.url:
                raise ResponseValidationError("Citation 无法反查对应文档 Evidence")

        claim_text = "\n".join(
            [
                report.summary,
                *report.analysis,
                *report.buy_conditions,
                *report.sell_or_rebalance_conditions,
                *report.risks,
            ]
        )
        unexpected = set(_NUMBER_RE.findall(claim_text)) - allowed_number_tokens
        if unexpected:
            raise ResponseValidationError(
                f"报告正文出现未由 Evidence 渲染的数字：{sorted(unexpected)}"
            )

        normalized = claim_text.lower()
        forbidden = sorted(item for item in _FORBIDDEN_EXPRESSIONS if item in normalized)
        if forbidden:
            raise ResponseValidationError(f"报告包含禁止的确定性投资表达：{forbidden}")

        if report.evidence_grade in {"D", "E"} and report.facts:
            raise ResponseValidationError("证据等级 D/E 的报告不得包含金融事实")


def collect_report_evidence_ids(report: ResearchReport) -> set[Any]:
    return {
        *[item.evidence_id for item in report.facts],
        *[item.evidence_id for item in report.citations],
    }
