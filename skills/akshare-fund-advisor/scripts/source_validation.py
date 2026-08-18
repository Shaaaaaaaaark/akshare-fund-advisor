"""Optional market-source providers and deterministic cross-source comparison."""

from __future__ import annotations

import hashlib
import multiprocessing
import queue
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Callable, Optional

import pandas as pd

BAOSTOCK_DOC = (
    "https://www.baostock.com/baostock/index.php/Python_API%E6%96%87%E6%A1%A3"
)
EFINANCE_DOC = "https://efinance.readthedocs.io/en/latest/api.html"


class SourceValidationError(Exception):
    """A non-fatal validation-source failure."""

    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class ProviderFrame:
    source_name: str
    provider_version: Optional[str]
    interface: str
    upstream: str
    documentation_url: str
    parameters: dict[str, Any]
    metric_basis: str
    frame: pd.DataFrame
    columns: tuple[str, ...] = field(init=False)
    as_of: Optional[str] = field(init=False)
    frame_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        columns = tuple(str(column) for column in self.frame.columns)
        dates = (
            pd.Series(
                pd.to_datetime(self.frame["date"], errors="coerce")
            ).dropna()
            if "date" in self.frame
            else pd.Series(dtype="datetime64[ns]")
        )
        as_of = dates.max().date().isoformat() if not dates.empty else None
        normalized = self.frame.copy()
        normalized.columns = list(columns)
        normalized = normalized.astype(str)
        hashed = pd.util.hash_pandas_object(
            normalized,
            index=True,
        ).to_numpy().tobytes()
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(
            self,
            "frame_sha256",
            hashlib.sha256(hashed).hexdigest(),
        )


def _provider_worker(
    function: Callable[..., dict[str, Any]],
    arguments: dict[str, Any],
    output: Any,
) -> None:
    try:
        output.put({"ok": True, "result": function(**arguments)})
    except Exception as exc:
        output.put(
            {
                "ok": False,
                "error": {
                    "code": getattr(exc, "code", "SOURCE_UNAVAILABLE"),
                    "message": str(exc),
                    "details": getattr(exc, "details", {}),
                },
            }
        )
    finally:
        output.close()
        output.join_thread()


def _terminate_process(process: Any) -> None:
    if not process.is_alive():
        process.join()
        return
    process.terminate()
    process.join(1)
    if process.is_alive():
        process.kill()
        process.join(1)


