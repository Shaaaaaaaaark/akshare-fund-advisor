"""Deterministic Claim construction from gated Evidence."""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from .models import (
    ClaimRecord,
    ClaimType,
    EvidenceRecord,
    EvidenceType,
    GateDecision,
)

_FIELD_PRIORITY = (
    "document_excerpt",
    "summary.pe_ttm.current",
    "summary.pe_ttm.percentile",
    "summary.pe_ttm.level",
    "summary.pb.current",
    "summary.pb.percentile",
    "summary.pb.level",
    "summary.stock_price.current",
    "metrics.latest_value",
    "metrics.returns_pct.12_month",
    "metrics.current_drawdown_pct",
    "metrics.max_drawdown_pct",
    "metrics.annualized_volatility_pct",
    "metrics.history_position_percentile",
    "market_snapshot.premium_rate_pct",
    "availability.off_exchange.subscription_status",
    "availability.off_exchange.redemption_status",
    "availability.exchange.standard_market_open_now",
    "availability.latest_nav_or_income",
    "count",
    "fund.code",
    "fund.name",
    "stock.code",
    "stock.name",
    "index.index_code",
    "index.name",
)


def _priority(field: str) -> tuple[int, str]:
    try:
        return _FIELD_PRIORITY.index(field), field
    except ValueError:
        return len(_FIELD_PRIORITY), field


def build_claims(
    task_id: UUID,
    evidence: Sequence[EvidenceRecord],
    decision: GateDecision,
    *,
    maximum: int = 20,
) -> list[ClaimRecord]:
    blocked = set(decision.blocked_evidence_ids)
    candidates = [
        item
        for item in evidence
        if item.evidence_id not in blocked and (item.numeric_allowed or _is_reportable_scalar(item))
    ]
    candidates.sort(key=lambda item: _priority(item.field))
    if candidates and all(item.type == EvidenceType.DOCUMENT_FACT for item in candidates):
        candidates = candidates[: min(maximum, 5)]

    claims: list[ClaimRecord] = []
    for item in candidates[:maximum]:
        claim_type = (
            ClaimType.DERIVED if item.type == EvidenceType.DERIVED_METRIC else ClaimType.FACT
        )
        allowed = claim_type in decision.allowed_claim_types
        claims.append(
            ClaimRecord(
                task_id=task_id,
                claim_type=claim_type,
                template_id="evidence_fact",
                arguments={"value": item.evidence_id},
                evidence_ids=[item.evidence_id],
                allowed=allowed,
                rejection_reasons=[] if allowed else ["证据门禁不允许该 Claim 类型"],
            )
        )
    return claims


def _is_reportable_scalar(item: EvidenceRecord) -> bool:
    if item.type == EvidenceType.DOCUMENT_FACT:
        return (
            item.field == "document_excerpt"
            and item.metadata.get("channel") != "web"
            and not item.metadata.get("prompt_injection_detected")
        )
    if item.type not in {EvidenceType.TOOL_FACT, EvidenceType.DERIVED_METRIC}:
        return False
    field = item.field
    if field in {
        "fund.code",
        "fund.name",
        "stock.code",
        "stock.name",
        "index.index_code",
        "index.name",
        "availability.mode",
        "availability.source_report_date",
        "availability.off_exchange.subscription_status",
        "availability.off_exchange.redemption_status",
        "availability.off_exchange.can_submit_subscription",
        "availability.off_exchange.can_submit_redemption",
        "availability.exchange.standard_market_open_now",
        "availability.exchange.can_submit_standard_session_order",
    }:
        return True
    return bool(
        re.fullmatch(
            r"results\[\d+\]\.(code|name|type)",
            field,
        )
        or re.fullmatch(
            r"results\[\d+\]\.fund\.(code|name|type)",
            field,
        )
    )
