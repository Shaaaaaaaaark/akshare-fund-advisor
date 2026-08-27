"""Shared fund-name catalogue lookup helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fund_advisor_data_core.audit import json_value, normalize_code
from fund_advisor_data_core.errors import DataCoreError


def fund_record(row: pd.Series) -> dict[str, Any]:
    return {
        "code": normalize_code(row.get("基金代码")),
        "name": json_value(row.get("基金简称")),
        "type": json_value(row.get("基金类型")),
        "pinyin_abbr": json_value(row.get("拼音缩写")),
    }


def search_candidates(
    names: pd.DataFrame,
    clean_query: str,
) -> list[tuple[int, dict[str, Any]]]:
    query_upper = clean_query.upper()
    query_code = normalize_code(clean_query)
    candidates: list[tuple[int, dict[str, Any]]] = []

    for _, row in names.iterrows():
        record = fund_record(row)
        code = record["code"]
        name = str(record["name"] or "")
        pinyin_abbr = str(record["pinyin_abbr"] or "").upper()
        pinyin_full = str(row.get("拼音全称") or "").upper()

        if query_code == code or clean_query == name:
            score = 0
        elif name.startswith(clean_query) or pinyin_abbr.startswith(query_upper):
            score = 1
        elif clean_query in name or query_upper in pinyin_abbr or query_upper in pinyin_full:
            score = 2
        else:
            continue
        candidates.append((score, record))

    candidates.sort(key=lambda item: (item[0], item[1]["code"]))
    return candidates


def resolve_fund(names: pd.DataFrame, query: str) -> dict[str, Any]:
    clean_query = query.strip()
    if not clean_query:
        raise DataCoreError("INVALID_ARGUMENT", "搜索词不能为空")
    candidates = search_candidates(names, clean_query)
    if not candidates:
        raise DataCoreError("FUND_NOT_FOUND", f"未找到基金：{query}", {"query": query})
    top_score = candidates[0][0]
    top_records = [record for score, record in candidates if score == top_score]
    if len(top_records) > 1:
        raise DataCoreError(
            "AMBIGUOUS_FUND",
            f"基金名称不唯一，请确认代码：{query}",
            {"candidates": top_records[:10]},
        )
    return top_records[0]
