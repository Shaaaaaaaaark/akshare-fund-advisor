"""Expose audited valuation series without leaking the full tool state."""

from __future__ import annotations

from typing import Any

from financial_agent.mcp_server.schemas import ToolEnvelope, ToolName


def valuation_chart_from_state(state: dict[str, Any]) -> dict[str, Any]:
    for raw in reversed(state.get("tool_results", [])):
        envelope = ToolEnvelope.model_validate(raw)
        if envelope.tool not in {
            ToolName.INDEX_VALUATION,
            ToolName.STOCK_VALUATION,
        }:
            continue
        if not _is_audited(envelope) or envelope.data is None:
            return {"available": False, "reason": "估值序列未通过数据审计"}
        data = envelope.data
        charts = data.get("charts") or {}
        metrics = {
            name: _chart_metric(charts.get(name), include_reference=True)
            for name in ("pe_ttm", "pb")
        }
        market_price = charts.get("index_points") or charts.get("stock_price")
        metrics["market_price"] = _chart_metric(
            market_price,
            include_reference=False,
        )
        metrics = {name: item for name, item in metrics.items() if item is not None}
        if not metrics:
            return {"available": False, "reason": "当前报告没有可展示的估值序列"}
        return {
            "available": True,
            "subject": data.get("index") or data.get("stock") or {},
            "subject_type": (
                "stock"
                if envelope.tool == ToolName.STOCK_VALUATION
                else "index"
            ),
            "lookback": data.get("lookback", {}),
            "metrics": metrics,
            "source": {
                "provider": (data.get("actual_source") or {}).get("provider"),
                "interfaces": (data.get("actual_source") or {}).get("interfaces", []),
                "audit_hashes": sorted(
                    {
                        str(item["frame_sha256"])
                        for item in envelope.data_audit
                        if item.get("validation") == "passed"
                        and item.get("frame_sha256")
                    }
                ),
            },
        }
    return {"available": False, "reason": "该报告不是指数估值报告"}


def _is_audited(envelope: ToolEnvelope) -> bool:
    return (
        envelope.ok
        and envelope.data_policy.get("ai_may_generate_market_data") is False
        and any(
            item.get("validation") == "passed" and item.get("frame_sha256")
            for item in envelope.data_audit
        )
    )


def _chart_metric(
    raw: Any,
    *,
    include_reference: bool,
) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    series = [
        [str(item[0]), float(item[1])]
        for item in raw.get("chart_series", [])
        if isinstance(item, list)
        and len(item) == 2
        and isinstance(item[1], (int, float))
    ][:3000]
    if not series:
        return None
    reference = raw.get("reference_lines") or {}
    payload = {
        "metric": raw.get("metric"),
        "unit": raw.get("unit"),
        "current": raw.get("current"),
        "percentile": raw.get("percentile"),
        "level": raw.get("level"),
        "mean": raw.get("mean"),
        "median": raw.get("median"),
        "minimum": raw.get("minimum"),
        "maximum": raw.get("maximum"),
        "latest_date": raw.get("latest_date"),
        "actual_start_date": raw.get("actual_start_date"),
        "source_observations": raw.get("source_observations"),
        "chart_series": series,
    }
    if include_reference:
        payload["reference_lines"] = {
            "opportunity": reference.get("p20"),
            "danger": reference.get("p80"),
            "mean": reference.get("mean"),
            "median": reference.get("median"),
        }
    return payload
