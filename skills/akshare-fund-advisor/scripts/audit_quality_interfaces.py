#!/usr/bin/env python3
"""Audit candidate AKShare interfaces for asset-quality screening."""

from __future__ import annotations

import argparse
import inspect
import io
import json
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from fund_advisor import (  # noqa: E402
    SHANGHAI,
    SUPPORTED_AKSHARE_VERSION,
    deadline,
    frame_fingerprint,
)


class AuditContractError(ValueError):
    """A candidate interface violated the discovery audit contract."""


@dataclass(frozen=True)
class AuditContext:
    as_of: date
    stock_code: str
    fund_code: str
    etf_code: str
    industry_board: str
    report_date: str
    fund_year: str
    timeout_seconds: int
    attempts: int


@dataclass(frozen=True)
class Candidate:
    interface: str
    group: str
    purpose: str
    recommendation: str
    required_columns: tuple[str, ...]
    arguments: Callable[[AuditContext], dict[str, Any]]


def qualified_stock_code(code: str, *, suffix: bool) -> str:
    market = "SH" if code.startswith(("5", "6", "9")) else "SZ"
    return f"{code}.{market}" if suffix else f"{market}{code}"


def candidate_interfaces() -> tuple[Candidate, ...]:
    return (
        Candidate(
            "stock_yjbb_em",
            "stock_financial",
            "沪深股票池的年度财务横截面初筛",
            "adopt_screening",
            (
                "股票代码",
                "股票简称",
                "营业总收入-同比增长",
                "净利润-同比增长",
                "净资产收益率",
                "每股经营现金流量",
                "销售毛利率",
                "所处行业",
                "最新公告日期",
            ),
            lambda ctx: {"date": ctx.report_date},
        ),
        Candidate(
            "stock_financial_analysis_indicator_em",
            "stock_financial",
            "候选股票主要财务指标深度核验",
            "adopt_deep_analysis",
            (
                "SECUCODE",
                "REPORT_DATE",
                "NOTICE_DATE",
                "ROEJQ",
                "ROIC",
                "ZCFZL",
                "JYXJLYYSR",
            ),
            lambda ctx: {
                "symbol": qualified_stock_code(ctx.stock_code, suffix=True),
                "indicator": "按报告期",
            },
        ),
        Candidate(
            "stock_financial_abstract_new_ths",
            "stock_financial",
            "主要财务指标的同花顺长表备用源",
            "conditional_fallback",
            (
                "report_date",
                "report_name",
                "report_period",
                "metric_name",
            ),
            lambda ctx: {
                "symbol": ctx.stock_code,
                "indicator": "按报告期",
            },
        ),
        Candidate(
            "stock_balance_sheet_by_report_em",
            "stock_financial",
            "资产、负债与商誉等财务安全字段核验",
            "adopt_deep_analysis",
            (
                "SECUCODE",
                "REPORT_DATE",
                "TOTAL_ASSETS",
                "TOTAL_LIABILITIES",
                "GOODWILL",
            ),
            lambda ctx: {
                "symbol": qualified_stock_code(ctx.stock_code, suffix=False)
            },
        ),
        Candidate(
            "stock_profit_sheet_by_report_em",
            "stock_financial",
            "收入、利润与扣非利润字段核验",
            "adopt_deep_analysis",
            (
                "SECUCODE",
                "REPORT_DATE",
                "OPERATE_INCOME",
                "PARENT_NETPROFIT",
                "DEDUCT_PARENT_NETPROFIT",
            ),
            lambda ctx: {
                "symbol": qualified_stock_code(ctx.stock_code, suffix=False)
            },
        ),
        Candidate(
            "stock_cash_flow_sheet_by_report_em",
            "stock_financial",
            "经营现金流与利润匹配度字段核验",
            "adopt_deep_analysis",
            (
                "SECUCODE",
                "REPORT_DATE",
                "NETCASH_OPERATE",
                "NETPROFIT",
            ),
            lambda ctx: {
                "symbol": qualified_stock_code(ctx.stock_code, suffix=False)
            },
        ),
        Candidate(
            "stock_zygc_em",
            "stock_financial",
            "主营业务与收入集中度核验",
            "conditional_deep_analysis",
            (
                "股票代码",
                "报告日期",
                "分类类型",
                "主营构成",
                "主营收入",
                "收入比例",
            ),
            lambda ctx: {
                "symbol": qualified_stock_code(ctx.stock_code, suffix=False)
            },
        ),
        Candidate(
            "stock_individual_info_em",
            "stock_financial",
            "个股当前行业字段",
            "reject_current_contract",
            ("item", "value"),
            lambda ctx: {
                "symbol": ctx.stock_code,
                "timeout": ctx.timeout_seconds,
            },
        ),
        Candidate(
            "stock_industry_change_cninfo",
            "industry",
            "个股在指定分类标准下的行业归属",
            "conditional_with_retry",
            (
                "行业大类",
                "行业编码",
                "分类标准",
                "证券代码",
                "变更日期",
            ),
            lambda ctx: {
                "symbol": ctx.stock_code,
                "start_date": "20000101",
                "end_date": ctx.as_of.strftime("%Y%m%d"),
            },
        ),
        Candidate(
            "stock_industry_pe_ratio_cninfo",
            "industry",
            "证监会行业分类的同口径静态 PE 基准",
            "conditional_with_retry",
            (
                "变动日期",
                "行业分类",
                "行业编码",
                "行业名称",
                "静态市盈率-加权平均",
                "静态市盈率-中位数",
            ),
            lambda ctx: {
                "symbol": "证监会行业分类",
                "date": ctx.as_of.strftime("%Y%m%d"),
            },
        ),
        Candidate(
            "stock_board_industry_name_em",
            "industry",
            "东方财富行业板块目录",
            "reject_unstable_upstream",
            ("板块名称", "板块代码"),
            lambda _ctx: {},
        ),
        Candidate(
            "stock_board_industry_cons_em",
            "industry",
            "东方财富行业板块成分",
            "reject_unstable_upstream",
            ("代码", "名称"),
            lambda ctx: {"symbol": ctx.industry_board},
        ),
        Candidate(
            "stock_board_industry_summary_ths",
            "industry",
            "同花顺行业行情概览",
            "reject_not_quality_or_mapping",
            ("板块", "涨跌幅", "总成交额"),
            lambda _ctx: {},
        ),
        Candidate(
            "stock_industry_category_cninfo",
            "industry",
            "巨潮行业分类目录",
            "reject_unstable_upstream",
            ("行业编码",),
            lambda _ctx: {"symbol": "申银万国行业分类标准"},
        ),
        Candidate(
            "fund_open_fund_rank_em",
            "fund_quality",
            "按基金类型获取收益与费率横截面候选池",
            "adopt_screening_with_freshness_gate",
            (
                "基金代码",
                "基金简称",
                "日期",
                "近1年",
                "近2年",
                "近3年",
                "手续费",
            ),
            lambda _ctx: {"symbol": "全部"},
        ),
        Candidate(
            "fund_rating_all",
            "fund_quality",
            "第三方评级横截面",
            "adopt_existing",
            ("代码", "简称", "基金经理", "基金公司", "类型"),
            lambda _ctx: {},
        ),
        Candidate(
            "fund_manager_em",
            "fund_quality",
            "基金与现任经理多对多关系及经理从业时间",
            "conditional_many_to_many",
            (
                "姓名",
                "所属公司",
                "现任基金代码",
                "累计从业时间",
            ),
            lambda _ctx: {},
        ),
        Candidate(
            "fund_individual_achievement_xq",
            "fund_quality",
            "阶段收益、最大回撤和同类排名的辅助核验",
            "conditional_source_rank",
            (
                "业绩类型",
                "周期",
                "本产品区间收益",
                "本产品最大回撒",
                "周期收益同类排名",
            ),
            lambda ctx: {
                "symbol": ctx.fund_code,
                "timeout": ctx.timeout_seconds,
            },
        ),
        Candidate(
            "fund_individual_analysis_xq",
            "fund_quality",
            "雪球基金风险分析字段",
            "reject_ambiguous_metric_semantics",
            (
                "周期",
                "较同类风险收益比",
                "较同类抗风险波动",
                "年化波动率",
                "年化夏普比率",
                "最大回撤",
            ),
            lambda ctx: {
                "symbol": ctx.fund_code,
                "timeout": ctx.timeout_seconds,
            },
        ),
        Candidate(
            "fund_portfolio_industry_allocation_em",
            "fund_quality",
            "报告期行业配置和集中度",
            "adopt_disclosed_snapshot",
            ("行业类别", "占净值比例", "市值", "截止时间"),
            lambda ctx: {
                "symbol": ctx.fund_code,
                "date": ctx.fund_year,
            },
        ),
        Candidate(
            "fund_scale_change_em",
            "fund_quality",
            "基金市场整体规模变动",
            "reject_market_aggregate",
            ("截止日期", "基金家数", "期末净资产"),
            lambda _ctx: {},
        ),
        Candidate(
            "fund_hold_structure_em",
            "fund_quality",
            "基金市场整体持有人结构",
            "reject_market_aggregate",
            ("截止日期", "基金家数", "机构持有比列"),
            lambda _ctx: {},
        ),
        Candidate(
            "fund_portfolio_change_em",
            "fund_quality",
            "基金重大买入卖出变动",
            "reject_current_decode_error",
            ("股票代码", "股票名称"),
            lambda ctx: {
                "symbol": ctx.fund_code,
                "indicator": "累计买入",
                "date": ctx.fund_year,
            },
        ),
        Candidate(
            "fund_etf_fund_info_em",
            "fund_quality",
            "ETF 历史净值明细",
            "reject_current_contract",
            ("净值日期",),
            lambda ctx: {
                "fund": ctx.etf_code,
                "start_date": f"{ctx.as_of.year - 1}0101",
                "end_date": ctx.as_of.strftime("%Y%m%d"),
            },
        ),
    )


