from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from financial_agent.config import AppConfig, get_config
from financial_agent.mcp_server.schemas import ToolEnvelope, ToolName

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeFundToolClient:
    def __init__(
        self,
        *,
        error_code: str | None = None,
        error_details: dict[str, Any] | None = None,
    ) -> None:
        self.error_code = error_code
        self.error_details = error_details or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, arguments: dict[str, Any]) -> ToolEnvelope:
        from financial_agent.mcp_server.schemas import ToolError

        self.calls.append((tool, arguments))
        if self.error_code:
            return ToolEnvelope(
                tool=ToolName(tool),
                ok=False,
                queried_at=datetime.now(SHANGHAI),
                data_policy={"ai_may_generate_market_data": False},
                error=ToolError(
                    code=self.error_code,
                    message="fake tool error",
                    details=self.error_details,
                ),
            )
        return valuation_envelope(tool)

    async def healthcheck(self) -> bool:
        return True


def valuation_envelope(tool: str = "index_valuation") -> ToolEnvelope:
    return ToolEnvelope(
        tool=ToolName(tool),
        ok=True,
        queried_at=datetime.now(SHANGHAI),
        data={
            "ok": True,
            "action": "valuation",
            "index": {"name": "沪深300", "index_code": "000300"},
            "summary": {
                "pe_ttm": {
                    "current": 12.3,
                    "percentile": 31.2,
                    "level": "lower_middle",
                },
                "pb": {
                    "current": 1.2,
                    "percentile": 25.0,
                    "level": "lower_middle",
                },
            },
            "lookback": {
                "requested_years": 3,
                "actual_start_date": "2023-01-03",
                "latest_date": "2026-07-24",
            },
            "charts": {
                "pe_ttm": {
                    "metric": "PE_TTM",
                    "unit": "倍",
                    "current": 12.3,
                    "percentile": 31.2,
                    "level": "lower_middle",
                    "mean": 13.0,
                    "median": 12.8,
                    "latest_date": "2026-07-24",
                    "actual_start_date": "2023-01-03",
                    "source_observations": 600,
                    "chart_series": [
                        ["2023-01-03", 11.2],
                        ["2026-07-24", 12.3],
                    ],
                    "reference_lines": {
                        "p20": 10.5,
                        "p80": 15.6,
                        "mean": 13.0,
                        "median": 12.8,
                    },
                },
                "pb": {
                    "metric": "PB",
                    "unit": "倍",
                    "current": 1.2,
                    "percentile": 25.0,
                    "level": "lower_middle",
                    "mean": 1.4,
                    "median": 1.3,
                    "latest_date": "2026-07-24",
                    "actual_start_date": "2023-01-03",
                    "source_observations": 600,
                    "chart_series": [
                        ["2023-01-03", 1.1],
                        ["2026-07-24", 1.2],
                    ],
                    "reference_lines": {
                        "p20": 1.05,
                        "p80": 1.65,
                        "mean": 1.4,
                        "median": 1.3,
                    },
                },
                "index_points": {
                    "metric": "INDEX_POINTS",
                    "unit": "点",
                    "current": 4649.19,
                    "latest_date": "2026-07-24",
                    "actual_start_date": "2023-01-03",
                    "source_observations": 600,
                    "chart_series": [
                        ["2023-01-03", 3887.9],
                        ["2026-07-24", 4649.19],
                    ],
                },
            },
        },
        data_audit=[
            {
                "interface": "stock_index_pe_lg",
                "validation": "passed",
                "frame_sha256": "abc123",
            }
        ],
        data_policy={"ai_may_generate_market_data": False},
    )


@pytest.fixture
def test_config(tmp_path: Path) -> AppConfig:
    config = get_config()
    return config.model_copy(
        update={
            "storage": config.storage.model_copy(
                update={
                    "database_url": f"sqlite:///{tmp_path / 'agent.db'}",
                    "document_dir": str(tmp_path / "documents"),
                }
            ),
            "mcp": config.mcp.model_copy(update={"transport": "inprocess"}),
            "agent": config.agent.model_copy(
                update={
                    "use_llm_for_intent": False,
                    "use_llm_for_report": False,
                }
            ),
        }
    )
