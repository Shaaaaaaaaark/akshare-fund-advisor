import importlib.util
import io
import json
import sys
import types
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "fund_advisor.py"
SPEC = importlib.util.spec_from_file_location("fund_advisor", SCRIPT_PATH)
fund_advisor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fund_advisor)


def make_advisor(ak=None, now=None):
    advisor = fund_advisor.FundAdvisor.__new__(fund_advisor.FundAdvisor)
    advisor.ak = ak or SimpleNamespace(__version__="1.18.64")
    advisor.now = now or datetime.now(fund_advisor.SHANGHAI)
    advisor.timeout_seconds = 1
    advisor.sources = []
    advisor.data_warnings = []
    advisor.data_audit = []
    advisor._names_frame = None
    advisor._purchase_frame = None
    advisor._calendar_frame = None
    advisor._etf_spot_frame = None
    advisor._profile_cache = {}
    advisor._valuation_cache = {}
    return advisor


def valuation_frames(end_date=None, periods=120):
    dates = pd.bdate_range(
        end=end_date or datetime.now(fund_advisor.SHANGHAI).date(),
        periods=periods,
    )
    pe = pd.DataFrame(
        {
            "日期": dates,
            "指数": ["沪深300"] * periods,
            "等权静态市盈率": [20.0] * periods,
            "静态市盈率": [15.0] * periods,
            "等权滚动市盈率": [19.0] * periods,
            "滚动市盈率": [14.0 + index / 100 for index in range(periods)],
        }
    )
    pb = pd.DataFrame(
        {
            "日期": dates,
            "指数": ["沪深300"] * periods,
            "市净率": [1.4 + index / 1000 for index in range(periods)],
            "等权市净率": [1.8] * periods,
            "市净率中位数": [1.5] * periods,
        }
    )
    return pe, pb


def exchange_history_frame(end_date=None, periods=260):
    dates = pd.bdate_range(
        end=end_date or datetime.now(fund_advisor.SHANGHAI).date(),
        periods=periods,
    )
    values = [3.0 + index / 1000 for index in range(periods)]
    return pd.DataFrame(
        {
            "日期": dates,
            "开盘": values,
            "收盘": values,
            "最高": values,
            "最低": values,
            "成交量": [1000] * periods,
            "成交额": [3000] * periods,
            "涨跌幅": [0.1] * periods,
        }
    )


class StatusInterpretationTest(unittest.TestCase):
    def test_open_and_closed_statuses(self):
        self.assertTrue(fund_advisor.operation_is_open("开放申购"))
        self.assertTrue(fund_advisor.operation_is_open("限大额"))
        self.assertTrue(fund_advisor.operation_is_open("暂停大额申购"))
        self.assertFalse(fund_advisor.operation_is_open("暂停申购"))
        self.assertFalse(fund_advisor.operation_is_open("封闭期"))
        self.assertIsNone(fund_advisor.operation_is_open("场内交易"))
        self.assertIsNone(fund_advisor.operation_is_open(""))

    def test_premium_direction_is_consistent(self):
        self.assertEqual(fund_advisor.premium_rate(1.05, 1.00), 5.0)
        self.assertEqual(fund_advisor.premium_rate(0.95, 1.00), -5.0)
        self.assertIsNone(fund_advisor.premium_rate(1.00, 0))
        self.assertIsNone(fund_advisor.json_value(pd.NaT))


