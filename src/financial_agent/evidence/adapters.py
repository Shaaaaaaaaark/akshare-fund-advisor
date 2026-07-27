"""Adapters that turn tool and document results into typed Evidence records."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from financial_agent.mcp_server.schemas import ToolEnvelope

from .models import (
    Confidence,
    EvidenceRecord,
    EvidenceSubject,
    EvidenceType,
    Freshness,
)

_SKIP_FIELDS = {
    "chart_series",
    "reference_lines",
    "window_statistics",
    "interpretation_priority",
    "limitations",
    "metric_guide",
}
_DERIVED_MARKERS = {
    "metrics",
    "summary",
    "charts",
    "derived",
    "index_valuation",
    "market_snapshot.premium_rate_pct",
}
_CURRENT_NUMERIC_MARKERS = {
    "latest_value",
    "current",
    "percentile",
    "drawdown",
    "volatility",
    "return",
    "yield",
    "premium",
    "price",
    "iopv",
    "weight",
    "fee",
    "observations",
    "count",
}
_PROMPT_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?previous|system\s+prompt|忽略(以上|之前|系统)"
    r"|泄露.*提示词|调用.*工具|执行.*命令)",
    re.IGNORECASE,
)


def _subject_from_data(data: dict[str, Any]) -> EvidenceSubject:
    if isinstance(data.get("index"), dict):
        item = data["index"]
        return EvidenceSubject(
            type="index",
            id=str(item.get("index_code") or item.get("qualified_code") or item.get("name")),
            name=item.get("name"),
        )
    if isinstance(data.get("fund"), dict):
        item = data["fund"]
        return EvidenceSubject(
            type="fund",
            id=str(item.get("code") or item.get("name")),
            name=item.get("name"),
        )
    if isinstance(data.get("stock"), dict):
        item = data["stock"]
        return EvidenceSubject(
            type="stock",
            id=str(item.get("code") or item.get("name")),
            name=item.get("name"),
        )
    return EvidenceSubject(
        type="query",
        id=str(data.get("query") or data.get("action") or "unknown"),
    )


def _parse_date(value: Any) -> date | datetime | None:
    if isinstance(value, (date, datetime)):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    try:
        if "T" in normalized:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return date.fromisoformat(normalized[:10])
    except ValueError:
        return None


def _unit_for_path(path: str) -> str | None:
    lowered = path.lower()
    if lowered.endswith("_pct") or "percentile" in lowered or "ratio_pct" in lowered:
        return "percent"
    if any(name in lowered for name in ("pe_ttm", ".pb", "price", "nav", "iopv")):
        return "value"
    if lowered.endswith("_days"):
        return "days"
    if lowered.endswith("_years"):
        return "years"
    return None


def _display_value(value: Any, unit: str | None) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float, Decimal)):
        text = f"{value:g}" if isinstance(value, (int, float)) else format(value, "f")
        return f"{text}%" if unit == "percent" else text
    return str(value)


def _iter_scalars(
    value: Any,
    path: str = "",
    inherited_date: date | datetime | None = None,
) -> Iterable[tuple[str, Any, date | datetime | None]]:
    if isinstance(value, dict):
        local_date = inherited_date
        for key in ("latest_date", "as_of", "data_date", "report_date"):
            parsed = _parse_date(value.get(key))
            if parsed is not None:
                local_date = parsed
                break
        for key, item in value.items():
            if key in _SKIP_FIELDS:
                continue
            child_path = f"{path}.{key}" if path else str(key)
            yield from _iter_scalars(item, child_path, local_date)
        return
    if isinstance(value, list):
        if len(value) > 20:
            return
        for index, item in enumerate(value):
            yield from _iter_scalars(item, f"{path}[{index}]", inherited_date)
        return
    if value is not None and isinstance(value, (str, int, float, bool, Decimal, date, datetime)):
        yield path, value, inherited_date


def _is_derived(path: str) -> bool:
    return any(marker in path for marker in _DERIVED_MARKERS)


def _is_financial_numeric(path: str, value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    lowered = path.lower()
    return any(marker in lowered for marker in _CURRENT_NUMERIC_MARKERS)


def tool_envelope_to_evidence(
    envelope: ToolEnvelope,
    task_id: UUID,
) -> list[EvidenceRecord]:
    """Convert a successful ToolEnvelope without changing any source value."""
    if not envelope.ok or envelope.data is None:
        return []

    passed_audits = [item for item in envelope.data_audit if item.get("validation") == "passed"]
    audit_hashes = sorted(
        {str(item["frame_sha256"]) for item in passed_audits if item.get("frame_sha256")}
    )
    audit_ref = ",".join(audit_hashes) or None
    policy_valid = envelope.data_policy.get("ai_may_generate_market_data") is False
    audit_valid = bool(passed_audits) and bool(audit_hashes) and policy_valid
    subject = _subject_from_data(envelope.data)
    records: list[EvidenceRecord] = []

    for field, value, as_of in _iter_scalars(envelope.data):
        if not field or field.endswith("latest_age_days"):
            continue
        unit = _unit_for_path(field)
        is_numeric = _is_financial_numeric(field, value)
        latest_age = _find_latest_age(envelope.data, field)
        freshness = Freshness.UNKNOWN
        if latest_age is not None:
            freshness = Freshness.VALID if 0 <= latest_age <= 10 else Freshness.STALE
        elif audit_valid:
            freshness = Freshness.VALID

        records.append(
            EvidenceRecord(
                task_id=task_id,
                type=(
                    EvidenceType.DERIVED_METRIC if _is_derived(field) else EvidenceType.TOOL_FACT
                ),
                subject=subject,
                field=field,
                value=value,
                display_value=_display_value(value, unit),
                unit=unit,
                as_of=as_of,
                source_ref=str(envelope.request_id),
                audit_ref=audit_ref,
                freshness=freshness,
                confidence=Confidence.HIGH if audit_valid else Confidence.LOW,
                numeric_allowed=bool(is_numeric and audit_valid and freshness != Freshness.STALE),
                metadata={
                    "tool": envelope.tool.value,
                    "schema_version": envelope.schema_version,
                    "market_data_policy_valid": policy_valid,
                },
            )
        )
    return records


def _find_latest_age(data: dict[str, Any], field: str) -> int | None:
    """Best-effort lookup of latest_age_days in the scalar's nearest parent."""
    clean_parts = [re.sub(r"\[\d+\]$", "", item) for item in field.split(".")]
    cursor: Any = data
    nearest: int | None = None
    for part in clean_parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            break
        cursor = cursor[part]
        if isinstance(cursor, dict):
            candidate = cursor.get("latest_age_days")
            if isinstance(candidate, int):
                nearest = candidate
    return nearest


def document_hit_to_evidence(
    *,
    task_id: UUID,
    subject: EvidenceSubject,
    text: str,
    source_ref: str,
    title: str,
    url: str,
    page: int | None,
    version: str | None,
    channel: str,
) -> EvidenceRecord:
    prompt_injection = bool(_PROMPT_INJECTION_RE.search(text))
    confidence = Confidence.LOW if channel == "web" or prompt_injection else Confidence.HIGH
    return EvidenceRecord(
        task_id=task_id,
        type=EvidenceType.DOCUMENT_FACT,
        subject=subject,
        field="document_excerpt",
        value=text,
        display_value=text,
        source_ref=source_ref,
        freshness=Freshness.UNKNOWN,
        confidence=confidence,
        numeric_allowed=False,
        metadata={
            "title": title,
            "url": url,
            "page": page,
            "version": version,
            "channel": channel,
            "prompt_injection_detected": prompt_injection,
        },
    )
