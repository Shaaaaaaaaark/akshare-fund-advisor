import {
  ArrowLeft,
  BarChart3,
  Bot,
  CalendarDays,
  Database,
  RefreshCw,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import {
  type FormEvent,
  useCallback,
  useEffect,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchStockDetail } from "../api";
import {
  displayNumber,
  displayPercent,
  levelLabel,
  warningText,
} from "../components/display";
import StatusBadge from "../components/StatusBadge";
import {
  PointChart,
  ValuationCharts,
} from "../components/ValuationCharts";
import type { StockDetailResponse } from "../types";

const DEFAULT_STOCK = "600519";
type StockYears = 1 | 3 | 5 | 10;

export default function StockDetailPage() {
  const { stock = DEFAULT_STOCK } = useParams();
  const navigate = useNavigate();
  const [years, setYears] = useState<StockYears>(10);
  const [query, setQuery] = useState(stock);
  const [payload, setPayload] = useState<StockDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(
    (signal: AbortSignal) => {
      setLoading(true);
      setError(null);
      setPayload(null);
      void fetchStockDetail(stock, years, signal)
        .then(setPayload)
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setError(
            reason instanceof Error ? reason.message : "股票数据请求失败",
          );
        })
        .finally(() => {
          if (!signal.aborted) {
            setLoading(false);
          }
        });
    },
    [stock, years],
  );

  useEffect(() => {
    setQuery(stock);
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey, stock]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) {
      return;
    }
    if (normalized === stock) {
      setRefreshKey((current) => current + 1);
      return;
    }
    navigate(`/stocks/${encodeURIComponent(normalized)}`);
  }

  if (loading && !payload) {
    return <StockLoading stock={stock} />;
  }

  if (error || !payload?.envelope?.ok || !payload.envelope.data) {
    return (
      <StockFailure
        stock={stock}
        query={query}
        setQuery={setQuery}
        message={
          error ??
          payload?.envelope?.error?.message ??
          "当前工具没有返回可用的股票数据。"
        }
        onSubmit={submit}
        onRetry={() => setRefreshKey((current) => current + 1)}
      />
    );
  }

  const data = payload.envelope.data;
  const price = data.charts.stock_price;
  const pe = data.charts.pe_ttm;
  const pb = data.charts.pb;
  const warnings =
    payload.meta.warnings ??
    payload.envelope.data_warnings ??
    data.data_quality.warnings ??
    [];

  return (
    <main className="workbench-page stock-detail-page">
      <div className="stock-breadcrumb">
        <Link to="/">
          <ArrowLeft aria-hidden="true" />
          数据面板
        </Link>
        <Link to="/chat" state={{ initialQuestion: `分析 ${data.stock.code}` }}>
          <Bot aria-hidden="true" />
          用 Agent 深入研究
        </Link>
      </div>

      <header className="stock-heading">
        <div>
          <p className="section-kicker">STOCK RESEARCH TERMINAL</p>
          <div className="stock-title-line">
            <h1>{data.stock.name}</h1>
            <span>{data.stock.qualified_code}</span>
            <StatusBadge status={payload.meta.status} />
          </div>
          <p>
            前复权价格、PE TTM 与 PB 独立展示，数据截至{" "}
            {payload.meta.as_of || data.lookback.latest_date || "—"}。
          </p>
        </div>
        <button
          type="button"
          className="icon-command"
          aria-label="刷新股票数据"
          title="刷新股票数据"
          disabled={loading}
          onClick={() => setRefreshKey((current) => current + 1)}
        >
          <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
        </button>
      </header>

      <section className="stock-toolbar" aria-label="股票查询">
        <form onSubmit={submit}>
          <Search aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入沪深 A 股代码或准确名称"
            aria-label="输入沪深 A 股代码或准确名称"
          />
          <button type="submit" disabled={!query.trim()}>
            查询
          </button>
        </form>
        <div className="stock-years-control" aria-label="历史窗口">
          {([1, 3, 5, 10] as StockYears[]).map((value) => (
            <button
              key={value}
              type="button"
              className={years === value ? "active" : ""}
              onClick={() => setYears(value)}
            >
              {value} 年
            </button>
          ))}
        </div>
      </section>

      <section className="stock-summary-band" aria-label="股票摘要">
        <StockSummaryItem
          label="前复权价格"
          value={displayNumber(data.summary.stock_price.current)}
          suffix="元"
          note={price?.latest_date || "日期不可用"}
        />
        <StockSummaryItem
          label="PE TTM"
          value={displayNumber(data.summary.pe_ttm.current)}
          note={summaryNote(
            data.summary.pe_ttm.percentile,
            data.summary.pe_ttm.level,
          )}
        />
        <StockSummaryItem
          label="PB"
          value={displayNumber(data.summary.pb.current)}
          note={summaryNote(
            data.summary.pb.percentile,
            data.summary.pb.level,
          )}
        />
        <div className="stock-summary-source">
          <Database aria-hidden="true" />
          <span>可用序列</span>
          <strong>{data.actual_source.available_series.join(" / ")}</strong>
          <small>{data.actual_source.provider}</small>
        </div>
      </section>

      {warnings.length > 0 && (
        <section className="stock-warning-band" aria-label="股票数据警告">
          <TriangleAlert aria-hidden="true" />
          <div>
            <strong>数据警告</strong>
            {warnings.map((warning, index) => (
              <span key={`${warningText(warning)}-${index}`}>
                {warningText(warning)}
              </span>
            ))}
          </div>
        </section>
      )}

      {price ? (
        <section className="stock-chart-section">
          <SectionHeading
            kicker="ADJUSTED PRICE"
            title="前复权价格历史"
            note={`${price.actual_start_date} 至 ${price.latest_date}`}
          />
          <div className="stock-chart-panel">
            <PointChart
              metric={price}
              title="前复权价格"
              ariaLabel="股票前复权价格历史曲线"
            />
          </div>
        </section>
      ) : (
        <MissingSeries name="前复权价格" />
      )}

      {pe || pb ? (
        <section className="stock-chart-section">
          <SectionHeading
            kicker="VALUATION HISTORY"
            title="PE TTM / PB 历史估值"
            note="独立纵轴，不合成综合分"
          />
          <div className="stock-reference-legend">
            <span>均值 / 中位数</span>
            <span>均值 ±1σ</span>
            <span>P20 / P80</span>
          </div>
          <div className="stock-chart-panel">
            <ValuationCharts pe={pe} pb={pb} />
          </div>
        </section>
      ) : (
        <MissingSeries name="PE TTM 与 PB" />
      )}

      <section className="stock-audit-section">
        <header>
          <ShieldCheck aria-hidden="true" />
          <div>
            <p className="section-kicker">PROVENANCE</p>
            <h2>来源与审计</h2>
          </div>
        </header>
        <div className="stock-provenance-grid">
          <div>
            <Database aria-hidden="true" />
            <span>数据接口</span>
            <strong>{data.actual_source.interfaces.join(" / ")}</strong>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" />
            <span>数据策略</span>
            <strong>不插值 · 不前向填充 · 不生成市场数值</strong>
          </div>
          <div>
            <CalendarDays aria-hidden="true" />
            <span>查询时间</span>
            <strong>{payload.envelope.queried_at}</strong>
          </div>
          <div>
            <BarChart3 aria-hidden="true" />
            <span>审计指纹</span>
            <strong>{payload.meta.audit_refs.length} 个</strong>
          </div>
        </div>
        <details>
          <summary>查看审计哈希</summary>
          <code>{payload.meta.audit_refs.join("\n") || "无可用审计指纹"}</code>
        </details>
      </section>

      <section className="stock-limitations">
        <strong>研究限制</strong>
        {data.limitations.map((item) => (
          <p key={item}>{item}</p>
        ))}
      </section>
    </main>
  );
}