class MetricsTest(unittest.TestCase):
    def test_metrics_include_drawdown_and_position(self):
        dates = pd.bdate_range("2024-01-02", periods=260)
        values = [100 + index * 0.1 for index in range(200)]
        values.extend([120 - index * 0.5 for index in range(60)])
        frame = pd.DataFrame({"日期": dates, "收盘": values})

        metrics = fund_advisor.calculate_metrics(
            frame,
            "日期",
            "收盘",
            years=3,
        )

        self.assertEqual(metrics["observations"], 260)
        self.assertLess(metrics["current_drawdown_pct"], 0)
        self.assertLessEqual(metrics["max_drawdown_pct"], metrics["current_drawdown_pct"])
        self.assertEqual(metrics["trend"], "down")
        self.assertGreaterEqual(metrics["history_position_percentile"], 0)
        self.assertLessEqual(metrics["history_position_percentile"], 100)
        self.assertNotIn("equal_monthly_dca_backtest", metrics)
        self.assertEqual(metrics["data_quality"]["interpolation"], "none")
        self.assertEqual(metrics["data_quality"]["forward_fill"], "none")
        experience = metrics["holding_experience"]
        self.assertIn("annualized_return_pct", experience)
        self.assertIn("downside_volatility_pct", experience)
        self.assertIn("max_drawdown_detail", experience)
        self.assertIn("monthly_return_statistics", experience)
        self.assertIn(
            "rolling_250_observation_return_statistics",
            experience,
        )

    def test_drawdown_recovery_dates_are_deterministic(self):
        dates = pd.bdate_range("2026-01-02", periods=4)
        series = pd.DataFrame(
            {
                "date": dates,
                "value": [100.0, 120.0, 90.0, 120.0],
            }
        )
        experience = fund_advisor.calculate_holding_experience(series)
        detail = experience["max_drawdown_detail"]
        self.assertEqual(detail["drawdown_pct"], -25.0)
        self.assertEqual(detail["peak_date"], dates[1].date())
        self.assertEqual(detail["trough_date"], dates[2].date())
        self.assertEqual(detail["recovery_date"], dates[3].date())
        self.assertTrue(detail["recovered"])

    def test_monotonic_series_has_no_fabricated_recovery_event(self):
        dates = pd.bdate_range("2026-01-02", periods=3)
        series = pd.DataFrame(
            {
                "date": dates,
                "value": [100.0, 110.0, 120.0],
            }
        )

        detail = fund_advisor.calculate_holding_experience(series)[
            "max_drawdown_detail"
        ]

        self.assertEqual(detail["drawdown_pct"], 0.0)
        self.assertIsNone(detail["peak_date"])
        self.assertIsNone(detail["trough_date"])
        self.assertIsNone(detail["recovery_date"])
        self.assertIsNone(detail["recovery_days_from_trough"])
        self.assertFalse(detail["recovered"])

    def test_valuation_metric_and_dca_action(self):
        dates = pd.bdate_range("2024-01-02", periods=100)
        frame = pd.DataFrame(
            {
                "日期": dates,
                "滚动市盈率": list(range(1, 101)),
            }
        )
        valuation = fund_advisor.calculate_valuation_metric(
            frame,
            "日期",
            "滚动市盈率",
            years=3,
        )

        self.assertEqual(valuation["percentile"], 100.0)
        self.assertEqual(valuation["level"], "high")
        action, basis = fund_advisor.dca_action_band(90, "up", None)
        self.assertEqual(action, "reduced_contribution_or_wait")
        self.assertEqual(basis, "pe_ttm_percentile")

    def test_low_position_downtrend_and_premium_actions(self):
        action, basis = fund_advisor.dca_action_band(None, "down", None)
        self.assertEqual(action, "base_contribution_no_valuation_signal")
        self.assertEqual(basis, "no_reliable_valuation")

        action, basis = fund_advisor.dca_action_band(10, "up", 5.0)
        self.assertEqual(action, "base_or_modest_tilt")
        self.assertEqual(basis, "pe_ttm_percentile")

        action, basis = fund_advisor.dca_action_band(10, "up", 5.01)
        self.assertEqual(action, "pause_current_exchange_venue")
        self.assertEqual(basis, "high_exchange_premium")

    def test_wind_style_valuation_chart_keeps_statistics_and_extremes(self):
        dates = pd.bdate_range("2022-01-03", periods=1000)
        values = [20 + (index % 50) * 0.1 for index in range(1000)]
        values[333] = 80
        values[777] = 5
        frame = pd.DataFrame({"日期": dates, "滚动市盈率": values})

        chart = fund_advisor.build_valuation_chart_metric(
            frame,
            "日期",
            "滚动市盈率",
            "PE_TTM",
            years=10,
            max_points=50,
        )
        displayed = {item[0]: item[1] for item in chart["chart_series"]}

        self.assertEqual(chart["source_observations"], 1000)
        self.assertLessEqual(chart["displayed_points"], 50)
        self.assertEqual(chart["minimum"]["value"], 5.0)
        self.assertEqual(chart["maximum"]["value"], 80.0)
        self.assertIn(dates[333].date().isoformat(), displayed)
        self.assertIn(dates[777].date().isoformat(), displayed)
        self.assertIn("p20", chart["reference_lines"])
        self.assertIn("mean_plus_1_stddev", chart["reference_lines"])
        self.assertEqual(chart["data_quality"]["interpolation"], "none")
        self.assertIn("3_years", chart["window_statistics"])

    def test_profile_value_parsing(self):
        self.assertEqual(fund_advisor.parse_percent_text("1.20%"), 1.2)
        self.assertIsNone(fund_advisor.parse_percent_text("1元/笔"))
        self.assertEqual(
            fund_advisor.parse_yi_text("25.92亿份（2026-03-31）"),
            25.92,
        )

    def test_index_alias_and_wind_code_resolution(self):
        alias = fund_advisor.FundAdvisor._resolve_index("沪深300指数")
        wind_code = fund_advisor.FundAdvisor._resolve_index("000300.SH")

        self.assertEqual(alias["name"], "沪深300")
        self.assertEqual(alias["wind_code"], "000300.SH")
        self.assertEqual(wind_code["akshare_symbol"], "沪深300")

    def test_sub_index_is_not_mapped_to_broad_index(self):
        fund = {
            "name": "沪深300非银行金融ETF",
            "type": "指数型",
        }
        profile = {
            "full_name": "沪深300非银行金融交易型开放式指数基金",
            "benchmark": "沪深300非银行金融指数收益率",
        }
        self.assertIsNone(
            fund_advisor.FundAdvisor._match_supported_index(fund, profile)
        )

        broad_fund = {"name": "沪深300ETF", "type": "指数型"}
        broad_profile = {"benchmark": "沪深300指数收益率*95%+存款利率*5%"}
        self.assertEqual(
            fund_advisor.FundAdvisor._match_supported_index(
                broad_fund,
                broad_profile,
            ),
            "沪深300",
        )
        with self.assertRaises(fund_advisor.AdvisorError) as context:
            fund_advisor.FundAdvisor._resolve_index("沪深300非银行金融")
        self.assertEqual(context.exception.code, "INDEX_NOT_SUPPORTED")

    def test_conflicting_duplicate_dates_are_rejected(self):
        frame = pd.DataFrame(
            {
                "日期": ["2026-01-02", "2026-01-02"],
                "收盘": [1.0, 1.1],
            }
        )
        with self.assertRaises(fund_advisor.AdvisorError) as context:
            fund_advisor.prepare_series(frame, "日期", "收盘", years=1)
        self.assertEqual(context.exception.code, "DUPLICATE_DATE_CONFLICT")

    def test_negative_money_fund_yield_is_not_silently_removed(self):
        frame = pd.DataFrame(
            {
                "净值日期": ["2026-01-02", "2026-01-03"],
                "7日年化收益率": [-0.01, 0.02],
            }
        )
        metrics = fund_advisor.calculate_yield_metrics(
            frame,
            "净值日期",
            "7日年化收益率",
        )
        self.assertEqual(metrics["observations"], 2)
        self.assertEqual(metrics["one_year_low_pct"], -0.01)

    def test_frame_fingerprint_changes_when_source_data_changes(self):
        first = pd.DataFrame({"代码": ["000001"], "净值": [1.0]})
        second = pd.DataFrame({"代码": ["000001"], "净值": [1.1]})
        self.assertNotEqual(
            fund_advisor.frame_fingerprint(first),
            fund_advisor.frame_fingerprint(second),
        )


