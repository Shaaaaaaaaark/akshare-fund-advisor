#!/usr/bin/env python3
"""AKShare-backed fund lookup and reference analysis for model consumption."""

import argparse
import hashlib
import io
import json
import math
import os
import re
import signal
import sys
import threading
import warnings
from contextlib import contextmanager, redirect_stderr
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

import pandas as pd

SHANGHAI = ZoneInfo("Asia/Shanghai")
PUBLIC_FUND_DOC = "https://akshare.akfamily.xyz/data/fund/fund_public.html"
INDEX_DOC = "https://akshare.akfamily.xyz/data/stock/stock.html"
AKSHARE_DOC = "https://akshare.akfamily.xyz/"
DEFAULT_TIMEOUT_SECONDS = int(os.environ.get("AKSHARE_FUND_TIMEOUT", "45"))
SUPPORTED_AKSHARE_VERSION = "1.18.64"
ETF_PREMIUM_PAUSE_THRESHOLD_PCT = 5.0
INTERFACE_CONTRACTS = {
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
    "fund_info_ths": {"字段", "值"},
    "fund_etf_spot_em": {
        "代码",
        "名称",
        "最新价",
        "IOPV实时估值",
        "基金折价率",
        "涨跌幅",
        "成交额",
        "换手率",
        "买一",
        "卖一",
        "数据日期",
        "更新时间",
    },
    "fund_etf_hist_em": {
        "日期",
        "开盘",
        "收盘",
        "最高",
        "最低",
        "成交量",
        "成交额",
        "涨跌幅",
    },
    "fund_lof_hist_em": {
        "日期",
        "开盘",
        "收盘",
        "最高",
        "最低",
        "成交量",
        "成交额",
        "涨跌幅",
    },
    "fund_etf_hist_sina": {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    },
    "fund_individual_detail_hold_xq": {"资产类型", "仓位占比"},
    "fund_individual_basic_info_xq": {"item", "value"},
    "fund_individual_detail_info_xq": {"费用类型", "条件或名称", "费用"},
    "fund_rating_all": {"代码", "简称", "基金公司", "类型"},
    "fund_portfolio_hold_em": {
        "股票代码",
        "股票名称",
        "占净值比例",
        "持股数",
        "持仓市值",
        "季度",
    },
    "tool_trade_date_hist_sina": {"trade_date"},
    "stock_index_pe_lg": {
        "日期",
        "指数",
        "等权静态市盈率",
        "静态市盈率",
        "等权滚动市盈率",
        "滚动市盈率",
    },
    "stock_index_pb_lg": {
        "日期",
        "指数",
        "市净率",
        "等权市净率",
        "市净率中位数",
    },
    "stock_zh_index_daily": {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    },
    "stock_info_a_code_name": {"code", "name"},
    "stock_zh_valuation_baidu": {"date", "value"},
    "stock_zh_a_daily": {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    },
}
SUPPORTED_INDEX_VALUATIONS = (
    "创业板50",
    "中证1000",
    "沪深300",
    "上证380",
    "中证500",
    "上证180",
    "深证红利",
    "深证100",
    "上证红利",
    "中证100",
    "中证800",
    "上证50",
)
INDEX_CATALOG = {
    "创业板50": {
        "akshare_symbol": "创业板50",
        "index_code": "399673",
        "qualified_code": "399673.SZ",
    },
    "中证1000": {
        "akshare_symbol": "中证1000",
        "index_code": "000852",
        "qualified_code": "000852.SH",
    },
    "沪深300": {
        "akshare_symbol": "沪深300",
        "index_code": "000300",
        "qualified_code": "000300.SH",
    },
    "上证380": {
        "akshare_symbol": "上证380",
        "index_code": "000009",
        "qualified_code": "000009.SH",
    },
    "中证500": {
        "akshare_symbol": "中证500",
        "index_code": "000905",
        "qualified_code": "000905.SH",
    },
    "上证180": {
        "akshare_symbol": "上证180",
        "index_code": "000010",
        "qualified_code": "000010.SH",
    },
    "深证红利": {
        "akshare_symbol": "深证红利",
        "index_code": "399324",
        "qualified_code": "399324.SZ",
    },
    "深证100": {
        "akshare_symbol": "深证100",
        "index_code": "399330",
        "qualified_code": "399330.SZ",
    },
    "上证红利": {
        "akshare_symbol": "上证红利",
        "index_code": "000015",
        "qualified_code": "000015.SH",
    },
    "中证100": {
        "akshare_symbol": "中证100",
        "index_code": "000903",
        "qualified_code": "000903.SH",
    },
    "中证800": {
        "akshare_symbol": "中证800",
        "index_code": "000906",
        "qualified_code": "000906.SH",
    },
    "上证50": {
        "akshare_symbol": "上证50",
        "index_code": "000016",
        "qualified_code": "000016.SH",
    },
}
INDEX_ALIASES = {
    "红利指数": "上证红利",
    "上证红利指数": "上证红利",
    "中证小盘500": "中证500",
    "沪深300指数": "沪深300",
    "上证50指数": "上证50",
}


class AdvisorError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class DataSourceTimeout(TimeoutError):
    pass