function StockSummaryItem({
  label,
  value,
  suffix,
  note,
}: {
  label: string;
  value: string;
  suffix?: string;
  note: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <div>
        <strong>{value}</strong>
        {value !== "—" && suffix && <small>{suffix}</small>}
      </div>
      <p>{note}</p>
    </div>
  );
}

function SectionHeading({
  kicker,
  title,
  note,
}: {
  kicker: string;
  title: string;
  note: string;
}) {
  return (
    <header className="stock-section-heading">
      <div>
        <p className="section-kicker">{kicker}</p>
        <h2>{title}</h2>
      </div>
      <span>{note}</span>
    </header>
  );
}

function MissingSeries({ name }: { name: string }) {
  return (
    <section className="stock-missing-series">
      <TriangleAlert aria-hidden="true" />
      <div>
        <strong>{name}当前不可用</strong>
        <span>页面保留缺失状态，不使用零值或其他序列替代。</span>
      </div>
    </section>
  );
}

function StockLoading({ stock }: { stock: string }) {
  return (
    <main className="workbench-page stock-detail-page">
      <div className="stock-loading" role="status">
        <span />
        <span />
        <div />
        <strong>正在读取 {stock} 的价格与估值数据</strong>
      </div>
    </main>
  );
}

function StockFailure({
  stock,
  query,
  setQuery,
  message,
  onSubmit,
  onRetry,
}: {
  stock: string;
  query: string;
  setQuery: (value: string) => void;
  message: string;
  onSubmit: (event: FormEvent) => void;
  onRetry: () => void;
}) {
  return (
    <main className="workbench-page stock-detail-page">
      <div className="stock-failure">
        <TriangleAlert aria-hidden="true" />
        <h1>当前无法确认 {stock} 的股票数据</h1>
        <p>{message}</p>
        <form onSubmit={onSubmit}>
          <Search aria-hidden="true" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="重新输入股票代码或名称"
          />
          <button type="submit">查询其他股票</button>
        </form>
        <button type="button" className="stock-retry" onClick={onRetry}>
          <RefreshCw aria-hidden="true" />
          重试
        </button>
      </div>
    </main>
  );
}

function summaryNote(
  percentile: number | null,
  level: string | null,
): string {
  if (percentile === null) {
    return "历史分位不可用";
  }
  return `历史分位 ${displayPercent(percentile)} · ${levelLabel(level)}`;
}