def date_columns(frame: pd.DataFrame) -> list[str]:
    result: list[str] = []
    for column in frame.columns:
        text = str(column)
        lower = text.lower()
        if "日期" in text or text in {"截止时间", "变更日期"}:
            result.append(text)
        elif lower.endswith("_date") or lower in {
            "report_date",
            "notice_date",
            "update_date",
        }:
            result.append(text)
    return result


def date_coverage(frame: pd.DataFrame, as_of: date) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in date_columns(frame):
        values = pd.to_datetime(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        dates = values.dt.date
        result[column] = {
            "minimum": dates.min().isoformat(),
            "maximum": dates.max().isoformat(),
            "valid_rows": len(values),
            "future_rows": int((dates > as_of).sum()),
        }
    return result


def normalize_codes(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(6)
    )


def interface_quality(
    interface: str,
    frame: pd.DataFrame,
    as_of: date,
) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    if interface == "stock_yjbb_em":
        codes = normalize_codes(frame["股票代码"])
        supported = codes.str.startswith(("0", "3", "6"))
        quality = {
            "unique_codes": int(codes.nunique()),
            "supported_hu_shen_rows": int(supported.sum()),
            "supported_hu_shen_unique_codes": int(codes[supported].nunique()),
            "supported_missing_industry_rows": int(
                frame.loc[supported, "所处行业"].isna().sum()
            ),
        }
    elif interface == "fund_open_fund_rank_em":
        codes = normalize_codes(frame["基金代码"])
        values = pd.to_datetime(frame["日期"], errors="coerce")
        quality = {
            "unique_codes": int(codes.nunique()),
            "duplicate_code_rows": int(codes.duplicated(keep=False).sum()),
            "invalid_date_rows": int(values.isna().sum()),
            "future_rows": int((values.dt.date > as_of).sum()),
            "older_than_10_days_rows": int(
                (values.dt.date < as_of - timedelta(days=10)).sum()
            ),
            "missing_return_rows": {
                column: int(frame[column].isna().sum())
                for column in ("近1年", "近2年", "近3年")
            },
        }
    elif interface == "fund_manager_em":
        codes = normalize_codes(frame["现任基金代码"])
        quality = {
            "unique_fund_codes": int(codes.nunique()),
            "duplicate_fund_code_rows": int(
                codes.duplicated(keep=False).sum()
            ),
            "relationship": "many_to_many",
            "tenure_unit_requires_confirmation": True,
        }
    elif interface == "fund_individual_analysis_xq":
        quality = {
            "semantic_warning": (
                "AKShare maps upstream volatility_rank and sharpe_rank to "
                "annualized volatility and Sharpe ratio labels; do not use "
                "until upstream semantics are independently confirmed."
            )
        }
    elif interface == "fund_individual_achievement_xq":
        ranks = frame["周期收益同类排名"].dropna().astype(str)
        quality = {
            "rank_is_fraction_text": bool(ranks.str.contains("/").all()),
            "missing_drawdown_rows": int(
                frame["本产品最大回撒"].isna().sum()
            ),
        }
    elif interface in {"fund_scale_change_em", "fund_hold_structure_em"}:
        quality = {"scope": "market_aggregate_not_single_fund"}
    elif interface == "stock_industry_change_cninfo":
        quality = {
            "classification_standards": sorted(
                frame["分类标准"].dropna().astype(str).unique().tolist()
            ),
            "csrc_rows": int(
                frame["分类标准"]
                .astype(str)
                .str.contains("证监会行业分类标准", na=False)
                .sum()
            ),
        }
    elif interface == "stock_industry_pe_ratio_cninfo":
        quality = {
            "unique_industry_codes": int(
                frame["行业编码"].astype(str).nunique()
            )
        }
    return quality


def audit_dataframe(
    candidate: Candidate,
    frame: pd.DataFrame,
    *,
    arguments: dict[str, Any],
    as_of: date,
    duration_seconds: float,
    attempts: int,
    source_module: str,
) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise AuditContractError(
            f"{candidate.interface} returned {type(frame).__name__}"
        )
    if frame.columns.duplicated().any():
        duplicates = [
            str(column)
            for column in frame.columns[frame.columns.duplicated()]
        ]
        raise AuditContractError(f"duplicate columns: {duplicates}")
    missing = sorted(
        set(candidate.required_columns) - {str(c) for c in frame.columns}
    )
    if missing:
        raise AuditContractError(f"missing required columns: {missing}")
    if frame.empty:
        raise AuditContractError("empty DataFrame")
    return {
        "interface": candidate.interface,
        "group": candidate.group,
        "purpose": candidate.purpose,
        "recommendation": candidate.recommendation,
        "status": "passed",
        "attempts": attempts,
        "duration_seconds": round(duration_seconds, 3),
        "source_module": source_module,
        "arguments": arguments,
        "rows": len(frame),
        "columns": [str(column) for column in frame.columns],
        "required_columns": list(candidate.required_columns),
        "date_coverage": date_coverage(frame, as_of),
        "quality": interface_quality(candidate.interface, frame, as_of),
        "frame_sha256": frame_fingerprint(frame),
    }


def error_code(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "UPSTREAM_TIMEOUT"
    if isinstance(exc, AuditContractError):
        return "DATA_CONTRACT_ERROR"
    return "DATA_SOURCE_ERROR"


def audit_candidate(
    candidate: Candidate,
    context: AuditContext,
    *,
    ak_module: Any,
) -> dict[str, Any]:
    function = getattr(ak_module, candidate.interface, None)
    arguments = candidate.arguments(context)
    if not callable(function):
        return {
            "interface": candidate.interface,
            "group": candidate.group,
            "purpose": candidate.purpose,
            "recommendation": candidate.recommendation,
            "status": "failed",
            "arguments": arguments,
            "error": {
                "code": "UNSUPPORTED",
                "type": "MissingInterface",
                "message": "interface is not available in the locked AKShare",
            },
        }

    started = time.monotonic()
    last_error: Exception | None = None
    last_attempt = 0
    for attempt in range(1, context.attempts + 1):
        last_attempt = attempt
        try:
            with io.StringIO() as stdout_buffer, io.StringIO() as stderr_buffer:
                with (
                    redirect_stdout(stdout_buffer),
                    redirect_stderr(stderr_buffer),
                    deadline(context.timeout_seconds),
                ):
                    frame = function(**arguments)
            return audit_dataframe(
                candidate,
                frame,
                arguments=arguments,
                as_of=context.as_of,
                duration_seconds=time.monotonic() - started,
                attempts=attempt,
                source_module=getattr(function, "__module__", ""),
            )
        except AuditContractError as exc:
            last_error = exc
            break
        except Exception as exc:
            last_error = exc
            if attempt < context.attempts:
                time.sleep(attempt)

    assert last_error is not None
    return {
        "interface": candidate.interface,
        "group": candidate.group,
        "purpose": candidate.purpose,
        "recommendation": candidate.recommendation,
        "status": "failed",
        "attempts": last_attempt,
        "duration_seconds": round(time.monotonic() - started, 3),
        "source_module": getattr(function, "__module__", ""),
        "signature": str(inspect.signature(function)),
        "arguments": arguments,
        "error": {
            "code": error_code(last_error),
            "type": type(last_error).__name__,
            "message": str(last_error)[:500],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit candidate AKShare financial, industry, and fund-quality "
            "interfaces without enabling production tools."
        )
    )
    parser.add_argument(
        "--group",
        choices=("all", "stock_financial", "industry", "fund_quality"),
        default="all",
    )
    parser.add_argument("--stock", default="600519")
    parser.add_argument("--fund", default="000001")
    parser.add_argument("--etf", default="510300")
    parser.add_argument("--industry-board", default="酿酒行业")
    parser.add_argument("--as-of", default=None, help="YYYYMMDD")
    parser.add_argument("--report-date", default=None, help="YYYYMMDD")
    parser.add_argument("--fund-year", default=None, help="YYYY")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--strict", action="store_true")
    return parser


def parse_context(args: argparse.Namespace) -> AuditContext:
    as_of = (
        datetime.strptime(args.as_of, "%Y%m%d").date()
        if args.as_of
        else datetime.now(SHANGHAI).date()
    )
    report_date = args.report_date or f"{as_of.year - 1}1231"
    fund_year = args.fund_year or str(as_of.year - 1)
    if args.timeout < 1 or args.timeout > 300:
        raise ValueError("timeout must be in [1, 300]")
    if args.attempts < 1 or args.attempts > 3:
        raise ValueError("attempts must be in [1, 3]")
    return AuditContext(
        as_of=as_of,
        stock_code=args.stock.strip(),
        fund_code=args.fund.strip(),
        etf_code=args.etf.strip(),
        industry_board=args.industry_board.strip(),
        report_date=report_date,
        fund_year=fund_year,
        timeout_seconds=args.timeout,
        attempts=args.attempts,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    context = parse_context(args)

    import akshare as ak

    actual_version = getattr(ak, "__version__", None)
    if actual_version != SUPPORTED_AKSHARE_VERSION:
        payload = {
            "ok": False,
            "error": {
                "code": "AKSHARE_VERSION_MISMATCH",
                "expected": SUPPORTED_AKSHARE_VERSION,
                "actual": actual_version,
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    candidates = [
        item
        for item in candidate_interfaces()
        if args.group == "all" or item.group == args.group
    ]
    results = [
        audit_candidate(item, context, ak_module=ak) for item in candidates
    ]
    failed = [item for item in results if item["status"] != "passed"]
    payload = {
        "ok": not failed,
        "action": "audit_quality_interfaces",
        "akshare_version": actual_version,
        "queried_at": datetime.now(SHANGHAI).isoformat(),
        "as_of": context.as_of.isoformat(),
        "group": args.group,
        "representative_inputs": {
            "stock_code": context.stock_code,
            "fund_code": context.fund_code,
            "etf_code": context.etf_code,
            "industry_board": context.industry_board,
            "report_date": context.report_date,
            "fund_year": context.fund_year,
        },
        "summary": {
            "total": len(results),
            "passed": len(results) - len(failed),
            "failed": len(failed),
        },
        "results": results,
        "data_policy": {
            "discovery_only": True,
            "production_tools_changed": False,
            "ai_may_generate_market_data": False,
            "failed_interface_means_not_confirmed": True,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