@contextmanager
def deadline(seconds: int) -> Iterable[None]:
    """Apply a best-effort timeout on Unix without adding another dependency."""
    if (
        seconds <= 0
        or not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def handle_timeout(_signum: int, _frame: Any) -> None:
        raise DataSourceTimeout("data source call timed out")

    previous_handler = signal.getsignal(signal.SIGALRM)
    signal.signal(signal.SIGALRM, handle_timeout)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def normalize_code(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text


def optional_float(value: Any) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return None
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def rounded(value: Any, digits: int = 2) -> Optional[float]:
    number = optional_float(value)
    return round(number, digits) if number is not None else None


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
        except (ValueError, TypeError):
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


def date_age_days(value: Any, today: Optional[date] = None) -> Optional[int]:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    parsed_date = parsed.date()
    reference = today or datetime.now(SHANGHAI).date()
    return (reference - parsed_date).days


def parse_percent_text(value: Any) -> Optional[float]:
    if value is None:
        return None
    matched = re.search(r"(-?\d+(?:\.\d+)?)\s*%", str(value))
    return rounded(matched.group(1)) if matched else None


def parse_yi_text(value: Any) -> Optional[float]:
    if value is None:
        return None
    matched = re.search(r"(-?\d+(?:\.\d+)?)\s*亿", str(value))
    return rounded(matched.group(1)) if matched else None


def disclosed_quarter_candidates(today: date, count: int = 4) -> List[str]:
    candidates: List[date] = []
    for year in range(today.year - 2, today.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            quarter_end = date(year, month, day)
            if (today - quarter_end).days >= 30:
                candidates.append(quarter_end)
    return [
        item.strftime("%Y%m%d")
        for item in sorted(candidates, reverse=True)[:count]
    ]


def operation_is_open(status: Any) -> Optional[bool]:
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


def premium_rate(price: Any, iopv: Any) -> Optional[float]:
    price_value = optional_float(price)
    iopv_value = optional_float(iopv)
    if price_value is None or iopv_value is None or iopv_value <= 0:
        return None
    return round((price_value - iopv_value) / iopv_value * 100, 2)


def premium_level(rate: Optional[float]) -> Optional[str]:
    if rate is None:
        return None
    if rate > ETF_PREMIUM_PAUSE_THRESHOLD_PCT:
        return "high_premium"
    if rate >= 0.5:
        return "premium"
    if rate <= -2:
        return "high_discount"
    if rate <= -0.5:
        return "discount"
    return "near_iopv"


def percentile_level(percentile: Optional[float]) -> str:
    if percentile is None:
        return "unknown"
    if percentile <= 20:
        return "low"
    if percentile <= 40:
        return "lower_middle"
    if percentile < 60:
        return "middle"
    if percentile < 80:
        return "upper_middle"
    return "high"


def percentile_of_current(values: pd.Series) -> Optional[float]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None
    current = float(numeric.iloc[-1])
    return round((numeric <= current).mean() * 100, 2)


def calculate_valuation_metric(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    years: int,
) -> Optional[Dict[str, Any]]:
    series = prepare_series(frame, date_column, value_column, years)
    if series.empty:
        return None
    percentile = percentile_of_current(series["value"])
    return {
        "current": rounded(series["value"].iloc[-1]),
        "percentile": percentile,
        "level": percentile_level(percentile),
        "history_low": rounded(series["value"].min()),
        "history_high": rounded(series["value"].max()),
        "latest_date": series["date"].iloc[-1].date(),
        "latest_age_days": date_age_days(series["date"].iloc[-1]),
        "actual_start_date": series["date"].iloc[0].date(),
        "observations": len(series),
        "data_quality": series.attrs.get("data_quality", {}),
    }


def sample_chart_series(
    series: pd.DataFrame,
    max_points: int,
) -> List[List[Any]]:
    if series.empty:
        return []
    count = len(series)
    if count <= max_points:
        indexes = list(range(count))
    else:
        values = series["value"].astype(float)
        mandatory = {
            0,
            count - 1,
            int(values.idxmin()),
            int(values.idxmax()),
        }
        remaining = max(max_points - len(mandatory), 0)
        sampled = {
            round(index * (count - 1) / max(remaining - 1, 1))
            for index in range(remaining)
        }
        indexes = sorted(mandatory | sampled)
        if len(indexes) > max_points:
            removable = [index for index in indexes if index not in mandatory]
            while len(indexes) > max_points and removable:
                indexes.remove(removable.pop(len(removable) // 2))

    return [
        [
            series["date"].iloc[index].date().isoformat(),
            rounded(series["value"].iloc[index], 4),
        ]
        for index in indexes
    ]


def valuation_window_statistics(
    series: pd.DataFrame,
    maximum_years: int,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    latest_date = series["date"].iloc[-1]
    for years in (3, 5, 10, 20):
        if years > maximum_years:
            continue
        window = series[
            series["date"] >= latest_date - pd.DateOffset(years=years)
        ]
        if len(window) < 100:
            continue
        values = window["value"].astype(float)
        percentile = percentile_of_current(values)
        result[f"{years}_years"] = {
            "actual_start_date": window["date"].iloc[0].date(),
            "latest_date": window["date"].iloc[-1].date(),
            "observations": len(window),
            "current": rounded(values.iloc[-1]),
            "percentile": percentile,
            "level": percentile_level(percentile),
            "median": rounded(values.median()),
            "mean": rounded(values.mean()),
            "p20": rounded(values.quantile(0.2)),
            "p80": rounded(values.quantile(0.8)),
            "minimum": rounded(values.min()),
            "maximum": rounded(values.max()),
        }
    return result


def build_valuation_chart_metric(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    metric: str,
    years: int,
    max_points: int,
) -> Optional[Dict[str, Any]]:
    series = prepare_series(frame, date_column, value_column, years)
    if series.empty:
        return None
    values = series["value"].astype(float)
    current = float(values.iloc[-1])
    mean = float(values.mean())
    median = float(values.median())
    standard_deviation = float(values.std(ddof=0))
    percentile = percentile_of_current(values)
    minimum_index = int(values.idxmin())
    maximum_index = int(values.idxmax())
    quantiles = values.quantile([0.1, 0.2, 0.5, 0.8, 0.9])
    chart_series = sample_chart_series(series, max_points)
    return {
        "metric": metric,
        "unit": "倍",
        "current": rounded(current),
        "percentile": percentile,
        "level": percentile_level(percentile),
        "mean": rounded(mean),
        "median": rounded(median),
        "standard_deviation": rounded(standard_deviation),
        "mean_minus_1_stddev": rounded(mean - standard_deviation),
        "mean_plus_1_stddev": rounded(mean + standard_deviation),
        "z_score": rounded(
            (current - mean) / standard_deviation
            if standard_deviation > 0
            else None
        ),
        "current_vs_mean_pct": rounded((current / mean - 1) * 100 if mean else None),
        "quantiles": {
            "p10": rounded(quantiles.loc[0.1]),
            "p20": rounded(quantiles.loc[0.2]),
            "p50": rounded(quantiles.loc[0.5]),
            "p80": rounded(quantiles.loc[0.8]),
            "p90": rounded(quantiles.loc[0.9]),
        },
        "minimum": {
            "value": rounded(values.iloc[minimum_index]),
            "date": series["date"].iloc[minimum_index].date(),
        },
        "maximum": {
            "value": rounded(values.iloc[maximum_index]),
            "date": series["date"].iloc[maximum_index].date(),
        },
        "latest_date": series["date"].iloc[-1].date(),
        "latest_age_days": date_age_days(series["date"].iloc[-1]),
        "actual_start_date": series["date"].iloc[0].date(),
        "source_observations": len(series),
        "data_quality": series.attrs.get("data_quality", {}),
        "window_statistics": valuation_window_statistics(series, years),
        "interpretation_priority": [
            "历史分位与中位数",
            "20%/80%分位区间",
            "均值",
            "均值正负一倍标准差仅作辅助",
        ],
        "displayed_points": len(chart_series),
        "chart_series": chart_series,
        "reference_lines": {
            "mean": rounded(mean),
            "median": rounded(median),
            "mean_minus_1_stddev": rounded(mean - standard_deviation),
            "mean_plus_1_stddev": rounded(mean + standard_deviation),
            "p20": rounded(quantiles.loc[0.2]),
            "p80": rounded(quantiles.loc[0.8]),
        },
    }


def dca_action_band(
    pe_percentile: Optional[float],
    trend: str,
    premium: Optional[float],
) -> Tuple[str, str]:
    if premium is not None and premium > ETF_PREMIUM_PAUSE_THRESHOLD_PCT:
        return "pause_current_exchange_venue", "high_exchange_premium"
    if pe_percentile is None:
        return "base_contribution_no_valuation_signal", "no_reliable_valuation"
    if pe_percentile >= 80:
        return "reduced_contribution_or_wait", "pe_ttm_percentile"
    if pe_percentile <= 20 and trend == "down":
        return "base_contribution_keep_reserve", "pe_ttm_percentile_downtrend"
    if pe_percentile <= 20:
        return "base_or_modest_tilt", "pe_ttm_percentile"
    return "base_contribution", "pe_ttm_percentile"


def prepare_series(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    years: int,
    positive_only: bool = True,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "value"])
    missing_columns = [
        column for column in (date_column, value_column) if column not in frame
    ]
    if missing_columns:
        raise AdvisorError(
            "DATA_CONTRACT_ERROR",
            "时间序列缺少必需字段",
            {
                "missing_columns": missing_columns,
                "actual_columns": [str(column) for column in frame.columns],
            },
        )
    result = frame[[date_column, value_column]].copy()
    result.columns = ["date", "value"]
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    source_rows = len(result)
    invalid_rows = int(result[["date", "value"]].isna().any(axis=1).sum())
    result = result.dropna().sort_values("date")

    duplicate_rows = int(result.duplicated("date", keep=False).sum())
    if duplicate_rows:
        conflicts = (
            result.groupby("date")["value"].nunique().loc[lambda values: values > 1]
        )
        if not conflicts.empty:
            raise AdvisorError(
                "DUPLICATE_DATE_CONFLICT",
                "同一日期存在不同数值，拒绝自动选择或合并",
                {
                    "conflict_dates": [
                        item.date().isoformat() for item in conflicts.index[:20]
                    ],
                    "conflict_count": len(conflicts),
                },
            )
        result = result.drop_duplicates("date", keep="last")

    nonpositive_rows = 0
    if positive_only:
        nonpositive_rows = int((result["value"] <= 0).sum())
        result = result[result["value"] > 0]
    if result.empty:
        return result
    start = result["date"].iloc[-1] - pd.DateOffset(years=years)
    result = result[result["date"] >= start].reset_index(drop=True)
    result.attrs["data_quality"] = {
        "source_rows": source_rows,
        "invalid_rows_dropped": invalid_rows,
        "duplicate_rows": duplicate_rows,
        "duplicate_policy": "仅同值重复可去重；冲突值直接报错",
        "nonpositive_rows_dropped": nonpositive_rows,
        "window_rows": len(result),
        "interpolation": "none",
        "forward_fill": "none",
    }
    return result


def trailing_return(
    series: pd.DataFrame,
    latest_value: float,
    months: int,
) -> Optional[float]:
    target = series["date"].iloc[-1] - pd.DateOffset(months=months)
    eligible = series[series["date"] <= target]
    if eligible.empty:
        return None
    base = optional_float(eligible["value"].iloc[-1])
    if base is None or base <= 0:
        return None
    return round((latest_value / base - 1) * 100, 2)


def calculate_holding_experience(series: pd.DataFrame) -> Dict[str, Any]:
    values = series["value"].astype(float)
    dates = series["date"]
    daily_returns = values.pct_change().dropna()
    elapsed_days = max((dates.iloc[-1] - dates.iloc[0]).days, 1)
    annualized_return = (
        (float(values.iloc[-1]) / float(values.iloc[0]))
        ** (365.25 / elapsed_days)
        - 1
    ) * 100

    downside_returns = daily_returns.clip(upper=0)
    downside_volatility = (
        math.sqrt(float((downside_returns**2).mean())) * math.sqrt(250) * 100
        if len(downside_returns) >= 20
        else None
    )

    running_peak = values.cummax()
    drawdowns = values / running_peak - 1
    maximum_drawdown = float(drawdowns.min())
    trough_position: Optional[int] = None
    peak_position: Optional[int] = None
    recovery_position: Optional[int] = None
    if maximum_drawdown < 0:
        trough_position = int(drawdowns.to_numpy().argmin())
        peak_position = int(
            values.iloc[: trough_position + 1].to_numpy().argmax()
        )
        peak_value = float(values.iloc[peak_position])
        recovery_candidates = [
            position
            for position in range(trough_position + 1, len(values))
            if float(values.iloc[position]) >= peak_value
        ]
        recovery_position = recovery_candidates[0] if recovery_candidates else None

    longest_underwater_days = 0
    current_underwater_start: Optional[int] = None
    for position, is_underwater in enumerate((drawdowns < 0).tolist()):
        if is_underwater and current_underwater_start is None:
            current_underwater_start = position
        if not is_underwater and current_underwater_start is not None:
            duration = (
                dates.iloc[position] - dates.iloc[current_underwater_start]
            ).days
            longest_underwater_days = max(longest_underwater_days, duration)
            current_underwater_start = None
    if current_underwater_start is not None:
        duration = (
            dates.iloc[-1] - dates.iloc[current_underwater_start]
        ).days
        longest_underwater_days = max(longest_underwater_days, duration)

    monthly = series.copy()
    monthly["month"] = monthly["date"].dt.to_period("M")
    monthly_values = monthly.groupby("month")["value"].last()
    monthly_returns = monthly_values.pct_change().dropna() * 100

    rolling_250 = values.pct_change(250).dropna() * 100
    return {
        "annualized_return_pct": rounded(annualized_return),
        "downside_volatility_pct": rounded(downside_volatility),
        "calmar_ratio": rounded(
            annualized_return / abs(maximum_drawdown * 100)
            if maximum_drawdown < 0
            else None
        ),
        "max_drawdown_detail": {
            "drawdown_pct": rounded(maximum_drawdown * 100),
            "peak_date": (
                dates.iloc[peak_position].date()
                if peak_position is not None
                else None
            ),
            "trough_date": (
                dates.iloc[trough_position].date()
                if trough_position is not None
                else None
            ),
            "recovery_date": (
                dates.iloc[recovery_position].date()
                if recovery_position is not None
                else None
            ),
            "recovery_days_from_trough": (
                (dates.iloc[recovery_position] - dates.iloc[trough_position]).days
                if recovery_position is not None and trough_position is not None
                else None
            ),
            "recovered": recovery_position is not None,
        },
        "longest_underwater_days": longest_underwater_days,
        "monthly_return_statistics": {
            "observations": len(monthly_returns),
            "positive_month_ratio_pct": rounded(
                (monthly_returns > 0).mean() * 100
                if len(monthly_returns)
                else None
            ),
            "median_pct": rounded(monthly_returns.median()),
            "best_pct": rounded(monthly_returns.max()),
            "worst_pct": rounded(monthly_returns.min()),
        },
        "rolling_250_observation_return_statistics": {
            "observations": len(rolling_250),
            "positive_ratio_pct": rounded(
                (rolling_250 > 0).mean() * 100 if len(rolling_250) else None
            ),
            "p10_pct": rounded(rolling_250.quantile(0.1)),
            "median_pct": rounded(rolling_250.median()),
            "p90_pct": rounded(rolling_250.quantile(0.9)),
            "best_pct": rounded(rolling_250.max()),
            "worst_pct": rounded(rolling_250.min()),
            "note": "250 个日频观测近似一年，不等同于精确自然年收益。",
        },
    }


def calculate_metrics(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
    years: int = 3,
) -> Dict[str, Any]:
    series = prepare_series(frame, date_column, value_column, years)
    if len(series) < 2:
        raise AdvisorError(
            "INSUFFICIENT_HISTORY",
            "历史数据不足，无法计算参考指标",
            {"observations": len(series)},
        )

    values = series["value"].astype(float)
    latest_value = float(values.iloc[-1])
    daily_returns = values.pct_change().dropna()
    running_peak = values.cummax()
    drawdowns = values / running_peak - 1
    annualized_volatility = (
        daily_returns.std(ddof=1) * math.sqrt(250) * 100
        if len(daily_returns) >= 20
        else None
    )
    moving_average_20 = values.tail(20).mean() if len(values) >= 20 else None
    moving_average_60 = values.tail(60).mean() if len(values) >= 60 else None
    moving_average_250 = values.tail(250).mean() if len(values) >= 250 else None

    if moving_average_20 is None or moving_average_60 is None:
        trend = "insufficient_history"
    elif latest_value >= moving_average_60 and moving_average_20 >= moving_average_60:
        trend = "up"
    elif latest_value < moving_average_60 and moving_average_20 < moving_average_60:
        trend = "down"
    else:
        trend = "mixed"

    position_percentile = percentile_of_current(values)
    window_low = float(values.min())
    window_high = float(values.max())
    holding_experience = calculate_holding_experience(series)
    return {
        "latest_date": series["date"].iloc[-1].date(),
        "latest_age_days": date_age_days(series["date"].iloc[-1]),
        "latest_value": rounded(latest_value, 4),
        "observations": len(series),
        "actual_start_date": series["date"].iloc[0].date(),
        "data_quality": series.attrs.get("data_quality", {}),
        "returns_pct": {
            "1_month": trailing_return(series, latest_value, 1),
            "3_month": trailing_return(series, latest_value, 3),
            "6_month": trailing_return(series, latest_value, 6),
            "12_month": trailing_return(series, latest_value, 12),
        },
        "current_drawdown_pct": rounded(drawdowns.iloc[-1] * 100),
        "max_drawdown_pct": rounded(drawdowns.min() * 100),
        "annualized_volatility_pct": rounded(annualized_volatility),
        "holding_experience": holding_experience,
        "positive_day_ratio_pct": rounded((daily_returns > 0).mean() * 100),
        "history_position_percentile": position_percentile,
        "history_position_level": percentile_level(position_percentile),
        "distance_from_window_high_pct": rounded(
            (latest_value / window_high - 1) * 100
        ),
        "distance_above_window_low_pct": rounded(
            (latest_value / window_low - 1) * 100
        ),
        "window_low": rounded(window_low, 4),
        "window_high": rounded(window_high, 4),
        "moving_average_20": rounded(moving_average_20, 4),
        "moving_average_60": rounded(moving_average_60, 4),
        "moving_average_250": rounded(moving_average_250, 4),
        "distance_from_ma20_pct": rounded(
            (latest_value / moving_average_20 - 1) * 100
            if moving_average_20
            else None
        ),
        "distance_from_ma60_pct": rounded(
            (latest_value / moving_average_60 - 1) * 100
            if moving_average_60
            else None
        ),
        "distance_from_ma250_pct": rounded(
            (latest_value / moving_average_250 - 1) * 100
            if moving_average_250
            else None
        ),
        "trend": trend,
    }


def calculate_yield_metrics(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
) -> Dict[str, Any]:
    series = prepare_series(
        frame,
        date_column,
        value_column,
        1,
        positive_only=False,
    )
    if series.empty:
        raise AdvisorError("INSUFFICIENT_HISTORY", "货币基金收益率历史数据为空")
    values = series["value"].astype(float)
    return {
        "latest_date": series["date"].iloc[-1].date(),
        "latest_age_days": date_age_days(series["date"].iloc[-1]),
        "latest_7d_annualized_yield_pct": rounded(values.iloc[-1], 4),
        "average_30_observations_pct": rounded(values.tail(30).mean(), 4),
        "average_90_observations_pct": rounded(values.tail(90).mean(), 4),
        "one_year_low_pct": rounded(values.min(), 4),
        "one_year_high_pct": rounded(values.max(), 4),
        "observations": len(values),
        "data_quality": series.attrs.get("data_quality", {}),
    }


def market_session_from_dates(
    trading_dates: Sequence[date],
    now: datetime,
) -> Dict[str, Any]:
    unique_dates = sorted(set(trading_dates))
    today = now.date()
    clock = now.timetz().replace(tzinfo=None)
    is_trading_day = today in unique_dates
    morning_open = time(9, 30) <= clock < time(11, 30)
    afternoon_open = time(13, 0) <= clock < time(15, 0)

    if not is_trading_day:
        state = "non_trading_day"
        market_open_now = False
    elif clock < time(9, 30):
        state = "pre_open"
        market_open_now = False
    elif morning_open or afternoon_open:
        state = "open"
        market_open_now = True
    elif time(11, 30) <= clock < time(13, 0):
        state = "lunch_break"
        market_open_now = False
    else:
        state = "closed"
        market_open_now = False

    if market_open_now:
        next_session_date = None
        next_session_time = None
    elif is_trading_day and clock < time(9, 30):
        next_session_date = today
        next_session_time = "09:30"
    elif is_trading_day and time(11, 30) <= clock < time(13, 0):
        next_session_date = today
        next_session_time = "13:00"
    else:
        future_dates = [item for item in unique_dates if item > today]
        next_session_date = future_dates[0] if future_dates else None
        next_session_time = "09:30" if next_session_date else None

    return {
        "timezone": "Asia/Shanghai",
        "checked_at": now,
        "is_trading_day": is_trading_day,
        "standard_market_open_now": market_open_now,
        "state": state,
        "standard_sessions": ["09:30-11:30", "13:00-15:00"],
        "next_standard_session_date": next_session_date,
        "next_standard_session_time": next_session_time,
        "calendar_data_through": unique_dates[-1] if unique_dates else None,
        "note": "仅判断交易日和标准时段；停牌、券商状态及特殊安排需另行核对。",
    }


class FundAdvisor:
    def __init__(
        self,
        now: Optional[datetime] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="urllib3 v2 only supports OpenSSL.*",
                )
                import akshare as ak
        except ImportError as exc:
            raise AdvisorError(
                "MISSING_DEPENDENCY",
                "未安装 AKShare，请先运行 scripts/setup.sh",
            ) from exc
        actual_version = getattr(ak, "__version__", None)
        if actual_version != SUPPORTED_AKSHARE_VERSION:
            raise AdvisorError(
                "AKSHARE_VERSION_MISMATCH",
                "AKShare 版本未经本 Skill 验证，拒绝继续以避免字段错位",
                {
                    "expected": SUPPORTED_AKSHARE_VERSION,
                    "actual": actual_version,
                },
            )
        self.ak = ak
        self.now = now or datetime.now(SHANGHAI)
        if self.now.tzinfo is None:
            self.now = self.now.replace(tzinfo=SHANGHAI)
        self.timeout_seconds = timeout_seconds
        self.sources: List[Dict[str, Any]] = []
        self.data_warnings: List[Dict[str, Any]] = []
        self.data_audit: List[Dict[str, Any]] = []
        self._names_frame: Optional[pd.DataFrame] = None
        self._purchase_frame: Optional[pd.DataFrame] = None
        self._calendar_frame: Optional[pd.DataFrame] = None
        self._etf_spot_frame: Optional[pd.DataFrame] = None
        self._stock_names_frame: Optional[pd.DataFrame] = None
        self._rating_frame: Optional[pd.DataFrame] = None
        self._rating_unavailable = False
        self._rating_audit: List[Dict[str, Any]] = []
        self._profile_cache: Dict[str, Optional[Dict[str, Any]]] = {}
        self._valuation_cache: Dict[Tuple[str, int], Dict[str, Any]] = {}
        self._valuation_audit_cache: Dict[
            Tuple[str, int],
            List[Dict[str, Any]],
        ] = {}

    def _add_source(
        self,
        interface: str,
        upstream: str,
        documentation_url: str = PUBLIC_FUND_DOC,
        provider: str = "AKShare",
        provider_version: Optional[str] = SUPPORTED_AKSHARE_VERSION,
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

    def _warn(self, interface: str, exc: Exception) -> None:
        warning = {
            "interface": interface,
            "message": str(exc),
            "effect": "该接口数据未用于结论，不能据此推断状态或数值。",
        }
        if warning not in self.data_warnings:
            self.data_warnings.append(warning)

    def _call(
        self,
        interface: str,
        upstream: str,
        function: Any,
        *args: Any,
        optional: bool = False,
        documentation_url: str = PUBLIC_FUND_DOC,
        required_columns: Optional[Sequence[str]] = None,
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> Optional[pd.DataFrame]:
        request_parameters = {
            "args": json_value(list(args)),
            "kwargs": json_value(kwargs),
        }
        try:
            with io.StringIO() as stderr_buffer:
                with redirect_stderr(stderr_buffer), deadline(self.timeout_seconds):
                    frame = function(*args, **kwargs)
            if not isinstance(frame, pd.DataFrame):
                raise AdvisorError(
                    "DATA_CONTRACT_ERROR",
                    f"{interface} 未返回 DataFrame",
                    {"actual_type": type(frame).__name__},
                )
            if frame.columns.duplicated().any():
                raise AdvisorError(
                    "DATA_CONTRACT_ERROR",
                    f"{interface} 返回重复列名",
                    {
                        "duplicate_columns": [
                            str(column)
                            for column in frame.columns[frame.columns.duplicated()]
                        ]
                    },
                )
            expected_columns = set(
                required_columns or INTERFACE_CONTRACTS.get(interface, set())
            )
            missing_columns = sorted(expected_columns - set(frame.columns))
            if missing_columns:
                raise AdvisorError(
                    "DATA_CONTRACT_ERROR",
                    f"{interface} 返回字段与已验证契约不一致",
                    {
                        "missing_columns": missing_columns,
                        "actual_columns": [str(column) for column in frame.columns],
                    },
                )
            if frame.empty and not allow_empty:
                raise AdvisorError(
                    "DATA_EMPTY",
                    f"{interface} 返回空数据，拒绝生成结论",
                )
            self._add_source(interface, upstream, documentation_url)
            self.data_audit.append(
                {
                    "interface": interface,
                    "parameters": request_parameters,
                    "row_count": len(frame),
                    "columns": [str(column) for column in frame.columns],
                    "required_columns": sorted(expected_columns),
                    "frame_sha256": frame_fingerprint(frame),
                    "validation": "passed",
                    "skill_transform_at_ingestion": "none",
                    "received_from_provider": "AKShare DataFrame",
                }
            )
            return frame
        except AdvisorError as exc:
            self.data_audit.append(
                {
                    "interface": interface,
                    "parameters": request_parameters,
                    "validation": "failed",
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    },
                }
            )
            if optional:
                self._warn(interface, exc)
                return None
            raise
        except Exception as exc:
            wrapped = AdvisorError(
                "DATA_SOURCE_ERROR",
                f"AKShare 接口 {interface} 查询失败，当前无法确认",
                {"interface": interface, "reason": str(exc)},
            )
            self.data_audit.append(
                {
                    "interface": interface,
                    "parameters": request_parameters,
                    "validation": "failed",
                    "error": {
                        "code": wrapped.code,
                        "message": wrapped.message,
                        "details": wrapped.details,
                    },
                }
            )
            if optional:
                self._warn(interface, wrapped)
                return None
            raise wrapped from exc

    def _names(self) -> pd.DataFrame:
        if self._names_frame is None:
            self._names_frame = self._call(
                "fund_name_em",
                "东方财富-基金基本信息",
                self.ak.fund_name_em,
            )
        return self._names_frame

    def _purchases(self, optional: bool = False) -> Optional[pd.DataFrame]:
        if self._purchase_frame is None:
            frame = self._call(
                "fund_purchase_em",
                "东方财富-基金申购状态",
                self.ak.fund_purchase_em,
                optional=optional,
            )
            if frame is not None:
                self._purchase_frame = frame
        return self._purchase_frame

    def _calendar(self) -> Optional[pd.DataFrame]:
        if self._calendar_frame is None:
            frame = self._call(
                "tool_trade_date_hist_sina",
                "新浪财经-交易日历",
                self.ak.tool_trade_date_hist_sina,
                optional=True,
            )
            if frame is not None:
                self._calendar_frame = frame
        return self._calendar_frame

    def _etf_spots(self) -> Optional[pd.DataFrame]:
        if self._etf_spot_frame is None:
            frame = self._call(
                "fund_etf_spot_em",
                "东方财富-ETF 实时行情",
                self.ak.fund_etf_spot_em,
                optional=True,
            )
            if frame is not None:
                self._etf_spot_frame = frame
        return self._etf_spot_frame

    def _fund_profile(self, fund: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        code = fund["code"]
        if code in self._profile_cache:
            return self._profile_cache[code]
        frame = self._call(
            "fund_info_ths",
            "同花顺-基金基本信息",
            self.ak.fund_info_ths,
            symbol=code,
            optional=True,
        )
        if frame is None or frame.empty or not {"字段", "值"}.issubset(frame.columns):
            self._profile_cache[code] = None
            return None
        raw = {
            str(row["字段"]).strip(): json_value(row["值"])
            for _, row in frame.iterrows()
        }
        returned_code = normalize_code(raw.get("基金代码"))
        if returned_code != code:
            self._warn(
                "fund_info_ths",
                AdvisorError(
                    "FUND_CODE_MISMATCH",
                    "基金详情返回代码与请求代码不一致",
                    {"requested": code, "returned": returned_code},
                ),
            )
            self._profile_cache[code] = None
            return None
        field_map = {
            "full_name": "基金全称",
            "investment_type": "投资类型",
            "manager": "基金经理",
            "inception_date": "成立日期",
            "share_scale": "份额规模",
            "management_fee": "管理费",
            "custodian_fee": "托管费",
            "max_subscription_fee": "最高申购费",
            "max_redemption_fee": "最高赎回费",
            "benchmark": "业绩比较基准",
            "fund_company": "基金管理人",
        }
        profile = {
            key: raw.get(source_key)
            for key, source_key in field_map.items()
            if raw.get(source_key) not in (None, "")
        }
        management_fee = parse_percent_text(profile.get("management_fee"))
        custodian_fee = parse_percent_text(profile.get("custodian_fee"))
        inception_date = pd.to_datetime(
            profile.get("inception_date"),
            errors="coerce",
        )
        profile["derived"] = {
            "management_fee_pct": management_fee,
            "custodian_fee_pct": custodian_fee,
            "known_ongoing_fee_pct": rounded(
                management_fee + custodian_fee
                if management_fee is not None and custodian_fee is not None
                else None
            ),
            "max_subscription_fee_pct": parse_percent_text(
                profile.get("max_subscription_fee")
            ),
            "max_redemption_fee_pct": parse_percent_text(
                profile.get("max_redemption_fee")
            ),
            "share_scale_yi_units": parse_yi_text(profile.get("share_scale")),
            "fund_age_years": rounded(
                (self.now.date() - inception_date.date()).days / 365.25
                if not pd.isna(inception_date)
                else None
            ),
            "classification": "deterministic_parse_of_source_facts",
            "note": (
                "份额规模单位为亿份，不等同于基金净资产；已知持续费率仅含管理费和托管费。"
            ),
        }
        self._profile_cache[code] = profile
        return profile

    def _fund_rating(
        self,
        fund: Dict[str, Any],
        *,
        optional: bool,
    ) -> Optional[Dict[str, Any]]:
        if self._rating_frame is None:
            if optional and self._rating_unavailable:
                return None
            audit_start = len(self.data_audit)
            frame = self._call(
                "fund_rating_all",
                "天天基金-基金评级",
                self.ak.fund_rating_all,
                optional=optional,
                allow_empty=True,
            )
            self._rating_audit = list(self.data_audit[audit_start:])
            if frame is None:
                self._rating_unavailable = True
                return None
            self._rating_frame = frame

        matched = self._rating_frame[
            self._rating_frame["代码"]
            .map(normalize_code)
            .eq(normalize_code(fund["code"]))
        ]
        if matched.empty:
            if optional:
                return None
            raise AdvisorError(
                "FUND_RATING_NOT_FOUND",
                f"评级数据未收录该基金：{fund['code']}",
                {"fund_code": fund["code"]},
            )
        row = matched.iloc[0]

        def agency(column: str) -> Optional[float]:
            return (
                optional_float(row.get(column))
                if column in matched.columns
                else None
            )

        return {
            "fund_type": json_value(row.get("类型")),
            "fund_company": json_value(row.get("基金公司")),
            "ratings": {
                "shanghai_securities": agency("上海证券"),
                "merchants_securities": agency("招商证券"),
                "jian_jin_xin": agency("济安金信"),
                "morningstar": agency("晨星评级"),
                "five_star_count": agency("5星评级家数"),
            },
            "notes": "评级为第三方机构历史结论，不构成投资建议，也不代表当前业绩。",
        }

    def _portfolio_snapshot(
        self,
        fund: Dict[str, Any],
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "asset_allocation": None,
            "stock_concentration": None,
        }
        for report_date in disclosed_quarter_candidates(self.now.date(), count=1):
            frame = self._call(
                "fund_individual_detail_hold_xq",
                "雪球基金-基金持仓资产比例",
                self.ak.fund_individual_detail_hold_xq,
                symbol=fund["code"],
                date=report_date,
                timeout=self.timeout_seconds,
                optional=True,
                allow_empty=True,
            )
            if frame is None or frame.empty:
                continue
            allocation = [
                {
                    "asset_type": json_value(row.get("资产类型")),
                    "weight_pct": rounded(row.get("仓位占比")),
                }
                for _, row in frame.iterrows()
            ]
            result["asset_allocation"] = {
                "report_date": report_date,
                "items": allocation,
                "reported_weight_sum_pct": rounded(
                    sum(
                        item["weight_pct"]
                        for item in allocation
                        if item["weight_pct"] is not None
                    )
                ),
                "note": "仓位占比为报告期披露数据，不代表当前实时仓位。",
            }
            break

        holdings_year = (
            self.now.year if self.now.month >= 4 else self.now.year - 1
        )
        holdings_frame = self._call(
            "fund_portfolio_hold_em",
            "东方财富-基金股票持仓",
            self.ak.fund_portfolio_hold_em,
            symbol=fund["code"],
            date=str(holdings_year),
            optional=True,
            allow_empty=True,
        )
        if holdings_frame is not None and not holdings_frame.empty:
            quarter_order = {}
            for quarter in holdings_frame["季度"].dropna().astype(str).unique():
                numbers = re.findall(r"\d+", quarter)
                if len(numbers) >= 2:
                    quarter_order[quarter] = (int(numbers[0]), int(numbers[1]))
            if quarter_order:
                latest_quarter = max(quarter_order, key=quarter_order.get)
                latest_holdings = holdings_frame[
                    holdings_frame["季度"].astype(str).eq(latest_quarter)
                ].copy()
                latest_holdings["占净值比例"] = pd.to_numeric(
                    latest_holdings["占净值比例"],
                    errors="coerce",
                )
                latest_holdings = latest_holdings.dropna(
                    subset=["占净值比例"]
                ).sort_values("占净值比例", ascending=False)
                top_ten = latest_holdings.head(10)
                result["stock_concentration"] = {
                    "report_period": latest_quarter,
                    "top_10_weight_pct": rounded(top_ten["占净值比例"].sum()),
                    "top_1_weight_pct": rounded(
                        top_ten["占净值比例"].iloc[0]
                        if not top_ten.empty
                        else None
                    ),
                    "reported_stock_count": len(latest_holdings),
                    "top_holdings": [
                        {
                            "code": normalize_code(row.get("股票代码")),
                            "name": json_value(row.get("股票名称")),
                            "weight_pct": rounded(row.get("占净值比例")),
                        }
                        for _, row in top_ten.iterrows()
                    ],
                    "note": "持仓为定期报告披露值，不代表当前实时持仓。",
                }
        return result

    @staticmethod
    def _match_supported_index(
        fund: Dict[str, Any],
        profile: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        benchmark = str((profile or {}).get("benchmark") or "")
        fund_names = [
            str(fund.get("name") or ""),
            str((profile or {}).get("full_name") or ""),
        ]
        for index_name in sorted(SUPPORTED_INDEX_VALUATIONS, key=len, reverse=True):
            escaped = re.escape(index_name)
            benchmark_pattern = (
                escaped
                + r"(?:指数)?(?:收益率|净收益率|总收益率|[\s]*[*×]|$|[（(])"
            )
            if re.search(benchmark_pattern, benchmark):
                return index_name
            fund_name_pattern = escaped + r"(?:ETF|LOF|指数|联接|增强|基金|$)"
            if any(re.search(fund_name_pattern, name) for name in fund_names):
                return index_name
        return None

    @staticmethod
    def _resolve_index(query: str) -> Dict[str, Any]:
        clean_query = query.strip()
        if not clean_query:
            raise AdvisorError("INVALID_ARGUMENT", "指数名称或代码不能为空")
        canonical_name = INDEX_ALIASES.get(clean_query, clean_query)
        if canonical_name in INDEX_CATALOG:
            return {"name": canonical_name, **INDEX_CATALOG[canonical_name]}

        query_upper = clean_query.upper()
        for name, spec in INDEX_CATALOG.items():
            if (
                query_upper == str(spec["qualified_code"]).upper()
                or query_upper == str(spec["index_code"]).upper()
            ):
                return {"name": name, **spec}

        raise AdvisorError(
            "INDEX_NOT_SUPPORTED",
            f"暂未找到可用估值映射：{query}",
            {
                "supported_indexes": sorted(INDEX_CATALOG),
                "guidance": (
                    "请传入 AKShare 已支持指数的精确名称、已列出的别名"
                    "或对应指数代码。"
                ),
            },
        )

    def _load_valuation_frames(
        self,
        index: Dict[str, Any],
    ) -> Tuple[
        Optional[pd.DataFrame],
        Optional[pd.DataFrame],
        Dict[str, Any],
    ]:
        symbol = index.get("akshare_symbol")
        if not symbol:
            raise AdvisorError(
                "AKSHARE_INDEX_UNAVAILABLE",
                f"AKShare 当前没有 {index['name']} 的同口径历史 PE/PB 回退接口",
            )
        pe_frame = self._call(
            "stock_index_pe_lg",
            "乐咕乐股-指数市盈率",
            self.ak.stock_index_pe_lg,
            symbol=symbol,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        pb_frame = self._call(
            "stock_index_pb_lg",
            "乐咕乐股-指数市净率",
            self.ak.stock_index_pb_lg,
            symbol=symbol,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        if pe_frame is None and pb_frame is None:
            raise AdvisorError(
                "VALUATION_SOURCE_UNAVAILABLE",
                f"AKShare 当前无法取得 {index['name']} 的历史 PE/PB",
                {"symbol": symbol},
            )
        return (
            pe_frame,
            pb_frame,
            {
                "provider": "AKShare",
                "interfaces": ["stock_index_pe_lg", "stock_index_pb_lg"],
                "upstream": "乐咕乐股",
                "fields": {
                    "PE_TTM": "滚动市盈率",
                    "PB": "市净率",
                },
                "available_metrics": [
                    metric
                    for metric, frame in (("PE_TTM", pe_frame), ("PB", pb_frame))
                    if frame is not None
                ],
                "missing_value_policy": "不前向填充；无效行在派生计算前剔除并计数",
            },
        )

    def _load_index_point_frame(
        self,
        index: Dict[str, Any],
    ) -> Optional[pd.DataFrame]:
        interface = getattr(self.ak, "stock_zh_index_daily", None)
        if not callable(interface):
            return None
        qualified_code = str(index.get("qualified_code") or "").upper()
        index_code = str(index.get("index_code") or "")
        if not qualified_code or not index_code:
            return None
        market = "sz" if qualified_code.endswith(".SZ") else "sh"
        return self._call(
            "stock_zh_index_daily",
            "新浪财经-指数历史行情",
            interface,
            symbol=f"{market}{index_code}",
            optional=True,
            documentation_url=INDEX_DOC,
        )

    def _index_valuation(
        self,
        fund: Dict[str, Any],
        profile: Optional[Dict[str, Any]],
        years: int,
    ) -> Dict[str, Any]:
        index_name = self._match_supported_index(fund, profile)
        if index_name is None:
            return {
                "available": False,
                "reason": "未能可靠匹配到 AKShare 支持的宽基指数估值接口。",
            }
        cache_key = (index_name, years)
        if cache_key in self._valuation_cache:
            return self._valuation_cache[cache_key]

        audit_start = len(self.data_audit)
        pe_frame = self._call(
            "stock_index_pe_lg",
            "乐咕乐股-指数市盈率",
            self.ak.stock_index_pe_lg,
            symbol=index_name,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        pb_frame = self._call(
            "stock_index_pb_lg",
            "乐咕乐股-指数市净率",
            self.ak.stock_index_pb_lg,
            symbol=index_name,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        pe = (
            calculate_valuation_metric(
                pe_frame,
                "日期",
                "滚动市盈率",
                years,
            )
            if pe_frame is not None
            else None
        )
        pb = (
            calculate_valuation_metric(
                pb_frame,
                "日期",
                "市净率",
                years,
            )
            if pb_frame is not None
            else None
        )

        def current_metric(
            metric_name: str,
            item: Optional[Dict[str, Any]],
        ) -> Optional[Dict[str, Any]]:
            if item is None or item.get("percentile") is None:
                return None
            age = item.get("latest_age_days")
            if age is None or age < 0 or age > 10:
                self._warn(
                    metric_name,
                    AdvisorError(
                        "STALE_OR_INVALID_DATA",
                        f"{metric_name} 最新日期异常或数据已过期，不用于当前估值",
                        {
                            "latest_date": json_value(item.get("latest_date")),
                            "latest_age_days": age,
                        },
                    ),
                )
                return None
            return item

        pe = current_metric("stock_index_pe_lg", pe)
        pb = current_metric("stock_index_pb_lg", pb)
        usable_metrics = [item for item in (pe, pb) if item is not None]
        if not usable_metrics:
            result = {
                "available": False,
                "index_name": index_name,
                "reason": "指数已匹配，但 PE/PB 历史数据当前不可用。",
            }
        else:
            result = {
                "available": True,
                "index_name": index_name,
                "lookback_years": years,
                "pe_ttm": pe,
                "pb": pb,
                "decision_priority": [
                    "PE_TTM 与 PB 分开解释",
                    "PE TTM 通常作为盈利估值主参考",
                    "PB 对金融、重资产和周期行业更重要",
                    "禁止计算 PE/PB 综合分位",
                ],
                "confidence": "high" if len(usable_metrics) == 2 else "medium",
                "note": (
                    "估值仅代表匹配指数，不代表基金费用、跟踪误差或经理能力；"
                    "PE 与 PB 的经济含义不同，不做简单平均。"
                ),
            }
        self._valuation_cache[cache_key] = result
        self._valuation_audit_cache[cache_key] = list(
            self.data_audit[audit_start:]
        )
        return result

    def valuation(
        self,
        query: str,
        years: int = 10,
        max_points: int = 600,
    ) -> Dict[str, Any]:
        index = self._resolve_index(query)
        pe_frame, pb_frame, source_info = self._load_valuation_frames(index)
        point_frame = self._load_index_point_frame(index)
        pe = (
            build_valuation_chart_metric(
                pe_frame,
                "日期",
                "滚动市盈率",
                "PE_TTM",
                years,
                max_points,
            )
            if pe_frame is not None
            else None
        )
        pb = (
            build_valuation_chart_metric(
                pb_frame,
                "日期",
                "市净率",
                "PB",
                years,
                max_points,
            )
            if pb_frame is not None
            else None
        )
        index_points = (
            build_valuation_chart_metric(
                point_frame,
                "date",
                "close",
                "INDEX_POINTS",
                years,
                max_points,
            )
            if point_frame is not None
            else None
        )
        if index_points is not None:
            index_points["unit"] = "点"
        for metric_name, metric in (("PE_TTM", pe), ("PB", pb)):
            if metric is None:
                continue
            age = metric.get("latest_age_days")
            if age is None or age < 0 or age > 10:
                self._warn(
                    metric_name,
                    AdvisorError(
                        "STALE_OR_INVALID_DATA",
                        f"{metric_name} 最新日期异常或数据已过期，不用于当前估值",
                        {
                            "latest_date": json_value(metric.get("latest_date")),
                            "latest_age_days": age,
                        },
                    ),
                )
                if metric_name == "PE_TTM":
                    pe = None
                else:
                    pb = None
                continue
            if metric.get("source_observations", 0) < 100:
                self._warn(
                    metric_name,
                    AdvisorError(
                        "INSUFFICIENT_HISTORY",
                        f"{metric_name} 有效样本少于 100，不用于历史分位",
                        {"observations": metric.get("source_observations")},
                    ),
                )
                if metric_name == "PE_TTM":
                    pe = None
                else:
                    pb = None
        if index_points is not None:
            age = index_points.get("latest_age_days")
            if age is None or age < 0 or age > 10:
                self._warn(
                    "INDEX_POINTS",
                    AdvisorError(
                        "STALE_OR_INVALID_DATA",
                        "指数点位最新日期异常或数据已过期，不用于图表",
                        {
                            "latest_date": json_value(
                                index_points.get("latest_date")
                            ),
                            "latest_age_days": age,
                        },
                    ),
                )
                index_points = None
        if pe is None and pb is None:
            raise AdvisorError(
                "VALUATION_DATA_EMPTY",
                f"{index['name']} 没有可用且时效合格的历史 PE/PB 数据",
            )
        source_info["available_metrics"] = [
            metric_name
            for metric_name, metric in (("PE_TTM", pe), ("PB", pb))
            if metric is not None
        ]
        if index_points is not None:
            source_info["interfaces"].append("stock_zh_index_daily")
            source_info["fields"]["INDEX_POINTS"] = "指数收盘点位"
        source_info["available_series"] = [
            *source_info["available_metrics"],
            *(["INDEX_POINTS"] if index_points is not None else []),
        ]
        available_windows = sorted(
            {
                window
                for metric in (pe, pb)
                if metric is not None
                for window in metric.get("window_statistics", {})
            },
            key=lambda item: int(item.split("_", 1)[0]),
        )

        start_dates = [
            metric["actual_start_date"]
            for metric in (pe, pb, index_points)
            if metric is not None
        ]
        latest_dates = [
            metric["latest_date"]
            for metric in (pe, pb, index_points)
            if metric is not None
        ]
        return {
            "ok": True,
            "action": "valuation",
            "index": index,
            "actual_source": source_info,
            "lookback": {
                "requested_years": years,
                "actual_start_date": min(start_dates) if start_dates else None,
                "latest_date": max(latest_dates) if latest_dates else None,
                "statistics_frequency": "daily",
                "chart_max_points": max_points,
                "sampling": (
                    "完整日频统计；图表等距采样并强制保留首尾、最高和最低点。"
                ),
            },
            "summary": {
                "pe_ttm": {
                    "current": pe.get("current") if pe else None,
                    "percentile": pe.get("percentile") if pe else None,
                    "level": pe.get("level") if pe else None,
                },
                "pb": {
                    "current": pb.get("current") if pb else None,
                    "percentile": pb.get("percentile") if pb else None,
                    "level": pb.get("level") if pb else None,
                },
                "combined_percentile": None,
                "combined_percentile_policy": "禁止将 PE 与 PB 分位简单平均",
                "interpretation": (
                    "分位数越低，表示当前估值在所选历史区间内相对越低；"
                    "PE 与 PB 必须分别解释，分位数不预测未来涨跌。"
                ),
            },
            "charts": {
                "pe_ttm": pe,
                "pb": pb,
                "index_points": index_points,
            },
            "chart_spec": {
                "renderer": "TRAE-dynamic-ui/PureShowWidget",
                "mode": "panel",
                "layout": (
                    "two_stacked_time_series"
                    if pe is not None and pb is not None
                    else "single_time_series"
                ),
                "title": f"{index['name']} 历史估值",
                "default_period": f"{years}年",
                "available_metrics": source_info["available_metrics"],
                "available_windows": available_windows,
                "lines": {
                    "PE_TTM": "sky",
                    "PB": "indigo",
                    "INDEX_POINTS": "slate",
                    "mean": "slate_dashed",
                    "mean_plus_minus_1_stddev": "amber_dashed",
                    "p20_p80": "mint_coral_dotted",
                },
                "required_features": [
                    "仅渲染 available_metrics 列出的非空估值指标",
                    "十字准星与日期联动提示",
                    "当前值、历史分位、均值、中位数、最高、最低摘要卡",
                    "仅展示 available_windows 列出的窗口分位",
                    "均值、正负一倍标准差、20% 与 80% 分位参考线",
                    "支持拖动缩放时间区间",
                    "PE/PB 与指数点位使用独立纵轴，不混合数值尺度",
                    "明确显示实际数据源和最新数据日期",
                ],
            },
            "limitations": [
                "AKShare 上游对亏损成分、权重、异常值和历史回溯的处理口径可能调整。",
                "PE/PB 只反映历史相对估值，不包含盈利预测、利率环境和行业结构变化。",
                "指数估值不能直接替代具体基金的溢价、费率和跟踪误差分析。",
            ],
            "data_integrity": {
                "ai_generated_market_data": False,
                "interpolation": "none",
                "forward_fill": "none",
                "raw_series_origin": "仅来自 actual_source 所列接口",
                "derived_values": "仅由脚本按输出中声明的公式计算",
            },
        }

    def _stock_names(self) -> pd.DataFrame:
        if self._stock_names_frame is None:
            self._stock_names_frame = self._call(
                "stock_info_a_code_name",
                "AKShare-A股代码名称",
                self.ak.stock_info_a_code_name,
                documentation_url=INDEX_DOC,
            )
        return self._stock_names_frame

    def _resolve_stock(self, query: str) -> Dict[str, str]:
        clean_query = query.strip()
        if not clean_query:
            raise AdvisorError("INVALID_ARGUMENT", "股票名称或代码不能为空")
        frame = self._stock_names()
        code_text = frame["code"].astype(str).str.zfill(6)
        name_text = frame["name"].astype(str)
        if re.fullmatch(r"\d{6}", clean_query):
            matched = frame[code_text.eq(clean_query)]
        else:
            exact = frame[name_text.eq(clean_query)]
            matched = exact if not exact.empty else frame[name_text.str.contains(
                re.escape(clean_query),
                regex=True,
                na=False,
            )]
        if matched.empty:
            raise AdvisorError(
                "STOCK_NOT_FOUND",
                f"未找到 A 股：{query}",
            )
        if len(matched) > 1:
            candidates = [
                {
                    "code": str(row["code"]).zfill(6),
                    "name": str(row["name"]),
                }
                for _, row in matched.head(10).iterrows()
            ]
            raise AdvisorError(
                "ENTITY_AMBIGUOUS",
                f"股票名称存在多个匹配：{query}",
                {"candidates": candidates},
            )
        row = matched.iloc[0]
        code = str(row["code"]).zfill(6)
        if code.startswith(("4", "8")):
            raise AdvisorError(
                "STOCK_MARKET_UNSUPPORTED",
                "当前个股曲线仅支持沪深 A 股，暂不支持北交所。",
                {"code": code},
            )
        market = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return {
            "code": code,
            "name": str(row["name"]),
            "qualified_code": f"{code}.{'SH' if market == 'sh' else 'SZ'}",
            "sina_symbol": f"{market}{code}",
        }

    def stock_valuation(
        self,
        query: str,
        years: int = 10,
        max_points: int = 600,
    ) -> Dict[str, Any]:
        stock = self._resolve_stock(query)
        period = {
            1: "近一年",
            3: "近三年",
            5: "近五年",
            10: "近十年",
        }[years]
        pe_frame = self._call(
            "stock_zh_valuation_baidu",
            "百度股市通-A股历史估值",
            self.ak.stock_zh_valuation_baidu,
            symbol=stock["code"],
            indicator="市盈率(TTM)",
            period=period,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        pb_frame = self._call(
            "stock_zh_valuation_baidu",
            "百度股市通-A股历史估值",
            self.ak.stock_zh_valuation_baidu,
            symbol=stock["code"],
            indicator="市净率",
            period=period,
            optional=True,
            documentation_url=INDEX_DOC,
        )
        start_date = (
            self.now.date() - timedelta(days=years * 366 + 10)
        ).strftime("%Y%m%d")
        end_date = self.now.date().strftime("%Y%m%d")
        price_frame = self._call(
            "stock_zh_a_daily",
            "新浪财经-A股前复权历史行情",
            self.ak.stock_zh_a_daily,
            symbol=stock["sina_symbol"],
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            optional=True,
            documentation_url=INDEX_DOC,
        )

        pe = (
            build_valuation_chart_metric(
                pe_frame,
                "date",
                "value",
                "PE_TTM",
                years,
                max_points,
            )
            if pe_frame is not None
            else None
        )
        pb = (
            build_valuation_chart_metric(
                pb_frame,
                "date",
                "value",
                "PB",
                years,
                max_points,
            )
            if pb_frame is not None
            else None
        )
        stock_price = (
            build_valuation_chart_metric(
                price_frame,
                "date",
                "close",
                "STOCK_PRICE",
                years,
                max_points,
            )
            if price_frame is not None
            else None
        )
        if stock_price is not None:
            stock_price["unit"] = "元"

        for metric_name, metric in (
            ("PE_TTM", pe),
            ("PB", pb),
            ("STOCK_PRICE", stock_price),
        ):
            if metric is None:
                continue
            age = metric.get("latest_age_days")
            if age is not None and 0 <= age <= 10:
                continue
            self._warn(
                metric_name,
                AdvisorError(
                    "STALE_OR_INVALID_DATA",
                    f"{metric_name} 最新日期异常或数据已过期，不用于图表",
                    {
                        "latest_date": json_value(metric.get("latest_date")),
                        "latest_age_days": age,
                    },
                ),
            )
            if metric_name == "PE_TTM":
                pe = None
            elif metric_name == "PB":
                pb = None
            else:
                stock_price = None

        for metric_name, metric in (("PE_TTM", pe), ("PB", pb)):
            if metric is None or metric.get("source_observations", 0) >= 100:
                continue
            self._warn(
                metric_name,
                AdvisorError(
                    "INSUFFICIENT_HISTORY",
                    f"{metric_name} 有效样本少于 100，不用于历史分位",
                    {"observations": metric.get("source_observations")},
                ),
            )
            if metric_name == "PE_TTM":
                pe = None
            else:
                pb = None

        if pe is None and pb is None and stock_price is None:
            raise AdvisorError(
                "STOCK_DATA_EMPTY",
                f"{stock['name']} 没有可用且时效合格的估值或价格数据",
            )
        charts = {
            "pe_ttm": pe,
            "pb": pb,
            "stock_price": stock_price,
        }
        available = [
            name
            for name, item in (
                ("PE_TTM", pe),
                ("PB", pb),
                ("STOCK_PRICE", stock_price),
            )
            if item is not None
        ]
        start_dates = [
            item["actual_start_date"]
            for item in charts.values()
            if item is not None
        ]
        latest_dates = [
            item["latest_date"]
            for item in charts.values()
            if item is not None
        ]
        return {
            "ok": True,
            "action": "stock_valuation",
            "stock": {
                key: value
                for key, value in stock.items()
                if key != "sina_symbol"
            },
            "actual_source": {
                "provider": "AKShare",
                "interfaces": [
                    "stock_info_a_code_name",
                    "stock_zh_valuation_baidu",
                    "stock_zh_a_daily",
                ],
                "available_series": available,
                "price_adjustment": "前复权",
            },
            "lookback": {
                "requested_years": years,
                "actual_start_date": min(start_dates) if start_dates else None,
                "latest_date": max(latest_dates) if latest_dates else None,
                "statistics_frequency": "daily",
                "chart_max_points": max_points,
            },
            "summary": {
                "pe_ttm": {
                    "current": pe.get("current") if pe else None,
                    "percentile": pe.get("percentile") if pe else None,
                    "level": pe.get("level") if pe else None,
                },
                "pb": {
                    "current": pb.get("current") if pb else None,
                    "percentile": pb.get("percentile") if pb else None,
                    "level": pb.get("level") if pb else None,
                },
                "stock_price": {
                    "current": (
                        stock_price.get("current")
                        if stock_price
                        else None
                    ),
                    "unit": "元",
                    "adjustment": "前复权",
                },
                "combined_percentile": None,
                "combined_percentile_policy": "禁止将 PE 与 PB 分位简单平均",
            },
            "charts": charts,
            "data_quality": {
                "pe_ttm_available": pe is not None,
                "pb_available": pb is not None,
                "price_available": stock_price is not None,
                "available_series": available,
                "missing_series": [
                    name
                    for name in ("PE_TTM", "PB", "STOCK_PRICE")
                    if name not in available
                ],
                "latest_date": max(latest_dates) if latest_dates else None,
                "warnings": list(self.data_warnings),
            },
            "limitations": [
                "历史 PE/PB 和股价不预测未来涨跌。",
                "个股估值需结合盈利质量、行业周期和财务报告，不构成投资建议。",
                "前复权价格用于历史可比，不等同于当时实际成交价。",
            ],
            "data_integrity": {
                "ai_generated_market_data": False,
                "interpolation": "none",
                "forward_fill": "none",
                "raw_series_origin": "仅来自 actual_source 所列 AKShare 接口",
            },
        }

    @staticmethod
    def _fund_record(row: pd.Series) -> Dict[str, Any]:
        return {
            "code": normalize_code(row.get("基金代码")),
            "name": json_value(row.get("基金简称")),
            "type": json_value(row.get("基金类型")),
            "pinyin_abbr": json_value(row.get("拼音缩写")),
        }

    def _search_candidates(self, query: str) -> List[Tuple[int, Dict[str, Any]]]:
        clean_query = query.strip()
        if not clean_query:
            raise AdvisorError("INVALID_ARGUMENT", "搜索词不能为空")
        query_upper = clean_query.upper()
        query_code = normalize_code(clean_query)
        candidates: List[Tuple[int, Dict[str, Any]]] = []

        for _, row in self._names().iterrows():
            record = self._fund_record(row)
            code = record["code"]
            name = str(record["name"] or "")
            pinyin_abbr = str(record["pinyin_abbr"] or "").upper()
            pinyin_full = str(row.get("拼音全称") or "").upper()

            if query_code == code or clean_query == name:
                score = 0
            elif name.startswith(clean_query) or pinyin_abbr.startswith(query_upper):
                score = 1
            elif (
                clean_query in name
                or query_upper in pinyin_abbr
                or query_upper in pinyin_full
            ):
                score = 2
            else:
                continue
            candidates.append((score, record))

        candidates.sort(key=lambda item: (item[0], item[1]["code"]))
        return candidates

    def search(self, query: str, limit: int = 10) -> Dict[str, Any]:
        candidates = self._search_candidates(query)
        return {
            "ok": True,
            "action": "search",
            "query": query,
            "count": min(len(candidates), limit),
            "has_more": len(candidates) > limit,
            "results": [record for _, record in candidates[:limit]],
            "guidance": (
                "存在多个份额或近似名称时，请使用明确基金代码继续查询。"
                if len(candidates) > 1
                else None
            ),
        }

    def resolve(self, query: str) -> Dict[str, Any]:
        candidates = self._search_candidates(query)
        if not candidates:
            raise AdvisorError(
                "FUND_NOT_FOUND",
                f"未找到基金：{query}",
                {"query": query},
            )
        top_score = candidates[0][0]
        top_records = [record for score, record in candidates if score == top_score]
        if len(top_records) > 1:
            raise AdvisorError(
                "AMBIGUOUS_FUND",
                f"基金名称不唯一，请确认代码：{query}",
                {"candidates": top_records[:10]},
            )
        return top_records[0]

    def _purchase_row(
        self,
        code: str,
        optional: bool,
    ) -> Optional[pd.Series]:
        frame = self._purchases(optional=optional)
        if frame is None or frame.empty or "基金代码" not in frame:
            return None
        matched = frame[
            frame["基金代码"].map(normalize_code).eq(normalize_code(code))
        ]
        return matched.iloc[0] if not matched.empty else None

    @staticmethod
    def _is_exchange_record(
        fund: Dict[str, Any],
        purchase_row: Optional[pd.Series],
    ) -> bool:
        if purchase_row is not None:
            statuses = (
                str(purchase_row.get("申购状态") or ""),
                str(purchase_row.get("赎回状态") or ""),
            )
            if any("场内交易" in item for item in statuses):
                return True
        upper_name = str(fund.get("name") or "").upper()
        return "ETF" in upper_name or "LOF" in upper_name

    def _market_session(self) -> Optional[Dict[str, Any]]:
        frame = self._calendar()
        if frame is None or frame.empty or "trade_date" not in frame:
            return None
        trading_dates = [
            item.date()
            for item in pd.to_datetime(frame["trade_date"], errors="coerce").dropna()
        ]
        if not trading_dates or max(trading_dates) < self.now.date():
            self._warn(
                "tool_trade_date_hist_sina",
                AdvisorError(
                    "STALE_OR_INVALID_DATA",
                    "交易日历未覆盖查询日期，不能确认当前标准交易时段",
                    {
                        "calendar_data_through": (
                            max(trading_dates) if trading_dates else None
                        ),
                        "query_date": self.now.date(),
                    },
                ),
            )
            return None
        return market_session_from_dates(trading_dates, self.now)

    def _status_for_fund(
        self,
        fund: Dict[str, Any],
        optional: bool = False,
    ) -> Dict[str, Any]:
        row = self._purchase_row(fund["code"], optional=optional)
        if row is None:
            if optional:
                return {
                    "confirmed": False,
                    "message": "申购状态表中未找到该代码，当前无法确认买卖状态。",
                }
            raise AdvisorError(
                "STATUS_NOT_FOUND",
                f"申购状态表中未找到基金 {fund['code']}，当前无法确认",
            )

        subscription_status = json_value(row.get("申购状态"))
        redemption_status = json_value(row.get("赎回状态"))
        exchange = self._is_exchange_record(fund, row)
        common = {
            "confirmed": True,
            "mode": "exchange" if exchange else "off_exchange",
            "source_report_date": json_value(
                row.get("最新净值/万份收益-报告时间")
            ),
            "latest_nav_or_income": rounded(row.get("最新净值/万份收益"), 4),
        }

        if exchange:
            session = self._market_session()
            standard_market_open_now = (
                session.get("standard_market_open_now")
                if session is not None
                else None
            )
            common["exchange"] = {
                "source_subscription_status": subscription_status,
                "source_redemption_status": redemption_status,
                "market_session": session,
                "standard_market_open_now": standard_market_open_now,
                "can_submit_standard_session_order": standard_market_open_now,
                "can_buy_now": None,
                "can_sell_now": None,
                "note": (
                    "standard_market_open_now 只判断交易日和标准时段；"
                    "can_buy_now/can_sell_now 保持 null，因为未确认停牌、"
                    "券商通道、产品权限、流动性或最小交易单位。"
                ),
            }
            return common

        raw_limit = optional_float(row.get("日累计限定金额"))
        effective_limit = (
            None if raw_limit is not None and raw_limit >= 10_000_000_000 else raw_limit
        )
        common["off_exchange"] = {
            "subscription_status": subscription_status,
            "redemption_status": redemption_status,
            "can_submit_subscription": operation_is_open(subscription_status),
            "can_submit_redemption": operation_is_open(redemption_status),
            "next_open_date": json_value(row.get("下一开放日")),
            "minimum_purchase_cny": rounded(row.get("购买起点")),
            "daily_limit_cny": rounded(effective_limit),
            "source_daily_limit_cny": rounded(raw_limit),
            "purchase_fee_pct": rounded(row.get("手续费")),
            "note": (
                "状态表示业务是否开放，不保证立即确认。截止时间、确认日、到账日、"
                "持有期锁定和平台规则需核对基金公告及销售平台。"
            ),
        }
        return common

    def status(self, query: str) -> Dict[str, Any]:
        fund = self.resolve(query)
        return {
            "ok": True,
            "action": "status",
            "fund": fund,
            "availability": self._status_for_fund(fund),
        }

    def _historical_metrics(
        self,
        fund: Dict[str, Any],
        availability: Dict[str, Any],
        years: int,
    ) -> Tuple[Dict[str, Any], str, str]:
        fund_type = str(fund.get("type") or "")
        if "货币" in fund_type:
            frame = self._call(
                "fund_open_fund_info_em",
                "东方财富-开放式基金净值",
                self.ak.fund_open_fund_info_em,
                symbol=fund["code"],
                indicator="7日年化收益率",
                period="成立来",
                required_columns=["净值日期", "7日年化收益率"],
            )
            metrics = calculate_yield_metrics(frame, "净值日期", "7日年化收益率")
            return (
                metrics,
                "seven_day_annualized_yield",
                "七日年化收益率会波动，不代表未来实际收益。",
            )

        if (
            availability.get("mode") == "exchange"
            or self._is_exchange_record(fund, None)
        ):
            start = (self.now.date() - timedelta(days=years * 366)).strftime("%Y%m%d")
            end = self.now.date().strftime("%Y%m%d")
            upper_name = str(fund.get("name") or "").upper()
            if "LOF" in upper_name:
                history_interface = "fund_lof_hist_em"
                history_function = self.ak.fund_lof_hist_em
                history_upstream = "东方财富-LOF 历史行情"
            elif "ETF" in upper_name:
                history_interface = "fund_etf_hist_em"
                history_function = self.ak.fund_etf_hist_em
                history_upstream = "东方财富-ETF 历史行情"
            else:
                history_interface = None
                history_function = None
                history_upstream = None
                self._warn(
                    "exchange_history",
                    AdvisorError(
                        "UNSUPPORTED_EXCHANGE_FUND",
                        "无法确认场内基金类型，未调用 ETF 或 LOF 专用历史接口",
                        {"fund_code": fund["code"], "fund_name": fund.get("name")},
                    ),
                )
            frame = (
                self._call(
                    history_interface,
                    history_upstream,
                    history_function,
                    symbol=fund["code"],
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="qfq",
                    optional=True,
                )
                if history_interface is not None
                else None
            )
            if frame is not None and not frame.empty:
                try:
                    metrics = calculate_metrics(frame, "日期", "收盘", years)
                    return (
                        metrics,
                        "exchange_qfq_close",
                        f"收益和回撤按 {history_interface} 返回的场内前复权收盘价计算。",
                    )
                except AdvisorError as exc:
                    self._warn(history_interface, exc)
            elif "ETF" in upper_name:
                market_prefix = "sh" if fund["code"].startswith(("5", "6")) else "sz"
                sina_symbol = f"{market_prefix}{fund['code']}"
                sina_frame = self._call(
                    "fund_etf_hist_sina",
                    "新浪财经-ETF 日行情",
                    self.ak.fund_etf_hist_sina,
                    symbol=sina_symbol,
                    optional=True,
                )
                if sina_frame is not None:
                    metrics = calculate_metrics(
                        sina_frame,
                        "date",
                        "close",
                        years,
                    )
                    return (
                        metrics,
                        "exchange_unadjusted_close_sina",
                        (
                            "东方财富 ETF 历史接口失败；改用 fund_etf_hist_sina "
                            "返回的未复权场内收盘价，来源和口径已单独标注。"
                        ),
                    )

        frame = self._call(
            "fund_open_fund_info_em",
            "东方财富-开放式基金净值",
            self.ak.fund_open_fund_info_em,
            symbol=fund["code"],
            indicator="累计净值走势",
            period="成立来",
            required_columns=["净值日期", "累计净值"],
            allow_empty=True,
        )
        if frame.empty:
            frame = self._call(
                "fund_open_fund_info_em",
                "东方财富-开放式基金净值",
                self.ak.fund_open_fund_info_em,
                symbol=fund["code"],
                indicator="单位净值走势",
                period="成立来",
                required_columns=["净值日期", "单位净值"],
            )
            return (
                calculate_metrics(frame, "净值日期", "单位净值", years),
                "unit_nav",
                "单位净值变化可能受分红和拆分影响，不等同于投资者实际收益。",
            )
        return (
            calculate_metrics(frame, "净值日期", "累计净值", years),
            "accumulated_nav",
            "累计净值用于历史观察；实际收益仍受申赎时间、费用和分红方式影响。",
        )

    def _etf_spot(self, fund: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if "ETF" not in str(fund.get("name") or "").upper():
            return None
        frame = self._etf_spots()
        if frame is None or frame.empty or "代码" not in frame:
            return None
        matched = frame[frame["代码"].map(normalize_code).eq(fund["code"])]
        if matched.empty:
            return None
        row = matched.iloc[0]
        premium = premium_rate(row.get("最新价"), row.get("IOPV实时估值"))
        data_age = date_age_days(row.get("数据日期"), self.now.date())
        usable_for_current_decision = (
            data_age is not None and 0 <= data_age <= 3
        )
        if not usable_for_current_decision:
            self._warn(
                "fund_etf_spot_em",
                AdvisorError(
                    "STALE_OR_INVALID_DATA",
                    "ETF 行情日期异常或已过期，不用于当前溢价决策",
                    {
                        "fund_code": fund["code"],
                        "data_date": json_value(row.get("数据日期")),
                        "data_age_days": data_age,
                    },
                ),
            )
        return {
            "date": json_value(row.get("数据日期")),
            "data_age_days": data_age,
            "usable_for_current_decision": usable_for_current_decision,
            "updated_at": json_value(row.get("更新时间")),
            "latest_price": rounded(row.get("最新价"), 4),
            "iopv": rounded(row.get("IOPV实时估值"), 4),
            "premium_rate_pct": premium,
            "premium_level": premium_level(premium),
            "premium_formula": "(latest_price - iopv) / iopv",
            "source_raw_discount_rate_pct": rounded(row.get("基金折价率")),
            "change_pct": rounded(row.get("涨跌幅")),
            "turnover_cny": rounded(row.get("成交额")),
            "turnover_rate_pct": rounded(row.get("换手率")),
            "bid_1": rounded(row.get("买一"), 4),
            "ask_1": rounded(row.get("卖一"), 4),
            "classification": {
                "latest_price": "source_fact",
                "iopv": "source_fact",
                "source_raw_discount_rate_pct": "source_fact",
                "premium_rate_pct": "deterministic_derived_metric",
            },
        }

    @staticmethod
    def _strategy_output(
        fund: Dict[str, Any],
        availability: Dict[str, Any],
        metrics: Dict[str, Any],
        spot: Optional[Dict[str, Any]],
        valuation: Dict[str, Any],
        profile: Optional[Dict[str, Any]],
        metric_basis: str,
    ) -> Dict[str, Any]:
        history_percentile = metrics.get("history_position_percentile")
        history_level = metrics.get("history_position_level", "unknown")
        pe_metric = valuation.get("pe_ttm") or {}
        pb_metric = valuation.get("pb") or {}
        pe_percentile = pe_metric.get("percentile")
        pb_percentile = pb_metric.get("percentile")
        pe_level = pe_metric.get("level", "unknown")
        pb_level = pb_metric.get("level", "unknown")
        primary_percentile = pe_percentile
        primary_level = pe_level if pe_percentile is not None else "unknown"
        primary_basis = (
            "pe_ttm_percentile"
            if pe_percentile is not None
            else "no_reliable_valuation_signal"
        )
        trend = metrics.get("trend", "unknown")
        premium = (
            (spot or {}).get("premium_rate_pct")
            if (spot or {}).get("usable_for_current_decision", False)
            else None
        )
        fund_text = " ".join(
            [
                str(fund.get("name") or ""),
                str(fund.get("type") or ""),
                str((profile or {}).get("investment_type") or ""),
            ]
        )
        is_money = "货币" in fund_text
        is_bond = "债券" in fund_text
        matched_broad_index = valuation.get("index_name")

        position_assessment = {
            "primary_basis": primary_basis,
            "primary_percentile": primary_percentile,
            "primary_level": primary_level,
            "history_position_percentile": history_percentile,
            "history_position_level": history_level,
            "pe_ttm_percentile": pe_percentile,
            "pe_ttm_level": pe_level,
            "pb_percentile": pb_percentile,
            "pb_level": pb_level,
            "combined_valuation_percentile": None,
            "trend": trend,
            "confidence": (
                valuation.get("confidence", "high")
                if pe_percentile is not None
                else ("low" if metric_basis == "accumulated_nav" else "medium")
            ),
            "interpretation": (
                "有可匹配指数时，以 PE TTM 分位为主要盈利估值参考，PB 单独辅助解释，二者不平均。"
                if pe_percentile is not None
                else "只能判断历史净值/价格位置，不能据此断言低估或高估。"
            ),
        }

        buy_reasons: List[str] = []
        if is_money:
            buy_code = "cash_management_not_timing"
            buy_reasons.append("货币基金主要比较流动性、费率和收益率，不适合按净值高低择时。")
        elif (
            premium is not None
            and premium > ETF_PREMIUM_PAUSE_THRESHOLD_PCT
        ):
            buy_code = "avoid_current_exchange_premium"
            buy_reasons.append("场内溢价超过 5%，当前价格显著高于 IOPV。")
        elif pe_percentile is not None and primary_level == "high":
            buy_code = "small_dca_or_wait"
            buy_reasons.append("PE TTM 处于长期高分位，新增资金不宜一次性投入。")
        elif pe_percentile is not None and primary_level in {"low", "lower_middle"} and trend == "down":
            buy_code = "small_batches_wait_for_stabilization"
            buy_reasons.append("PE TTM 偏低但趋势仍弱，适合维持基础定投并保留现金。")
        elif pe_percentile is not None and primary_level in {"low", "lower_middle"}:
            buy_code = "normal_or_increased_dca"
            buy_reasons.append("PE TTM 偏低且趋势未继续恶化，可考虑小幅估值倾斜。")
        else:
            buy_code = "base_dca_no_valuation_signal"
            buy_reasons.append("缺少可靠估值信号，按产品质量、目标仓位和现金流执行基础定投。")
        if trend == "up":
            buy_reasons.append("趋势偏强，但上涨趋势不是继续上涨的保证。")
        elif trend == "down":
            buy_reasons.append("趋势偏弱，应预留继续回撤和验证基本逻辑的空间。")

        if pe_percentile is not None and primary_level == "high":
            sell_code = "review_rebalance_if_overweight"
            sell_summary = "若仓位已超过目标或资金目标已达到，可考虑分批再平衡，不应仅因创新高全部卖出。"
        elif pe_percentile is not None and primary_level in {"low", "lower_middle"} and trend == "down":
            sell_code = "do_not_panic_sell_without_thesis_review"
            sell_summary = "低位下跌不自动构成卖点；先检查基金逻辑、经理、配置需求和可承受回撤。"
        else:
            sell_code = "hold_or_rebalance_to_target"
            sell_summary = "没有成本、仓位和期限时不判断具体卖点，优先按目标资产比例再平衡。"

        dca_action, dca_basis = dca_action_band(
            pe_percentile,
            trend,
            premium,
        )
        if is_money:
            dca_suitability = "not_needed"
            dca_action = "cash_management_not_dca"
            dca_basis = "cash_management"
        elif is_bond:
            dca_suitability = "optional_for_cash_flow_matching"
        elif matched_broad_index:
            dca_suitability = "generally_suitable_for_long_horizon"
        else:
            dca_suitability = "conditional_on_fund_quality_and_allocation_need"

        execution_notes: List[str] = []
        if availability.get("mode") == "off_exchange":
            off_exchange = availability.get("off_exchange") or {}
            if off_exchange.get("can_submit_subscription") is False:
                execution_notes.append("当前申购业务未开放，策略档位暂时无法执行。")
            if off_exchange.get("daily_limit_cny") is not None:
                execution_notes.append("存在日累计申购限额。")
        elif availability.get("mode") == "exchange":
            execution_notes.append("场内执行还需满足交易时段、流动性和券商规则。")

        return {
            "position_assessment": position_assessment,
            "decision_reference": {
                "classification": "rule_based_policy_not_market_data",
                "buy": {
                    "code": buy_code,
                    "summary": buy_reasons[0],
                    "reasons": buy_reasons,
                },
                "sell": {
                    "code": sell_code,
                    "summary": sell_summary,
                    "required_user_inputs": [
                        "持仓成本",
                        "当前仓位及目标仓位",
                        "计划持有年限",
                        "资金用途",
                        "最大可承受回撤",
                    ],
                },
                "rule": "位置和估值只用于制定分批条件，不构成确定性买卖指令。",
            },
            "dca_plan": {
                "classification": "rule_based_policy_not_market_data",
                "suitability": dca_suitability,
                "base_amount_definition": "用户计划的常规定投金额，记为 1.0 倍。",
                "suggested_frequency": (
                    "不适用，按现金管理需求配置"
                    if is_money
                    else (
                        "每月 1 次"
                        if is_bond
                        else "每月 1-2 次，固定日期，不追逐单日涨跌"
                    )
                ),
                "current_action": dca_action,
                "action_basis": dca_basis,
                "amount_policy": (
                    "不输出机械倍数。先确定每期预算和目标仓位，再在基础定投、"
                    "减量定投、暂停当前场内渠道、小幅估值倾斜之间选择。"
                ),
                "drawdown_rule": [
                    {
                        "condition": "出现回撤但基本面、跟踪标的和目标仓位未变化",
                        "action": "维持基础定投；回撤本身不构成自动加码理由",
                    },
                    {
                        "condition": "PE 处于长期低分位且趋势不再恶化",
                        "action": "只允许小幅估值倾斜，并保留后续现金",
                    },
                    {
                        "condition": "基金逻辑、经理、跟踪标的或家庭现金流变化",
                        "action": "停止机械加仓，重新评估产品和风险承受能力",
                    },
                ],
                "pause_conditions": [
                    "场内溢价率 > 5%",
                    "未来 3 年内需要使用该资金",
                    "没有 3-6 个月应急资金",
                    "基金经理、投资策略或跟踪标的发生重大变化",
                    "该类资产已经超过目标仓位",
                ],
                "execution_notes": execution_notes,
                "required_user_inputs": [
                    "每期可投资预算",
                    "当前仓位与目标仓位",
                    "至少 3-5 年资金期限",
                    "应急资金是否充足",
                    "最大可承受回撤",
                ],
                "note": "定投首先是现金流和资产配置纪律，估值只用于小幅调整节奏。",
            },
        }

    def analyze(
        self,
        query: str,
        years: int = 3,
        include_spot: bool = True,
    ) -> Dict[str, Any]:
        audit_start = len(self.data_audit)
        warning_start = len(self.data_warnings)
        fund = self.resolve(query)
        availability = self._status_for_fund(fund, optional=True)
        metrics, metric_basis, basis_note = self._historical_metrics(
            fund,
            availability,
            years,
        )
        latest_age = metrics.get("latest_age_days")
        if latest_age is None or latest_age < 0 or latest_age > 10:
            raise AdvisorError(
                "STALE_OR_INVALID_DATA",
                "基金历史序列最新日期异常或数据已过期，拒绝生成当前买卖参考",
                {
                    "latest_date": json_value(metrics.get("latest_date")),
                    "latest_age_days": latest_age,
                    "metric_basis": metric_basis,
                },
            )
        profile = self._fund_profile(fund)
        rating = self._fund_rating(fund, optional=True)
        valuation = self._index_valuation(fund, profile, 10)
        spot = self._etf_spot(fund) if include_spot else None
        fund_text = " ".join(
            [
                str(fund.get("name") or ""),
                str(fund.get("type") or ""),
                str((profile or {}).get("investment_type") or ""),
            ]
        )
        portfolio = (
            {
                "asset_allocation": None,
                "stock_concentration": None,
            }
            if "货币" in fund_text
            else self._portfolio_snapshot(fund)
        )
        strategy = self._strategy_output(
            fund,
            availability,
            metrics,
            spot,
            valuation,
            profile,
            metric_basis,
        )
        available_metrics = [
            "长期收益与风险路径",
            "当前回撤和最大回撤修复信息",
            "月度收益统计",
            "滚动250日收益分布",
        ]
        missing_metrics: List[str] = []
        if profile and profile.get("derived", {}).get("known_ongoing_fee_pct") is not None:
            available_metrics.append("管理费与托管费")
        else:
            missing_metrics.append("可核验的持续费率")
        if profile and profile.get("derived", {}).get("share_scale_yi_units") is not None:
            available_metrics.append("份额规模")
        else:
            missing_metrics.append("份额规模")
        if rating and any(
            value is not None
            for value in rating.get("ratings", {}).values()
        ):
            available_metrics.append("第三方基金评级")
        else:
            missing_metrics.append("第三方基金评级")
        missing_metrics.append("基金净资产规模")
        if portfolio.get("asset_allocation"):
            available_metrics.append("报告期资产配置")
        else:
            missing_metrics.append("最新资产配置")
        if portfolio.get("stock_concentration"):
            available_metrics.append("前十大股票持仓集中度")
        else:
            missing_metrics.append("前十大股票持仓集中度")
        if valuation.get("available"):
            available_metrics.append("匹配指数的历史 PE/PB")
        elif "指数" in fund_text or "ETF" in fund_text:
            missing_metrics.append("可可靠匹配的底层指数估值")
        if "指数" in fund_text or "ETF" in fund_text:
            missing_metrics.extend(["跟踪误差", "跟踪差异"])
        else:
            missing_metrics.extend(["基金经理任职变化", "相对业绩基准超额收益"])
        metric_coverage = {
            "available": available_metrics,
            "missing_or_not_reliably_available": missing_metrics,
            "rule": "缺失指标不得由模型推断或用近似指标替代。",
        }
        operation_audit = self.data_audit[audit_start:]
        operation_warnings = self.data_warnings[warning_start:]

        def audit_view(
            interfaces: Optional[set[str]] = None,
            supplemental: Optional[Sequence[Dict[str, Any]]] = None,
        ) -> List[Dict[str, Any]]:
            selected = [
                item
                for item in operation_audit
                if interfaces is None or item.get("interface") in interfaces
            ]
            for item in supplemental or []:
                if (
                    (interfaces is None or item.get("interface") in interfaces)
                    and item not in selected
                ):
                    selected.append(item)
            return [
                {
                    key: item[key]
                    for key in (
                        "interface",
                        "parameters",
                        "validation",
                        "frame_sha256",
                        "error",
                    )
                    if key in item
                }
                for item in selected
            ]

        def warning_view(
            interfaces: Optional[set[str]] = None,
        ) -> List[Dict[str, Any]]:
            return [
                item
                for item in operation_warnings
                if interfaces is None or item.get("interface") in interfaces
            ]

        def group_metadata(
            basis: str,
            as_of: Any,
            interfaces: Optional[set[str]] = None,
            supplemental_audit: Optional[
                Sequence[Dict[str, Any]]
            ] = None,
        ) -> Dict[str, Any]:
            return {
                "metric_basis": basis,
                "as_of": json_value(as_of),
                "data_audit": audit_view(interfaces, supplemental_audit),
                "warnings": warning_view(interfaces),
            }

        product_interfaces = {
            "fund_info_ths",
            "fund_rating_all",
            "fund_individual_detail_hold_xq",
            "fund_portfolio_hold_em",
        }
        performance_interfaces = {
            "fund_open_fund_info_em",
            "fund_etf_hist_em",
            "fund_lof_hist_em",
            "fund_etf_hist_sina",
        }
        valuation_interfaces = {
            "stock_index_pe_lg",
            "stock_index_pb_lg",
        }
        trading_interfaces = {
            "fund_purchase_em",
            "tool_trade_date_hist_sina",
            "fund_etf_spot_em",
        }
        allocation = portfolio.get("asset_allocation")
        concentration = portfolio.get("stock_concentration")
        product_as_of = {
            "profile": None,
            "rating": None,
            "asset_allocation": (
                allocation.get("report_date")
                if isinstance(allocation, dict)
                else None
            ),
            "stock_concentration": (
                concentration.get("report_period")
                if isinstance(concentration, dict)
                else None
            ),
        }
        performance_as_of = metrics.get("latest_date")
        valuation_as_of = {
            "pe_ttm": (valuation.get("pe_ttm") or {}).get("latest_date"),
            "pb": (valuation.get("pb") or {}).get("latest_date"),
        }
        valuation_audit = self._valuation_audit_cache.get(
            (str(valuation.get("index_name") or ""), 10),
            [],
        )
        trading_as_of = {
            "status": availability.get("source_report_date"),
            "market_snapshot": (spot or {}).get("date"),
        }
        performance = {
            "returns_pct": metrics.get("returns_pct"),
            "annualized_volatility_pct": metrics.get(
                "annualized_volatility_pct"
            ),
            "current_drawdown_pct": metrics.get("current_drawdown_pct"),
            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
            "positive_day_ratio_pct": metrics.get("positive_day_ratio_pct"),
            "history_position_percentile": metrics.get(
                "history_position_percentile"
            ),
            "holding_experience": metrics.get("holding_experience"),
            "latest_date": performance_as_of,
            **group_metadata(
                metric_basis,
                performance_as_of,
                performance_interfaces,
            ),
        }
        valuation_analysis = {
            **valuation,
            **group_metadata(
                (
                    "matched_index_pe_ttm_and_pb"
                    if valuation.get("available")
                    else "unavailable"
                ),
                valuation_as_of,
                valuation_interfaces,
                valuation_audit,
            ),
        }
        analysis = {
            "identity": fund,
            "product_profile": {
                "profile": profile,
                "rating": rating,
                "portfolio_snapshot": portfolio,
                **group_metadata(
                    "source_product_facts_and_disclosed_holdings",
                    product_as_of,
                    product_interfaces,
                    self._rating_audit,
                ),
            },
            "performance": performance,
            "holding_experience": metrics.get("holding_experience"),
            "valuation": valuation_analysis,
            "trading_context": {
                "basis_note": basis_note,
                "execution_status": availability,
                "market_snapshot": spot,
                **group_metadata(
                    metric_basis,
                    trading_as_of,
                    trading_interfaces,
                ),
            },
            "data_quality": {
                "lookback_years": years,
                "latest_date": performance_as_of,
                "latest_age_days": latest_age,
                "metric_coverage": metric_coverage,
                **group_metadata(
                    "data_quality_metadata",
                    performance_as_of,
                ),
            },
        }
        return {
            "ok": True,
            "action": "analyze",
            "fund": fund,
            "fund_profile": profile,
            "fund_rating": rating,
            "lookback_years": years,
            "valuation_lookback_years": 10,
            "metric_basis": metric_basis,
            "basis_note": basis_note,
            "metrics": metrics,
            "index_valuation": valuation,
            "market_snapshot": spot,
            "portfolio_snapshot": portfolio,
            "metric_coverage": metric_coverage,
            "analysis": analysis,
            **strategy,
            "execution_status": availability,
            "data_integrity": {
                "ai_generated_market_data": False,
                "raw_facts": "仅来自 sources 和 data_audit 中列出的接口",
                "derived_metrics": "仅由脚本执行确定性公式",
                "decision_policy": "定投动作区间与买卖文字是规则模板，不是行情数据",
            },
            "investor_inputs_required": [
                "投资目标",
                "计划持有期限",
                "每期可投资现金流",
                "当前资产配置和目标仓位",
                "应急资金是否覆盖 3-6 个月支出",
                "最大可承受回撤",
            ],
            "metric_guide": {
                "annualized_return_pct": "观察区间首尾值折算的复合年化增长，不代表未来收益。",
                "annualized_volatility_pct": "日收益波动年化值，越高表示持有过程波动越大。",
                "downside_volatility_pct": "只统计负收益波动，更接近亏损体验。",
                "max_drawdown_detail": "历史最深回撤及其峰值、谷值和修复时间。",
                "longest_underwater_days": "净值低于此前高点的最长持续日历时间。",
                "rolling_250_observation_return_statistics": "不同历史时点近似持有一年的结果分布。",
                "pe_ttm_percentile": "底层指数当前滚动PE在所选历史窗口的位置。",
                "pb_percentile": "底层指数当前PB历史位置，与PE分开解释。",
                "premium_rate_pct": "ETF场内价格相对IOPV的偏离，正数为溢价。",
            },
        }

    def profile(self, query: str) -> Dict[str, Any]:
        """基金档案：基本信息 + 费率规则 + 资产配置。

        全部来自雪球系稳定接口，逐接口审计并带 frame_sha256。任一接口失败走
        optional 降级为 warning，不猜测、不补值；三个接口全部失败时抛出
        CANNOT_CONFIRM 级错误，绝不虚构产品条款。
        """
        fund = self.resolve(query)
        code = fund["code"]

        basic_frame = self._call(
            "fund_individual_basic_info_xq",
            "雪球-基金-基本信息",
            self.ak.fund_individual_basic_info_xq,
            symbol=code,
            optional=True,
        )
        fee_frame = self._call(
            "fund_individual_detail_info_xq",
            "雪球-基金-费率与买卖规则",
            self.ak.fund_individual_detail_info_xq,
            symbol=code,
            optional=True,
        )
        hold_frame = self._call(
            "fund_individual_detail_hold_xq",
            "雪球-基金-资产配置",
            self.ak.fund_individual_detail_hold_xq,
            symbol=code,
            optional=True,
        )

        basic_info = self._item_value_pairs(basic_frame)
        fee_rules = (
            [
                {
                    "fee_type": json_value(row.get("费用类型")),
                    "condition": json_value(row.get("条件或名称")),
                    "fee": optional_float(row.get("费用")),
                }
                for _, row in fee_frame.iterrows()
            ]
            if fee_frame is not None
            else []
        )
        allocation = (
            [
                {
                    "asset_type": json_value(row.get("资产类型")),
                    "weight_pct": optional_float(row.get("仓位占比")),
                }
                for _, row in hold_frame.iterrows()
            ]
            if hold_frame is not None
            else []
        )

        if basic_frame is None and fee_frame is None and hold_frame is None:
            raise AdvisorError(
                "DATA_SOURCE_ERROR",
                "基金档案接口均失败，当前无法确认产品事实",
                {"fund_code": code},
            )

        return {
            "ok": True,
            "action": "profile",
            "fund": fund,
            "basic_info": basic_info,
            "fee_rules": fee_rules,
            "asset_allocation": allocation,
            "notes": (
                "产品事实来自雪球实时接口；费率与买卖规则不是当前市场数值，"
                "交易前请以基金公告和销售平台为准。"
            ),
        }

    def rating(self, query: str) -> Dict[str, Any]:
        """基金评级：多家机构评级 + 类型。

        评级全量接口按代码精确过滤，未命中返回 NOT_FOUND，不做近似匹配，
        避免把评级张冠李戴到别的基金。
        """
        fund = self.resolve(query)
        rating = self._fund_rating(fund, optional=False)
        if rating is None:
            raise AdvisorError(
                "DATA_SOURCE_ERROR",
                "基金评级接口当前无法确认",
                {"fund_code": fund["code"]},
            )
        return {
            "ok": True,
            "action": "rating",
            "fund": fund,
            **rating,
        }

    @staticmethod
    def _item_value_pairs(frame: Optional[pd.DataFrame]) -> Dict[str, Any]:
        if frame is None or frame.empty:
            return {}
        return {
            str(row.get("item")): json_value(row.get("value"))
            for _, row in frame.iterrows()
            if row.get("item")
        }

    def compare(self, queries: Sequence[str], years: int = 3) -> Dict[str, Any]:
        flattened: List[str] = []
        for query in queries:
            flattened.extend(item.strip() for item in query.split(",") if item.strip())
        if not 2 <= len(flattened) <= 5:
            raise AdvisorError(
                "INVALID_ARGUMENT",
                "compare 需要 2 到 5 只基金",
                {"received": len(flattened)},
            )

        results: List[Dict[str, Any]] = []
        for query in flattened:
            try:
                results.append(self.analyze(query, years=years, include_spot=True))
            except AdvisorError as exc:
                results.append(
                    {
                        "ok": False,
                        "query": query,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                        },
                    }
                )

        successful = [item for item in results if item.get("ok")]

        def share_class(item: Dict[str, Any]) -> Optional[str]:
            name = str(item.get("fund", {}).get("name") or "").strip()
            matched = re.search(r"([AC])(?:类)?[）)]?$", name, re.IGNORECASE)
            return matched.group(1).upper() if matched else None

        def benchmark(item: Dict[str, Any]) -> Optional[str]:
            value = (item.get("fund_profile") or {}).get("benchmark")
            text = str(value or "").strip()
            return text or None

        def all_same(values: Sequence[Optional[str]]) -> Optional[bool]:
            if not values or any(value is None for value in values):
                return None
            return len(set(values)) == 1

        fund_types = [
            str(item["fund"].get("type") or "").strip() or None
            for item in successful
        ]
        share_classes = [share_class(item) for item in successful]
        metric_bases = [
            str(item.get("metric_basis") or "").strip() or None
            for item in successful
        ]
        benchmarks = [benchmark(item) for item in successful]
        checks = {
            "same_reported_fund_type": all_same(fund_types),
            "same_share_class": all_same(share_classes),
            "same_metric_basis": all_same(metric_bases),
            "same_tracking_or_benchmark": all_same(benchmarks),
        }
        comparison_ready = (
            len(successful) == len(results)
            and bool(successful)
            and all(value is True for value in checks.values())
        )

        def comparison_row(item: Dict[str, Any]) -> Dict[str, Any]:
            metrics = item.get("metrics") or {}
            experience = metrics.get("holding_experience") or {}
            profile = item.get("fund_profile") or {}
            rating = item.get("fund_rating") or {}
            portfolio = item.get("portfolio_snapshot") or {}
            allocation = portfolio.get("asset_allocation")
            if isinstance(allocation, dict):
                allocation_items = allocation.get("items")
            elif isinstance(allocation, list):
                allocation_items = allocation
            else:
                allocation_items = None
            return {
                "fund_code": item["fund"].get("code"),
                "fund_name": item["fund"].get("name"),
                "fund_type": item["fund"].get("type"),
                "share_class": share_class(item),
                "metric_basis": item.get("metric_basis"),
                "tracking_or_benchmark": benchmark(item),
                "as_of": metrics.get("latest_date"),
                "return_12_month_pct": (
                    (metrics.get("returns_pct") or {}).get("12_month")
                ),
                "annualized_return_pct": experience.get(
                    "annualized_return_pct"
                ),
                "max_drawdown_pct": metrics.get("max_drawdown_pct"),
                "annualized_volatility_pct": metrics.get(
                    "annualized_volatility_pct"
                ),
                "known_ongoing_fee_pct": (
                    (profile.get("derived") or {}).get(
                        "known_ongoing_fee_pct"
                    )
                ),
                "ratings": rating.get("ratings"),
                "asset_allocation": allocation_items,
            }

        comparison_rows = [comparison_row(item) for item in successful]

        def sorted_view(
            field: str,
            *,
            reverse: bool,
        ) -> List[Dict[str, Any]]:
            values = [
                {
                    "fund_code": row["fund_code"],
                    "fund_name": row["fund_name"],
                    "value": row[field],
                }
                for row in comparison_rows
                if isinstance(row.get(field), (int, float))
                and not isinstance(row.get(field), bool)
            ]
            return sorted(
                values,
                key=lambda row: row["value"],
                reverse=reverse,
            )

        sorted_views = (
            {
                "return_12_month_pct_desc": sorted_view(
                    "return_12_month_pct",
                    reverse=True,
                ),
                "annualized_return_pct_desc": sorted_view(
                    "annualized_return_pct",
                    reverse=True,
                ),
                "max_drawdown_pct_desc_shallower_first": sorted_view(
                    "max_drawdown_pct",
                    reverse=True,
                ),
                "annualized_volatility_pct_asc": sorted_view(
                    "annualized_volatility_pct",
                    reverse=False,
                ),
                "known_ongoing_fee_pct_asc": sorted_view(
                    "known_ongoing_fee_pct",
                    reverse=False,
                ),
            }
            if comparison_ready
            else {}
        )
        return {
            "ok": bool(successful),
            "action": "compare",
            "lookback_years": years,
            "results": results,
            "comparison_table": {
                "rows": comparison_rows,
                "sorting_applied": comparison_ready,
                "sorted_views": sorted_views,
                "sorting_policy": (
                    "仅在基金类型、份额类别、指标口径和跟踪标的/业绩基准均一致时排序；"
                    "缺失值不作为零参与排序。"
                ),
            },
            "comparability": {
                **checks,
                "reported_fund_types": fund_types,
                "share_classes": share_classes,
                "metric_bases": metric_bases,
                "tracking_or_benchmarks": benchmarks,
                "comparable_for_return_ranking": comparison_ready,
                "note": (
                    "不同基金类型、跟踪标的或指标口径不应直接按收益率排名；"
                    "分别比较估值、历史位置、收益、回撤、波动、费用、溢价和定投适配性。"
                ),
            },
        }

    def audit(
        self,
        fund_code: str = "000001",
        etf_code: str = "510300",
        lof_code: str = "166009",
        index_name: str = "沪深300",
    ) -> Dict[str, Any]:
        checks: List[Dict[str, Any]] = []

        def run_check(name: str, function: Any) -> Any:
            try:
                value = function()
                if value is None:
                    raise AdvisorError(
                        "AUDIT_CHECK_FAILED",
                        f"{name} 未返回可验证结果",
                    )
                checks.append({"check": name, "status": "passed"})
                return value
            except AdvisorError as exc:
                checks.append(
                    {
                        "check": name,
                        "status": "failed",
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "details": exc.details,
                        },
                    }
                )
                return None
            except Exception as exc:
                checks.append(
                    {
                        "check": name,
                        "status": "failed",
                        "error": {
                            "code": "UNEXPECTED_ERROR",
                            "message": str(exc),
                        },
                    }
                )
                return None

        names = run_check("fund_name_em_schema", self._names)
        if names is not None:
            for code, label in (
                (fund_code, "fund_code_in_name_table"),
                (etf_code, "etf_code_in_name_table"),
                (lof_code, "lof_code_in_name_table"),
            ):
                normalized = normalize_code(code)
                exists = names["基金代码"].map(normalize_code).eq(normalized).any()
                checks.append(
                    {
                        "check": label,
                        "status": "passed" if exists else "failed",
                        "requested_code": normalized,
                    }
                )

        run_check("fund_purchase_em_schema", self._purchases)
        fund = run_check("resolve_fund_identity", lambda: self.resolve(fund_code))
        if fund is not None:
            def require_profile() -> Dict[str, Any]:
                profile = self._fund_profile(fund)
                if profile is None:
                    raise AdvisorError(
                        "FUND_PROFILE_UNAVAILABLE",
                        "基金资料接口未通过代码一致性校验",
                    )
                return profile

            run_check("fund_info_ths_identity", require_profile)
            run_check(
                "fund_open_unit_nav_schema",
                lambda: self._call(
                    "fund_open_fund_info_em",
                    "东方财富-开放式基金净值",
                    self.ak.fund_open_fund_info_em,
                    symbol=fund["code"],
                    indicator="单位净值走势",
                    period="成立来",
                    required_columns=["净值日期", "单位净值", "日增长率"],
                ),
            )
            run_check(
                "fund_open_accumulated_nav_schema",
                lambda: self._call(
                    "fund_open_fund_info_em",
                    "东方财富-开放式基金净值",
                    self.ak.fund_open_fund_info_em,
                    symbol=fund["code"],
                    indicator="累计净值走势",
                    period="成立来",
                    required_columns=["净值日期", "累计净值"],
                ),
            )

        end = self.now.date().strftime("%Y%m%d")
        start = (self.now.date() - timedelta(days=45)).strftime("%Y%m%d")
        run_check(
            "fund_etf_hist_em_schema",
            lambda: self._call(
                "fund_etf_hist_em",
                "东方财富-ETF 历史行情",
                self.ak.fund_etf_hist_em,
                symbol=normalize_code(etf_code),
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            ),
        )
        run_check(
            "fund_lof_hist_em_schema",
            lambda: self._call(
                "fund_lof_hist_em",
                "东方财富-LOF 历史行情",
                self.ak.fund_lof_hist_em,
                symbol=normalize_code(lof_code),
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            ),
        )
        etf_market_prefix = "sh" if normalize_code(etf_code).startswith(("5", "6")) else "sz"
        run_check(
            "fund_etf_hist_sina_schema",
            lambda: self._call(
                "fund_etf_hist_sina",
                "新浪财经-ETF 日行情",
                self.ak.fund_etf_hist_sina,
                symbol=f"{etf_market_prefix}{normalize_code(etf_code)}",
            ),
        )
        run_check("fund_etf_spot_em_schema", self._etf_spots)
        run_check("tool_trade_date_hist_sina_schema", self._calendar)
        run_check(
            "stock_index_pe_pb_schema",
            lambda: self.valuation(
                index_name,
                years=3,
                max_points=50,
            ),
        )

        failed = [check for check in checks if check["status"] != "passed"]
        return {
            "ok": not failed,
            "action": "audit",
            "akshare_version": getattr(self.ak, "__version__", None),
            "strict_version": SUPPORTED_AKSHARE_VERSION,
            "representative_inputs": {
                "fund_code": normalize_code(fund_code),
                "etf_code": normalize_code(etf_code),
                "lof_code": normalize_code(lof_code),
                "index_name": index_name,
            },
            "checks": checks,
            "summary": {
                "passed": len(checks) - len(failed),
                "failed": len(failed),
                "all_contracts_passed": not failed,
            },
            "integrity_guarantees": [
                "仅调用真实 AKShare 接口，不使用 Mock 或硬编码行情数据",
                "字段缺失、空数据、版本不匹配和同日冲突值直接失败",
                "每个成功接口记录请求参数、返回列、行数和 SHA-256 指纹",
                "不插值、不前向填充、不由模型补造缺失数值",
            ],
        }

    def common_output(self) -> Dict[str, Any]:
        return {
            "queried_at": self.now,
            "timezone": "Asia/Shanghai",
            "akshare_version": getattr(self.ak, "__version__", None),
            "sources": self.sources,
            "data_audit": self.data_audit,
            "data_warnings": self.data_warnings,
            "data_policy": {
                "ai_may_generate_market_data": False,
                "missing_data_policy": "返回 null、warning 或 error，禁止猜测、插值或补值",
                "source_fact_policy": "所有源数据必须带接口、参数、字段、行数和 SHA-256 指纹",
                "derived_metric_policy": "只允许脚本按已声明公式计算，模型不得改写数值",
                "policy_output": "买卖与定投规则不是事实数据，必须与源数据分开解释",
            },
            "derived_formulas": {
                "trailing_return_pct": "(latest / prior_observation - 1) * 100",
                "current_drawdown_pct": "(latest / running_peak - 1) * 100",
                "max_drawdown_pct": "min(value / running_peak - 1) * 100",
                "annualized_volatility_pct": "std(daily_return, ddof=1) * sqrt(250) * 100",
                "annualized_return_pct": "((ending / beginning) ** (365.25 / elapsed_days) - 1) * 100",
                "downside_volatility_pct": "sqrt(mean(min(daily_return, 0) ** 2)) * sqrt(250) * 100",
                "calmar_ratio": "annualized_return_pct / abs(max_drawdown_pct)",
                "history_percentile": "count(observation <= current) / observation_count * 100",
                "premium_rate_pct": "(latest_price - iopv) / iopv * 100",
                "valuation_policy": "PE_TTM 与 PB 分别计算分位，禁止简单平均",
            },
            "disclaimer": (
                "仅供信息研究和风险参考，不构成投资建议或收益承诺；"
                "交易前请核对基金公告和销售/券商平台。"
            ),
        }


def bounded_integer(minimum: int, maximum: int) -> Any:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("必须是整数") from exc
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(
                f"必须在 {minimum} 到 {maximum} 之间"
            )
        return parsed

    return parse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AKShare 基金高低位、买卖条件、定投策略和执行状态分析"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    search_parser = subparsers.add_parser("search", help="按代码、名称或拼音搜索")
    search_parser.add_argument("--query", required=True, help="基金代码、名称或拼音")
    search_parser.add_argument("--limit", type=int, default=10, choices=range(1, 21))

    status_parser = subparsers.add_parser("status", help="查询申购、赎回或场内时段")
    status_parser.add_argument("--fund", required=True, help="明确代码或唯一基金名称")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="查询高低位、买卖条件、风险和定投策略",
    )
    analyze_parser.add_argument("--fund", required=True, help="明确代码或唯一基金名称")
    analyze_parser.add_argument("--years", type=int, default=3, choices=(1, 3, 5))

    valuation_parser = subparsers.add_parser(
        "valuation",
        help="生成 AKShare 指数历史 PE/PB 图表数据",
    )
    valuation_parser.add_argument(
        "--index",
        required=True,
        help="AKShare 支持的指数名称、别名或对应指数代码",
    )
    valuation_parser.add_argument(
        "--years",
        type=int,
        default=10,
        choices=(3, 5, 10, 20),
    )
    valuation_parser.add_argument(
        "--max-points",
        type=bounded_integer(50, 3000),
        default=600,
        metavar="50..3000",
        help="每张图返回的最大数据点数（50 到 3000）",
    )

    audit_parser = subparsers.add_parser(
        "audit",
        help="调用真实接口并审计版本、字段、样本和数据指纹",
    )
    audit_parser.add_argument("--fund", default="000001")
    audit_parser.add_argument("--etf", default="510300")
    audit_parser.add_argument("--lof", default="166009")
    audit_parser.add_argument("--index", default="沪深300")

    compare_parser = subparsers.add_parser("compare", help="比较 2 到 5 只基金")
    compare_parser.add_argument("--funds", required=True, nargs="+")
    compare_parser.add_argument("--years", type=int, default=3, choices=(1, 3, 5))

    profile_parser = subparsers.add_parser(
        "profile",
        help="基金档案：基本信息、费率规则和资产配置",
    )
    profile_parser.add_argument("--fund", required=True, help="明确代码或唯一基金名称")

    rating_parser = subparsers.add_parser(
        "rating",
        help="基金评级：多家机构评级和类型",
    )
    rating_parser.add_argument("--fund", required=True, help="明确代码或唯一基金名称")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    advisor: Optional[FundAdvisor] = None
    try:
        advisor = FundAdvisor()
        if args.action == "search":
            payload = advisor.search(args.query, args.limit)
        elif args.action == "status":
            payload = advisor.status(args.fund)
        elif args.action == "analyze":
            payload = advisor.analyze(args.fund, args.years)
        elif args.action == "valuation":
            payload = advisor.valuation(
                args.index,
                args.years,
                args.max_points,
            )
        elif args.action == "audit":
            payload = advisor.audit(
                args.fund,
                args.etf,
                args.lof,
                args.index,
            )
        elif args.action == "profile":
            payload = advisor.profile(args.fund)
        elif args.action == "rating":
            payload = advisor.rating(args.fund)
        else:
            payload = advisor.compare(args.funds, args.years)
        payload.update(advisor.common_output())
        print(
            json.dumps(
                json_value(payload),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return 0 if payload.get("ok") else 1
    except AdvisorError as exc:
        payload = {
            "ok": False,
            "action": getattr(args, "action", None),
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
            "queried_at": datetime.now(SHANGHAI),
            "documentation_url": AKSHARE_DOC,
        }
        if advisor is not None:
            payload.update(advisor.common_output())
        print(
            json.dumps(
                json_value(payload),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return 1
    except Exception as exc:
        payload = {
            "ok": False,
            "action": getattr(args, "action", None),
            "error": {
                "code": "UNEXPECTED_ERROR",
                "message": "运行失败，当前无法确认基金信息",
                "details": {"reason": str(exc)},
            },
            "queried_at": datetime.now(SHANGHAI),
        }
        if advisor is not None:
            payload.update(advisor.common_output())
        print(
            json.dumps(
                json_value(payload),
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
