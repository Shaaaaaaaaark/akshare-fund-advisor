"""Deterministic evidence gate.

The LLM never assigns an evidence grade. This module contains the versioned
business rules that decide whether report generation may continue.
"""

from __future__ import annotations

from collections.abc import Sequence

from financial_agent.domain import Intent

from .models import (
    ClaimType,
    EvidenceRecord,
    EvidenceType,
    Freshness,
    GateDecision,
)

GATE_POLICY_VERSION = "2026-07-01"

_DOCUMENT_RECOMMENDED = {
    Intent.FUND_ANALYSIS,
    Intent.DCA_REFERENCE,
    Intent.SELL_OR_REBALANCE,
    Intent.DOCUMENT_QA,
}


class EvidenceGate:
    def evaluate(
        self,
        intent: Intent,
        evidence: Sequence[EvidenceRecord],
        warnings: Sequence[str] = (),
        *,
        policy_violation: str | None = None,
    ) -> GateDecision:
        if policy_violation:
            return GateDecision(
                grade="E",
                warnings=list(warnings),
                reasons=[policy_violation],
                policy_version=GATE_POLICY_VERSION,
            )

        if not evidence:
            return GateDecision(
                grade="D",
                warnings=list(warnings),
                reasons=["没有可验证的 Evidence"],
                policy_version=GATE_POLICY_VERSION,
            )

        blocked = [
            item.evidence_id
            for item in evidence
            if item.freshness == Freshness.STALE
            or item.metadata.get("prompt_injection_detected") is True
            or (item.numeric_allowed and (not item.audit_ref or item.confidence.value == "low"))
        ]
        usable = [item for item in evidence if item.evidence_id not in blocked]
        usable_numeric = [
            item
            for item in usable
            if item.numeric_allowed
            and item.type in {EvidenceType.TOOL_FACT, EvidenceType.DERIVED_METRIC}
        ]
        tool_evidence = [
            item
            for item in usable
            if item.type in {EvidenceType.TOOL_FACT, EvidenceType.DERIVED_METRIC}
        ]
        document_evidence = [item for item in usable if item.type == EvidenceType.DOCUMENT_FACT]
        trusted_document_evidence = [
            item for item in document_evidence if item.metadata.get("channel") != "web"
        ]

        if not tool_evidence and intent != Intent.DOCUMENT_QA:
            return GateDecision(
                grade="D",
                blocked_evidence_ids=blocked,
                warnings=list(warnings),
                reasons=["缺少通过审计的工具事实"],
                policy_version=GATE_POLICY_VERSION,
            )
        if intent == Intent.DOCUMENT_QA and not trusted_document_evidence:
            return GateDecision(
                grade="D",
                blocked_evidence_ids=blocked,
                warnings=list(warnings),
                reasons=["没有通过安全检查的文档 Evidence"],
                policy_version=GATE_POLICY_VERSION,
            )
        if (
            intent
            in {
                Intent.FUND_ANALYSIS,
                Intent.INDEX_VALUATION,
                Intent.STOCK_VALUATION,
                Intent.DCA_REFERENCE,
                Intent.SELL_OR_REBALANCE,
            }
            and not usable_numeric
        ):
            return GateDecision(
                grade="D",
                blocked_evidence_ids=blocked,
                warnings=list(warnings),
                reasons=["缺少允许进入报告的金融数值 Evidence"],
                policy_version=GATE_POLICY_VERSION,
            )

        allowed = {
            ClaimType.FACT,
            ClaimType.DERIVED,
            ClaimType.INTERPRETATION,
            ClaimType.WARNING,
        }
        if warnings or blocked:
            return GateDecision(
                grade="C",
                allowed_claim_types=allowed,
                blocked_evidence_ids=blocked,
                warnings=list(warnings),
                reasons=["存在非关键数据告警，输出范围已收窄"],
                policy_version=GATE_POLICY_VERSION,
            )
        if intent in _DOCUMENT_RECOMMENDED and not trusted_document_evidence:
            return GateDecision(
                grade="B",
                allowed_claim_types=allowed,
                warnings=["未检索到产品官方文档，本次只使用工具事实。"],
                reasons=["文档证据缺失"],
                policy_version=GATE_POLICY_VERSION,
            )
        return GateDecision(
            grade="A",
            allowed_claim_types=allowed,
            policy_version=GATE_POLICY_VERSION,
        )
