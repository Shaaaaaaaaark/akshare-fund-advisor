"""Shared helpers for source validation, auditing, and JSON-safe values."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Sequence
from zoneinfo import ZoneInfo

import pandas as pd

from .errors import DataCoreError

SHANGHAI = ZoneInfo("Asia/Shanghai")
PUBLIC_FUND_DOC = "https://akshare.akfamily.xyz/data/fund/fund_public.html"
SUPPORTED_AKSHARE_VERSION = "1.18.64"

INTERFACE_CONTRACTS: dict[str, set[str]] = {
    "fund_name_em": {
        "基金代码",
        "拼音缩写",
        "基金简称",
        "基金类型",
        "拼音全称",
    },
    "fund_purchase_em": {
        "基金代码",
        "基金简称",
        "基金类型",
        "最新净值/万份收益",
        "最新净值/万份收益-报告时间",
        "申购状态",
        "赎回状态",
        "下一开放日",
        "购买起点",
        "日累计限定金额",
        "手续费",
    },
}

DATA_POLICY: dict[str, Any] = {
    "ai_may_generate_market_data": False,
    "missing_data_policy": "返回 null、warning 或 error，禁止猜测、插值或补值",
    "source_fact_policy": "所有源数据必须带接口、参数、字段、行数和 SHA-256 指纹",
    "derived_metric_policy": "只允许脚本按已声明公式计算，模型不得改写数值",
    "policy_output": "买卖与定投规则不是事实数据，必须与源数据分开解释",
}


@dataclass
class AuditBundle:
    queried_at: datetime = field(default_factory=lambda: datetime.now(SHANGHAI))
    sources: list[dict[str, Any]] = field(default_factory=list)
    data_audit: list[dict[str, Any]] = field(default_factory=list)
    data_warnings: list[dict[str, Any] | str] = field(default_factory=list)
    data_policy: dict[str, Any] = field(default_factory=lambda: dict(DATA_POLICY))

    def add_source(
        self,
        interface: str,
        upstream: str,
        *,
        documentation_url: str = PUBLIC_FUND_DOC,
        provider: str = "AKShare",
        provider_version: str | None = SUPPORTED_AKSHARE_VERSION,
    ) -> None:
        source = {
            "provider": provider,
            "provider_version": provider_version,
            "interface": interface,
            "upstream": upstream,
            "documentation_url": documentation_url,
        }
        if source not in self.sources:
            self.sources.append(source)

    def add_passed_frame(
        self,
        interface: str,
        parameters: dict[str, Any],
        frame: pd.DataFrame,
        *,
        required_columns: Sequence[str],
    ) -> None:
        self.data_audit.append(
            {
                "interface": interface,
                "parameters": json_value(parameters),
                "row_count": len(frame),
                "columns": [str(column) for column in frame.columns],
                "required_columns": sorted(str(column) for column in required_columns),
                "frame_sha256": frame_fingerprint(frame),
                "validation": "passed",
                "skill_transform_at_ingestion": "none",
                "received_from_provider": "AKShare DataFrame",
            }
        )

    def add_failed_call(
        self,
        interface: str,
        parameters: dict[str, Any],
        exc: DataCoreError,
    ) -> None:
        self.data_audit.append(
            {
                "interface": interface,
                "parameters": json_value(parameters),
                "validation": "failed",
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": json_value(exc.details),
                },
            }
        )


def normalize_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


def optional_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def rounded(value: Any, digits: int = 2) -> float | None:
    number = optional_float(value)
    return round(number, digits) if number is not None else None


def operation_is_open(status: Any) -> bool | None:
    text = str(status or "").strip()
    if not text or text == "nan" or "场内交易" in text:
        return None
    limited_markers = ("暂停大额", "暂停大笔", "限额", "限大额")
    if any(marker in text for marker in limited_markers):
        return True
    negative_markers = ("暂停", "停止", "封闭", "不可", "终止")
    if any(marker in text for marker in negative_markers):
        return False
    positive_markers = ("开放", "正常", "可申", "可赎")
    if any(marker in text for marker in positive_markers):
        return True
    return None


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if value is pd.NaT:
        return None
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return json_value(value.item())
        except (TypeError, ValueError):
            pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def frame_fingerprint(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized.columns = [str(column) for column in normalized.columns]
    normalized = normalized.astype(str)
    hashed = pd.util.hash_pandas_object(normalized, index=True).values.tobytes()
    return hashlib.sha256(hashed).hexdigest()


def validate_frame(
    frame: Any,
    interface: str,
    *,
    required_columns: Sequence[str] | None = None,
    allow_empty: bool = False,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise DataCoreError(
            "DATA_CONTRACT_ERROR",
            f"{interface} 未返回 DataFrame",
            {"actual_type": type(frame).__name__},
        )
    if frame.columns.duplicated().any():
        raise DataCoreError(
            "DATA_CONTRACT_ERROR",
            f"{interface} 返回重复列名",
            {
                "duplicate_columns": [
                    str(column) for column in frame.columns[frame.columns.duplicated()]
                ]
            },
        )
    expected_columns = set(required_columns or INTERFACE_CONTRACTS.get(interface, set()))
    missing_columns = sorted(expected_columns - set(frame.columns))
    if missing_columns:
        raise DataCoreError(
            "DATA_CONTRACT_ERROR",
            f"{interface} 返回字段与已验证契约不一致",
            {
                "missing_columns": missing_columns,
                "actual_columns": [str(column) for column in frame.columns],
            },
        )
    if frame.empty and not allow_empty:
        raise DataCoreError(
            "DATA_EMPTY",
            f"{interface} 返回空数据，拒绝生成结论",
        )
    return frame
