from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "skills"
    / "akshare-fund-advisor"
    / "scripts"
    / "audit_quality_interfaces.py"
)
SPEC = importlib.util.spec_from_file_location(
    "audit_quality_interfaces",
    SCRIPT_PATH,
)
audit_quality_interfaces = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit_quality_interfaces
SPEC.loader.exec_module(audit_quality_interfaces)


def test_candidate_inventory_has_three_groups_and_unique_interfaces() -> None:
    candidates = audit_quality_interfaces.candidate_interfaces()
    names = [item.interface for item in candidates]

    assert len(candidates) == 24
    assert len(names) == len(set(names))
    assert {item.group for item in candidates} == {
        "stock_financial",
        "industry",
        "fund_quality",
    }


def test_audit_dataframe_records_dates_quality_and_fingerprint() -> None:
    candidate = next(
        item
        for item in audit_quality_interfaces.candidate_interfaces()
        if item.interface == "fund_open_fund_rank_em"
    )
    frame = pd.DataFrame(
        {
            "基金代码": ["000001", "000002"],
            "基金简称": ["示例一", "示例二"],
            "日期": ["2026-08-04", "2026-08-05"],
            "近1年": [1.0, None],
            "近2年": [2.0, None],
            "近3年": [3.0, None],
            "手续费": ["1%", "1%"],
        }
    )

    result = audit_quality_interfaces.audit_dataframe(
        candidate,
        frame,
        arguments={"symbol": "全部"},
        as_of=date(2026, 8, 4),
        duration_seconds=0.1,
        attempts=1,
        source_module="fake",
    )

    assert result["status"] == "passed"
    assert result["date_coverage"]["日期"]["future_rows"] == 1
    assert result["quality"]["unique_codes"] == 2
    assert result["quality"]["missing_return_rows"]["近1年"] == 1
    assert len(result["frame_sha256"]) == 64


def test_audit_dataframe_rejects_missing_required_columns() -> None:
    candidate = next(
        item
        for item in audit_quality_interfaces.candidate_interfaces()
        if item.interface == "stock_yjbb_em"
    )

    with pytest.raises(
        audit_quality_interfaces.AuditContractError,
        match="missing required columns",
    ):
        audit_quality_interfaces.audit_dataframe(
            candidate,
            pd.DataFrame({"股票代码": ["600519"]}),
            arguments={"date": "20251231"},
            as_of=date(2026, 8, 4),
            duration_seconds=0.1,
            attempts=1,
            source_module="fake",
        )