def _run_isolated(
    function: Callable[..., dict[str, Any]],
    arguments: dict[str, Any],
    *,
    timeout_seconds: float,
    interface: str,
) -> dict[str, Any]:
    """Run an optional provider in a killable process."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds 必须大于 0")
    context = multiprocessing.get_context("spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_provider_worker,
        args=(function, arguments, output),
        daemon=True,
    )
    try:
        process.start()
        try:
            payload = output.get(timeout=timeout_seconds)
        except queue.Empty as exc:
            _terminate_process(process)
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                f"{interface} 超过 {timeout_seconds} 秒，已终止校验进程",
                {"timeout_seconds": timeout_seconds},
            ) from exc
        process.join(2)
        if process.is_alive():
            _terminate_process(process)
    finally:
        output.cancel_join_thread()
        output.close()

    if not isinstance(payload, dict):
        raise SourceValidationError(
            "SOURCE_SCHEMA_CHANGED",
            f"{interface} 校验进程返回结构无效",
            {"actual_type": type(payload).__name__},
        )
    if not payload.get("ok"):
        error = payload["error"]
        raise SourceValidationError(
            error.get("code", "SOURCE_UNAVAILABLE"),
            error.get("message", f"{interface} 校验失败"),
            error.get("details", {}),
        )
    return payload["result"]


def _query_baostock(parameters: dict[str, Any]) -> dict[str, Any]:
    import baostock as bs

    login = bs.login()
    if getattr(login, "error_code", None) != "0":
        raise SourceValidationError(
            "SOURCE_UNAVAILABLE",
            "Baostock 登录失败",
            {
                "error_code": getattr(login, "error_code", None),
                "error_msg": getattr(login, "error_msg", None),
            },
        )
    try:
        result = bs.query_history_k_data_plus(**parameters)
        if getattr(result, "error_code", None) != "0":
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                "Baostock 历史行情查询失败",
                {
                    "error_code": getattr(result, "error_code", None),
                    "error_msg": getattr(result, "error_msg", None),
                },
            )
        rows: list[list[str]] = []
        while result.next():
            rows.append(result.get_row_data())
        return {"rows": rows, "fields": result.fields}
    finally:
        bs.logout()


def _query_efinance_stock(parameters: dict[str, Any]) -> dict[str, Any]:
    import efinance

    frame = efinance.stock.get_quote_history(**parameters)
    if not isinstance(frame, pd.DataFrame):
        raise SourceValidationError(
            "SOURCE_SCHEMA_CHANGED",
            "efinance 历史行情未返回 DataFrame",
            {"actual_type": type(frame).__name__},
        )
    return {"frame": frame}


def _query_efinance_fund(parameters: dict[str, Any]) -> dict[str, Any]:
    import efinance

    frame = efinance.fund.get_quote_history(**parameters)
    if not isinstance(frame, pd.DataFrame):
        raise SourceValidationError(
            "SOURCE_SCHEMA_CHANGED",
            "efinance 基金净值未返回 DataFrame",
            {"actual_type": type(frame).__name__},
        )
    return {"frame": frame}


def _package_version(package: str) -> Optional[str]:
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _validate_canonical_price_frame(
    frame: pd.DataFrame,
    *,
    interface: str,
) -> pd.DataFrame:
    required = {"date", "code", "close", "volume", "amount", "adjustment"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SourceValidationError(
            "SOURCE_SCHEMA_CHANGED",
            f"{interface} 缺少已审计字段",
            {
                "missing_columns": missing,
                "actual_columns": [str(column) for column in frame.columns],
            },
        )
    result = frame.copy()
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    for column in ("close", "volume", "amount"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result = result.dropna(subset=["date", "close"]).sort_values("date")
    if result.empty:
        raise SourceValidationError(
            "SOURCE_UNAVAILABLE",
            f"{interface} 没有可比较的价格数据",
        )
    duplicate_dates = result["date"].duplicated(keep=False)
    if duplicate_dates.any():
        conflicts = (
            result.loc[duplicate_dates]
            .groupby("date", dropna=False)["close"]
            .nunique(dropna=True)
        )
        conflict_dates = [
            item.strftime("%Y-%m-%d")
            for item in conflicts[conflicts > 1].index
        ]
        if conflict_dates:
            raise SourceValidationError(
                "SOURCE_SCHEMA_CHANGED",
                f"{interface} 同一日期存在冲突收盘价",
                {"conflict_dates": conflict_dates[:10]},
            )
        result = result.drop_duplicates(subset=["date"], keep="last")
    return result.reset_index(drop=True)


class BaostockProvider:
    """Baostock historical daily-price provider."""

    name = "Baostock"
    interface = "baostock.query_history_k_data_plus"
    documentation_url = BAOSTOCK_DOC

    def __init__(self, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_stock_daily(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
        adjustment: str = "none",
    ) -> ProviderFrame:
        if _package_version("baostock") is None:
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                "未安装 Baostock 校验源",
                {"package": "baostock"},
            )

        adjust_flags = {"backward": "1", "forward": "2", "none": "3"}
        if adjustment not in adjust_flags:
            raise SourceValidationError(
                "SOURCE_BASIS_MISMATCH",
                "Baostock 复权口径不受支持",
                {"adjustment": adjustment},
            )
        market = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return self._fetch_daily(
            qualified_code=f"{market}.{code}",
            start_date=start_date,
            end_date=end_date,
            adjustment=adjustment,
            adjustflag=adjust_flags[adjustment],
            metric_basis=f"{adjustment}_daily_close",
        )

    def fetch_index_daily(
        self,
        *,
        qualified_code: str,
        start_date: str,
        end_date: str,
    ) -> ProviderFrame:
        if _package_version("baostock") is None:
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                "未安装 Baostock 校验源",
                {"package": "baostock"},
            )
        if not qualified_code.startswith(("sh.", "sz.")):
            raise SourceValidationError(
                "SOURCE_BASIS_MISMATCH",
                "Baostock 指数必须使用显式市场前缀",
                {"qualified_code": qualified_code},
            )
        return self._fetch_daily(
            qualified_code=qualified_code,
            start_date=start_date,
            end_date=end_date,
            adjustment="none",
            adjustflag="3",
            metric_basis="index_none_daily_close",
        )

    def _fetch_daily(
        self,
        *,
        qualified_code: str,
        start_date: str,
        end_date: str,
        adjustment: str,
        adjustflag: str,
        metric_basis: str,
    ) -> ProviderFrame:
        fields = (
            "date,code,open,high,low,close,volume,amount,"
            "adjustflag,tradestatus"
        )
        parameters = {
            "code": qualified_code,
            "fields": fields,
            "start_date": start_date,
            "end_date": end_date,
            "frequency": "d",
            "adjustflag": adjustflag,
        }

        payload = _run_isolated(
            _query_baostock,
            {"parameters": parameters},
            timeout_seconds=self.timeout_seconds,
            interface=self.interface,
        )
        raw = pd.DataFrame(payload["rows"], columns=payload["fields"])

        frame = pd.DataFrame(
            {
                "date": raw.get("date"),
                "code": raw.get("code"),
                "close": raw.get("close"),
                "volume": raw.get("volume"),
                "amount": raw.get("amount"),
                "adjustment": adjustment,
                "trade_status": raw.get("tradestatus"),
            }
        )
        frame = _validate_canonical_price_frame(
            frame,
            interface=self.interface,
        )
        return ProviderFrame(
            source_name=self.name,
            provider_version=_package_version("baostock"),
            interface=self.interface,
            upstream="Baostock 自有数据服务",
            documentation_url=self.documentation_url,
            parameters=parameters,
            metric_basis=metric_basis,
            frame=frame,
        )


class EFinanceProvider:
    """Optional efinance audit provider; not installed by default."""

    name = "efinance"
    stock_interface = "efinance.stock.get_quote_history"
    fund_interface = "efinance.fund.get_quote_history"
    documentation_url = EFINANCE_DOC

    def __init__(self, timeout_seconds: float = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def _require_package(self) -> None:
        if _package_version("efinance") is None:
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                "未安装 efinance 审计源",
                {
                    "package": "efinance",
                    "note": "许可声明需确认，不作为默认生产依赖",
                },
            )

    def fetch_stock_daily(
        self,
        *,
        code: str,
        start_date: str,
        end_date: str,
        adjustment: str = "none",
    ) -> ProviderFrame:
        self._require_package()
        fqt = {"none": 0, "forward": 1, "backward": 2}.get(adjustment)
        if fqt is None:
            raise SourceValidationError(
                "SOURCE_BASIS_MISMATCH",
                "efinance 复权口径不受支持",
                {"adjustment": adjustment},
            )
        parameters = {
            "stock_codes": code,
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
            "klt": 101,
            "fqt": fqt,
            "use_id_cache": False,
        }
        payload = _run_isolated(
            _query_efinance_stock,
            {"parameters": parameters},
            timeout_seconds=self.timeout_seconds,
            interface=self.stock_interface,
        )
        raw = payload["frame"]
        frame = pd.DataFrame(
            {
                "date": raw.get("日期"),
                "code": raw.get("股票代码"),
                "close": raw.get("收盘"),
                "volume": raw.get("成交量"),
                "amount": raw.get("成交额"),
                "adjustment": adjustment,
            }
        )
        frame = _validate_canonical_price_frame(
            frame,
            interface=self.stock_interface,
        )
        return ProviderFrame(
            source_name=self.name,
            provider_version=_package_version("efinance"),
            interface=self.stock_interface,
            upstream="东方财富公开行情接口",
            documentation_url=self.documentation_url,
            parameters=parameters,
            metric_basis=f"{adjustment}_daily_close",
            frame=frame,
        )

    def fetch_fund_nav(
        self,
        *,
        code: str,
        limit: int = 20,
    ) -> ProviderFrame:
        self._require_package()
        parameters = {"fund_code": code, "pz": limit}
        payload = _run_isolated(
            _query_efinance_fund,
            {"parameters": parameters},
            timeout_seconds=self.timeout_seconds,
            interface=self.fund_interface,
        )
        raw = payload["frame"]
        required = {"日期", "单位净值", "累计净值"}
        if not isinstance(raw, pd.DataFrame) or not required.issubset(raw.columns):
            raise SourceValidationError(
                "SOURCE_SCHEMA_CHANGED",
                "efinance 基金净值字段与审计契约不一致",
                {
                    "actual_type": type(raw).__name__,
                    "actual_columns": (
                        [str(item) for item in raw.columns]
                        if isinstance(raw, pd.DataFrame)
                        else []
                    ),
                },
            )
        frame = raw.rename(
            columns={
                "日期": "date",
                "单位净值": "unit_nav",
                "累计净值": "accumulated_nav",
            }
        )[["date", "unit_nav", "accumulated_nav"]].copy()
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        for column in ("unit_nav", "accumulated_nav"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date")
        if frame.empty:
            raise SourceValidationError(
                "SOURCE_UNAVAILABLE",
                "efinance 没有可审计的基金净值数据",
            )
        return ProviderFrame(
            source_name=self.name,
            provider_version=_package_version("efinance"),
            interface=self.fund_interface,
            upstream="东方财富基金公开接口",
            documentation_url=self.documentation_url,
            parameters=parameters,
            metric_basis="unit_nav_and_accumulated_nav",
            frame=frame.reset_index(drop=True),
        )


def compare_daily_close(
    primary: pd.DataFrame,
    check: pd.DataFrame,
    *,
    entity: str,
    primary_source: str,
    check_source: str,
    metric_basis: str,
    relative_tolerance: float = 0.001,
    absolute_tolerance: float = 0.01,
    stale_after_days: int = 3,
    minimum_overlap: int = 5,
) -> tuple[pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    """Compare same-basis close series without filling or changing either side."""

    primary_clean = _validate_canonical_price_frame(
        primary,
        interface=primary_source,
    )
    check_clean = _validate_canonical_price_frame(
        check,
        interface=check_source,
    )
    primary_basis = set(primary_clean["adjustment"].dropna().astype(str))
    check_basis = set(check_clean["adjustment"].dropna().astype(str))
    if primary_basis != check_basis or primary_basis != {"none"}:
        warning = {
            "code": "SOURCE_BASIS_MISMATCH",
            "field": "close",
            "primary_source": primary_source,
            "check_source": check_source,
            "entity": entity,
            "primary_basis": sorted(primary_basis),
            "check_basis": sorted(check_basis),
            "effect": "口径不可比，未执行数值差异判断，主源事实不变。",
        }
        return pd.DataFrame(), [warning], {"comparable": False}

    left = primary_clean[["date", "close"]].rename(
        columns={"close": "primary_close"}
    )
    right = check_clean[["date", "close"]].rename(
        columns={"close": "check_close"}
    )
    comparison = left.merge(right, on="date", how="inner", validate="one_to_one")
    comparison["absolute_diff"] = (
        comparison["primary_close"] - comparison["check_close"]
    ).abs()
    denominator = comparison["primary_close"].abs()
    comparison["relative_diff"] = comparison["absolute_diff"].where(
        denominator.eq(0),
        comparison["absolute_diff"] / denominator,
    )
    allowed = denominator.mul(relative_tolerance).clip(
        lower=absolute_tolerance
    )
    comparison["outside_tolerance"] = comparison["absolute_diff"].gt(allowed)

    warnings: list[dict[str, Any]] = []
    primary_latest = primary_clean["date"].max()
    check_latest = check_clean["date"].max()
    lag_days = (primary_latest - check_latest).days
    if lag_days > stale_after_days:
        warnings.append(
            {
                "code": "SOURCE_STALE",
                "field": "close",
                "primary_source": primary_source,
                "check_source": check_source,
                "entity": entity,
                "primary_latest_date": primary_latest.date().isoformat(),
                "check_latest_date": check_latest.date().isoformat(),
                "lag_days": lag_days,
                "effect": "校验源过期，主源事实不变。",
            }
        )

    if len(comparison) < minimum_overlap:
        warnings.append(
            {
                "code": "SOURCE_UNAVAILABLE",
                "field": "close",
                "primary_source": primary_source,
                "check_source": check_source,
                "entity": entity,
                "overlap_observations": len(comparison),
                "minimum_overlap": minimum_overlap,
                "effect": "共同日期样本不足，未形成可靠交叉校验，主源事实不变。",
            }
        )
    else:
        mismatches = comparison[comparison["outside_tolerance"]]
        if not mismatches.empty:
            samples = [
                {
                    "date": row.date.date().isoformat(),
                    "primary_value": float(row.primary_close),
                    "check_value": float(row.check_close),
                    "relative_diff_pct": round(float(row.relative_diff) * 100, 6),
                }
                for row in mismatches.tail(5).itertuples()
            ]
            warnings.append(
                {
                    "code": "SOURCE_DISAGREE",
                    "field": "close",
                    "primary_source": primary_source,
                    "check_source": check_source,
                    "entity": entity,
                    "metric_basis": metric_basis,
                    "relative_tolerance": relative_tolerance,
                    "absolute_tolerance": absolute_tolerance,
                    "overlap_observations": len(comparison),
                    "mismatch_observations": len(mismatches),
                    "samples": samples,
                    "effect": "仅披露差异，不覆盖或平均主源事实。",
                }
            )

    summary = {
        "comparable": True,
        "metric_basis": metric_basis,
        "overlap_observations": len(comparison),
        "mismatch_observations": int(comparison["outside_tolerance"].sum()),
        "primary_latest_date": primary_latest.date().isoformat(),
        "check_latest_date": check_latest.date().isoformat(),
        "relative_tolerance": relative_tolerance,
        "absolute_tolerance": absolute_tolerance,
        "interpolation": "none",
        "forward_fill": "none",
    }
    return comparison, warnings, summary