class MarketSessionTest(unittest.TestCase):
    def test_market_open_and_next_session(self):
        timezone = ZoneInfo("Asia/Shanghai")
        trading_dates = [date(2026, 7, 16), date(2026, 7, 17)]
        session = fund_advisor.market_session_from_dates(
            trading_dates,
            datetime(2026, 7, 16, 10, 0, tzinfo=timezone),
        )

        self.assertTrue(session["is_trading_day"])
        self.assertTrue(session["standard_market_open_now"])
        self.assertEqual(session["state"], "open")
        self.assertIsNone(session["next_standard_session_date"])

        closed = fund_advisor.market_session_from_dates(
            trading_dates,
            datetime(2026, 7, 16, 16, 0, tzinfo=timezone),
        )
        self.assertFalse(closed["standard_market_open_now"])
        self.assertEqual(closed["next_standard_session_date"], date(2026, 7, 17))

    def test_stale_calendar_does_not_claim_market_state(self):
        timezone = ZoneInfo("Asia/Shanghai")
        advisor = make_advisor(
            now=datetime(2026, 7, 21, 10, 0, tzinfo=timezone)
        )
        advisor._calendar_frame = pd.DataFrame(
            {"trade_date": [date(2026, 7, 20)]}
        )

        self.assertIsNone(advisor._market_session())
        self.assertEqual(
            advisor.data_warnings[0]["interface"],
            "tool_trade_date_hist_sina",
        )


