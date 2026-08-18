#!/usr/bin/env python3
"""Audit optional cross-validation providers with representative live calls."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd
from source_validation import (
    BaostockProvider,
    EFinanceProvider,
    ProviderFrame,
)


def audit_call(
    provider: str,
    label: str,
    function: Callable[[], ProviderFrame],
) -> dict[str, Any]:
    try:
        result = function()
        dates = (
            pd.Series(
                pd.to_datetime(result.frame["date"], errors="coerce")
            ).dropna()
            if "date" in result.frame
            else pd.Series(dtype="datetime64[ns]")
        )
        return {
            "provider": provider,
            "label": label,
            "status": "passed",
            "interface": result.interface,
            "provider_version": result.provider_version,
            "parameters": result.parameters,
            "metric_basis": result.metric_basis,
            "row_count": len(result.frame),
            "columns": list(result.columns),
            "start_date": (
                dates.min().date().isoformat() if not dates.empty else None
            ),
            "latest_date": result.as_of,
            "frame_sha256": result.frame_sha256,
        }
    except Exception as exc:
        return {
            "provider": provider,
            "label": label,
            "status": "failed",
            "error": {
                "code": getattr(exc, "code", "SOURCE_UNAVAILABLE"),
                "message": str(exc),
                "details": getattr(exc, "details", {}),
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="审计 Baostock/efinance 免费数据源的接口与字段"
    )
    parser.add_argument(
        "--providers",
        default="baostock",
        help="逗号分隔：baostock,efinance；efinance 不随默认环境安装",
    )
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    args = parser.parse_args()

    selected = {
        item.strip().lower()
        for item in args.providers.split(",")
        if item.strip()
    }
    unknown = selected - {"baostock", "efinance"}
    if unknown:
        parser.error(f"未知 Provider：{sorted(unknown)}")

    end = date.today()
    start = end - timedelta(days=max(args.days, 10))
    start_text = start.isoformat()
    end_text = end.isoformat()
    results: list[dict[str, Any]] = []

    if "baostock" in selected:
        baostock_provider = BaostockProvider(
            timeout_seconds=args.timeout_seconds
        )
        for code in ("600519", "000001", "300750", "510300", "159915"):
            results.append(
                audit_call(
                    "baostock",
                    code,
                    lambda code=code: baostock_provider.fetch_stock_daily(
                        code=code,
                        start_date=start_text,
                        end_date=end_text,
                        adjustment="none",
                    ),
                )
            )
        for name, qualified_code in (
            ("沪深300", "sh.000300"),
            ("中证500", "sh.000905"),
            ("创业板50", "sz.399673"),
        ):
            results.append(
                audit_call(
                    "baostock",
                    f"index:{name}",
                    lambda qualified_code=qualified_code: (
                        baostock_provider.fetch_index_daily(
                            qualified_code=qualified_code,
                            start_date=start_text,
                            end_date=end_text,
                        )
                    ),
                )
            )

    if "efinance" in selected:
        efinance_provider = EFinanceProvider(
            timeout_seconds=args.timeout_seconds
        )
        for code in ("600519", "000001", "300750", "510300", "159915"):
            results.append(
                audit_call(
                    "efinance",
                    code,
                    lambda code=code: efinance_provider.fetch_stock_daily(
                        code=code,
                        start_date=start_text,
                        end_date=end_text,
                        adjustment="none",
                    ),
                )
            )
        for code in ("000001", "110022"):
            results.append(
                audit_call(
                    "efinance",
                    f"fund:{code}",
                    lambda code=code: efinance_provider.fetch_fund_nav(
                        code=code,
                        limit=20,
                    ),
                )
            )

    payload = {
        "queried_on": end.isoformat(),
        "providers": sorted(selected),
        "results": results,
        "summary": {
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
        },
        "policy": {
            "audit_only": True,
            "automatic_source_override": False,
            "ai_may_generate_market_data": False,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["summary"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
