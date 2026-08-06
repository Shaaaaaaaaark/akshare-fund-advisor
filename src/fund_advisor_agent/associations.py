"""Rule-based and optional model-backed association builders."""

from __future__ import annotations

from typing import Protocol

from .state import (
    AssociationDraft,
    Confidence,
    FactRef,
    Relationship,
)


class AssociationModel(Protocol):
    async def build_associations(
        self,
        facts: list[FactRef],
        question: str,
    ) -> list[AssociationDraft]: ...


class RuleBasedAssociationModel:
    async def build_associations(
        self,
        facts: list[FactRef],
        question: str,
    ) -> list[AssociationDraft]:
        del question
        pairs = (
            (
                ".summary.pe_ttm.percentile",
                ".summary.pb.percentile",
                Relationship.CONTRAST,
                "PE 与 PB 反映不同估值口径，应分别观察其历史位置。",
            ),
            (
                ".analysis.performance.annualized_volatility_pct",
                ".analysis.performance.max_drawdown_pct",
                Relationship.CONSISTENCY,
                "历史波动与历史回撤是互补的风险特征，应结合观察。",
            ),
            (
                ".summary.stock_price.current",
                ".summary.pe_ttm.percentile",
                Relationship.CO_OCCURRENCE,
                "价格位置与盈利估值位置同时可见，但不能据此推断后续涨跌。",
            ),
        )
        for left_suffix, right_suffix, relationship, explanation in pairs:
            left = _find_fact(facts, left_suffix)
            right = _find_fact(facts, right_suffix)
            if left is not None and right is not None:
                return [
                    AssociationDraft(
                        evidence_refs=[left.fact_id, right.fact_id],
                        relationship=relationship,
                        explanation=explanation,
                        confidence=_confidence(left, right),
                    )
                ]

        numeric = [
            fact
            for fact in facts
            if fact.source_kind == "market"
            and isinstance(fact.value, (int, float))
            and not isinstance(fact.value, bool)
        ]
        if len(numeric) < 2:
            return []
        return [
            AssociationDraft(
                evidence_refs=[numeric[0].fact_id, numeric[1].fact_id],
                relationship=Relationship.CO_OCCURRENCE,
                explanation="这两项已审计事实可结合观察，但不能据此证明因果关系。",
                confidence=_confidence(numeric[0], numeric[1]),
            )
        ]


def _find_fact(facts: list[FactRef], suffix: str) -> FactRef | None:
    return next(
        (fact for fact in facts if fact.field_path.endswith(suffix)),
        None,
    )


def _confidence(left: FactRef, right: FactRef) -> Confidence:
    if left.audit_ref and right.audit_ref and left.as_of and right.as_of:
        return Confidence.HIGH
    if left.audit_ref and right.audit_ref:
        return Confidence.MEDIUM
    return Confidence.LOW