class DataFallbackTest(unittest.TestCase):
    def test_auto_source_falls_back_to_akshare_after_wind_timeout(self):
        pe, pb = valuation_frames()
        ak = SimpleNamespace(
            __version__="1.18.64",
            stock_index_pe_lg=lambda **_kwargs: pe,
            stock_index_pb_lg=lambda **_kwargs: pb,
        )
        advisor = make_advisor(ak=ak)
        wind_module = types.ModuleType("WindPy")

        def timeout_start(**_kwargs):
            raise fund_advisor.DataSourceTimeout("timed out")

        wind_module.w = SimpleNamespace(start=timeout_start)
        with patch.object(
            fund_advisor.importlib.util,
            "find_spec",
            return_value=object(),
        ), patch.dict(sys.modules, {"WindPy": wind_module}):
            result = advisor.valuation(
                "沪深300",
                years=3,
                source="auto",
                max_points=50,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["actual_source"]["provider"], "AKShare")
        self.assertIn("PE_TTM", result["actual_source"]["available_metrics"])
        self.assertTrue(
            any(
                item["interface"] == "w.wsd"
                and item["validation"] == "failed"
                for item in advisor.data_audit
            )
        )
        self.assertTrue(
            any(item["interface"] == "w.wsd" for item in advisor.data_warnings)
        )

    def test_valuation_keeps_fresh_pb_when_pe_interface_fails(self):
        _, pb = valuation_frames()

        def failed_pe(**_kwargs):
            raise RuntimeError("PE unavailable")

        ak = SimpleNamespace(
            __version__="1.18.64",
            stock_index_pe_lg=failed_pe,
            stock_index_pb_lg=lambda **_kwargs: pb,
        )
        advisor = make_advisor(ak=ak)

        result = advisor.valuation(
            "沪深300",
            years=3,
            source="akshare",
            max_points=50,
        )

        self.assertIsNone(result["charts"]["pe_ttm"])
        self.assertIsNotNone(result["charts"]["pb_lf"])
        self.assertEqual(result["actual_source"]["available_metrics"], ["PB_LF"])
        self.assertTrue(
            any(
                item["interface"] == "stock_index_pe_lg"
                for item in advisor.data_warnings
            )
        )

    def test_index_valuation_discards_stale_pe_but_keeps_fresh_pb(self):
        stale_end = datetime.now(fund_advisor.SHANGHAI).date() - pd.Timedelta(
            days=20
        )
        stale_pe, _ = valuation_frames(end_date=stale_end)
        _, fresh_pb = valuation_frames()
        ak = SimpleNamespace(
            __version__="1.18.64",
            stock_index_pe_lg=lambda **_kwargs: stale_pe,
            stock_index_pb_lg=lambda **_kwargs: fresh_pb,
        )
        advisor = make_advisor(ak=ak)

        result = advisor._index_valuation(
            {"name": "沪深300ETF", "type": "指数型"},
            {"benchmark": "沪深300指数收益率"},
            years=10,
        )

        self.assertTrue(result["available"])
        self.assertIsNone(result["pe_ttm"])
        self.assertIsNotNone(result["pb"])
        self.assertEqual(result["confidence"], "medium")

    def test_etf_history_does_not_depend_on_purchase_status_availability(self):
        history = exchange_history_frame()
        ak = SimpleNamespace(
            __version__="1.18.64",
            fund_etf_hist_em=lambda **_kwargs: history,
        )
        advisor = make_advisor(ak=ak)

        metrics, basis, _note = advisor._historical_metrics(
            {"code": "510300", "name": "沪深300ETF", "type": "指数型"},
            {"confirmed": False},
            years=1,
        )

        self.assertEqual(basis, "exchange_qfq_close")
        self.assertEqual(metrics["observations"], 260)


