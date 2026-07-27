"""Best-effort Elasticsearch projections for audit and report search."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from elasticsearch import Elasticsearch

from financial_agent.config import AppConfig, get_config


class ElasticsearchAuditProjection:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        url = self._config.observability.elasticsearch_url
        self._client = Elasticsearch(url) if url else None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def index_task(self, state: dict[str, Any]) -> None:
        if self._client is None:
            return
        self._ensure_indexes()
        task_id = str(state["task_id"])
        tool_calls = [
            {
                "request_id": item.get("request_id"),
                "tool": item.get("tool"),
                "ok": item.get("ok"),
                "audit_refs": [
                    audit.get("frame_sha256")
                    for audit in item.get("data_audit", [])
                    if audit.get("frame_sha256")
                ],
                "error_code": (item.get("error") or {}).get("code"),
            }
            for item in state.get("tool_results", [])
        ]
        evidence_refs = [
            {
                "evidence_id": item.get("evidence_id"),
                "type": item.get("type"),
                "subject_type": (item.get("subject") or {}).get("type"),
                "subject_id": (item.get("subject") or {}).get("id"),
                "field": item.get("field"),
                "source_ref": item.get("source_ref"),
                "audit_ref": item.get("audit_ref"),
                "freshness": item.get("freshness"),
            }
            for item in state.get("evidence", [])
        ]
        self._client.index(
            index=self._config.observability.audit_index,
            id=task_id,
            document={
                "task_id": task_id,
                "conversation_id": state.get("conversation_id"),
                "trace_id": state.get("trace_id"),
                "status": state.get("status"),
                "intent": state.get("intent"),
                "evidence_grade": (state.get("gate_decision") or {}).get("grade"),
                "tool_calls": tool_calls,
                "evidence_refs": evidence_refs,
                "errors": state.get("errors", []),
                "indexed_at": datetime.now(timezone.utc),
            },
        )
        report = state.get("final_report") or None
        if report:
            self._client.index(
                index=self._config.observability.report_index,
                id=str(report["report_id"]),
                document={
                    "report_id": report["report_id"],
                    "task_id": task_id,
                    "trace_id": state.get("trace_id"),
                    "title": report.get("title"),
                    "summary": report.get("summary"),
                    "analysis": report.get("analysis", []),
                    "warnings": report.get("warnings", []),
                    "evidence_grade": report.get("evidence_grade"),
                    "generated_at": report.get("generated_at"),
                },
            )

    def _ensure_indexes(self) -> None:
        if self._client is None:
            return
        for index in (
            self._config.observability.audit_index,
            self._config.observability.report_index,
        ):
            if not self._client.indices.exists(index=index):
                self._client.indices.create(index=index)