class AuditAndErrorOutputTest(unittest.TestCase):
    def test_audit_marks_optional_interface_none_as_failed(self):
        pe, pb = valuation_frames()
        history = exchange_history_frame(periods=45)
        today = datetime.now(fund_advisor.SHANGHAI).date()
        names = pd.DataFrame(
            {
                "基金代码": ["000001", "510300", "166009"],
                "拼音缩写": ["HXCZ", "HS300ETF", "LOF"],
                "基金简称": ["华夏成长", "沪深300ETF", "LOF基金"],
                "基金类型": ["混合型", "指数型", "混合型"],
                "拼音全称": ["HUAXIACHENGZHANG", "HUSHEN300ETF", "LOF"],
            }
        )
        purchases = pd.DataFrame(
            {
                "基金代码": ["000001"],
                "基金简称": ["华夏成长"],
                "基金类型": ["混合型"],
                "最新净值/万份收益": [1.0],
                "最新净值/万份收益-报告时间": [today],
                "申购状态": ["开放申购"],
                "赎回状态": ["开放赎回"],
                "下一开放日": [None],
                "购买起点": [10.0],
                "日累计限定金额": [100000.0],
                "手续费": [0.15],
            }
        )
        unit_nav = pd.DataFrame(
            {
                "净值日期": [today],
                "单位净值": [1.0],
                "日增长率": [0.0],
            }
        )
        accumulated_nav = pd.DataFrame(
            {"净值日期": [today], "累计净值": [2.0]}
        )
        sina_history = pd.DataFrame(
            {
                "date": [today],
                "open": [3.0],
                "high": [3.1],
                "low": [2.9],
                "close": [3.0],
                "volume": [1000],
            }
        )

        def open_fund_info(**kwargs):
            if kwargs["indicator"] == "单位净值走势":
                return unit_nav
            return accumulated_nav

        def failed_spot():
            raise RuntimeError("spot unavailable")

        ak = SimpleNamespace(
            __version__="1.18.64",
            fund_name_em=lambda: names,
            fund_purchase_em=lambda: purchases,
            fund_info_ths=lambda **_kwargs: pd.DataFrame(
                {"字段": ["基金代码"], "值": ["000001"]}
            ),
            fund_open_fund_info_em=open_fund_info,
            fund_etf_hist_em=lambda **_kwargs: history,
            fund_lof_hist_em=lambda **_kwargs: history,
            fund_etf_hist_sina=lambda **_kwargs: sina_history,
            fund_etf_spot_em=failed_spot,
            tool_trade_date_hist_sina=lambda: pd.DataFrame(
                {"trade_date": [today]}
            ),
            stock_index_pe_lg=lambda **_kwargs: pe,
            stock_index_pb_lg=lambda **_kwargs: pb,
        )
        advisor = make_advisor(ak=ak)

        result = advisor.audit()

        spot_check = next(
            item
            for item in result["checks"]
            if item["check"] == "fund_etf_spot_em_schema"
        )
        self.assertEqual(spot_check["status"], "failed")
        self.assertFalse(result["ok"])
        self.assertGreaterEqual(result["summary"]["failed"], 1)

    def test_main_error_response_preserves_common_audit_fields(self):
        class FailingAdvisor:
            def __init__(self):
                self.audit = [{"interface": "stock_index_pe_lg"}]

            def valuation(self, *_args):
                raise fund_advisor.AdvisorError(
                    "DATA_SOURCE_ERROR",
                    "source failed",
                )

            def common_output(self):
                return {
                    "data_audit": self.audit,
                    "data_warnings": [],
                    "data_policy": {"ai_may_generate_market_data": False},
                    "sources": [],
                }

        output = io.StringIO()
        with patch.object(fund_advisor, "FundAdvisor", FailingAdvisor):
            with redirect_stdout(output):
                exit_code = fund_advisor.main(
                    [
                        "valuation",
                        "--index",
                        "沪深300",
                        "--source",
                        "akshare",
                    ]
                )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["error"]["code"], "DATA_SOURCE_ERROR")
        self.assertEqual(payload["data_audit"], [{"interface": "stock_index_pe_lg"}])
        self.assertFalse(payload["data_policy"]["ai_may_generate_market_data"])


if __name__ == "__main__":
    unittest.main()
