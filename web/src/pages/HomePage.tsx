import {
  Activity,
  ArrowRight,
  BarChart3,
  Database,
  Landmark,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  fetchOverview,
  fetchOverviewModule,
  type OverviewModule,
} from "../api";
import { displayNumber, displayPercent } from "../components/display";
import StatusBadge from "../components/StatusBadge";
import type {
  DataStatus,
  DatasetMeta,
  OverviewResponse,
} from "../types";

export default function HomePage() {
  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshingModule, setRefreshingModule] =
    useState<OverviewModule | null>(null);
  const [moduleErrors, setModuleErrors] = useState<
    Partial<Record<OverviewModule, string>>
  >({});
  const moduleRefreshSeq = useRef<Record<OverviewModule, number>>({
    index: 0,
    etf: 0,
    fund: 0,
    stock: 0,
  });

  useEffect(() => {
    const controller = new AbortController();
    invalidateModuleRefreshes(moduleRefreshSeq.current);
    setLoading(true);
    setError(null);
    void fetchOverview(controller.signal)
      .then(setOverview)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          return;
        }
        setError(reason instanceof Error ? reason.message : "总览请求失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [refreshKey]);

  const indexData = overview?.index.envelope?.data;
  const etfData = overview?.etf.envelope?.data;
  const fundData = overview?.fund.envelope?.data;
  const stockData = overview?.stock.envelope?.data;

  async function refreshModule(module: OverviewModule) {
    const requestSeq = moduleRefreshSeq.current[module] + 1;
    moduleRefreshSeq.current[module] = requestSeq;
    setRefreshingModule(module);
    setModuleErrors((current) => ({ ...current, [module]: undefined }));
    try {
      const result = await fetchOverviewModule(module);
      if (moduleRefreshSeq.current[module] !== requestSeq) {
        return;
      }
      setOverview((current) =>
        current ? withOverviewModule(current, module, result) : current,
      );
    } catch (reason) {
      if (moduleRefreshSeq.current[module] !== requestSeq) {
        return;
      }
      setModuleErrors((current) => ({
        ...current,
        [module]: reason instanceof Error ? reason.message : "模块刷新失败",
      }));
    } finally {
      if (moduleRefreshSeq.current[module] === requestSeq) {
        setRefreshingModule(null);
      }
    }
  }

  return (
    <main className="workbench-page home-page overview-page">
      <header className="overview-heading">
        <div>
          <p className="section-kicker">AUDITED MARKET OVERVIEW</p>
          <h1>跨模块投研总览</h1>
          <p>指数、ETF、主动基金和股票独立取数；每块保留来源、日期和审计状态。</p>
        </div>
        <div className="overview-heading-actions">
          <span className="home-policy">
            <ShieldCheck aria-hidden="true" />
            <span>
              <strong>AKShare 审计事实</strong>
              不补点 · 不跨口径排名
            </span>
          </span>
          <button
            type="button"
            className="overview-refresh"
            aria-label="刷新跨模块总览"
            title="刷新跨模块总览"
            disabled={loading}
            onClick={() => setRefreshKey((key) => key + 1)}
          >
            <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
          </button>
        </div>
      </header>

      {error ? (
        <section className="overview-error" role="alert">
          <strong>当前无法确认跨模块总览</strong>
          <span>{error}</span>
          <button type="button" onClick={() => setRefreshKey((key) => key + 1)}>
            重试
          </button>
        </section>
      ) : !overview ? (
        <OverviewLoading />
      ) : (
        <>
          <section className="overview-status-bar" aria-label="总览状态">
            <div>
              <span>总览状态</span>
              <StatusBadge status={overview.status} />
            </div>
            <OverviewStatus
              label="指数"
              status={overview.index.meta.status}
              asOf={overview.index.meta.as_of}
            />
            <OverviewStatus
              label="ETF"
              status={overview.etf.meta.status}
              asOf={overview.etf.meta.as_of}
            />
            <OverviewStatus
              label="主动基金"
              status={overview.fund.meta.status}
              asOf={overview.fund.meta.as_of}
            />
            <OverviewStatus
              label="股票"
              status={overview.stock.meta.status}
              asOf={overview.stock.meta.as_of}
            />
          </section>

          <section className="overview-grid" aria-label="跨模块数据">
            <OverviewCard
              icon={<BarChart3 aria-hidden="true" />}
              category="指数估值"
              title={indexData?.index.name || overview.index.index}
              code={indexData?.index.qualified_code}
              status={overview.index.meta.status}
              meta={overview.index.meta}
              href={`/indices/${encodeURIComponent(overview.index.index)}`}
              refreshing={refreshingModule === "index"}
              refreshError={moduleErrors.index}
              onRefresh={() => void refreshModule("index")}
              metrics={[
                ["指数点位", displayNumber(indexData?.charts.index_points?.current)],
                ["PE TTM", displayNumber(indexData?.summary.pe_ttm?.current)],
                ["PE 分位", displayPercent(indexData?.summary.pe_ttm?.percentile)],
                ["PB", displayNumber(indexData?.summary.pb?.current)],
              ]}
            />

            <OverviewCard
              icon={<Activity aria-hidden="true" />}
              category="ETF 行情"
              title={etfData?.identity.name || overview.etf.fund}
              code={etfData?.identity.code}
              status={overview.etf.meta.status}
              meta={overview.etf.meta}
              href={`/funds/${encodeURIComponent(overview.etf.fund)}`}
              refreshing={refreshingModule === "etf"}
              refreshError={moduleErrors.etf}
              onRefresh={() => void refreshModule("etf")}
              metrics={[
                ["收盘价", withUnit(etfData?.summary.latest_close, "元")],
                ["当日涨跌", displayPercent(etfData?.summary.latest_change_pct)],
                ["成交额", withUnit(etfData?.summary.latest_turnover_yi_cny, "亿元")],
                ["当前回撤", displayPercent(etfData?.summary.current_drawdown_pct)],
              ]}
            />

            <OverviewCard
              icon={<Database aria-hidden="true" />}
              category="主动基金"
              title={fundData?.fund.name || overview.fund.fund}
              code={fundData?.fund.code}
              status={overview.fund.meta.status}
              meta={overview.fund.meta}
              href={`/funds/${encodeURIComponent(overview.fund.fund)}/product`}
              refreshing={refreshingModule === "fund"}
              refreshError={moduleErrors.fund}
              onRefresh={() => void refreshModule("fund")}
              metrics={[
                ["最新净值", displayNumber(fundData?.metrics?.latest_value)],
                ["历史位置", displayPercent(fundData?.metrics?.history_position_percentile)],
                ["年化波动", displayPercent(fundData?.metrics?.annualized_volatility_pct)],
                ["最大回撤", displayPercent(fundData?.metrics?.max_drawdown_pct)],
              ]}
            />

            <OverviewCard
              icon={<Landmark aria-hidden="true" />}
              category="股票估值"
              title={stockData?.stock.name || overview.stock.stock}
              code={stockData?.stock.qualified_code}
              status={overview.stock.meta.status}
              meta={overview.stock.meta}
              href={`/stocks/${encodeURIComponent(overview.stock.stock)}`}
              refreshing={refreshingModule === "stock"}
              refreshError={moduleErrors.stock}
              onRefresh={() => void refreshModule("stock")}
              metrics={[
                ["前复权价格", withUnit(stockData?.summary.stock_price.current, "元")],
                ["PE TTM", displayNumber(stockData?.summary.pe_ttm.current)],
                ["PE 分位", displayPercent(stockData?.summary.pe_ttm.percentile)],
                ["PB", displayNumber(stockData?.summary.pb.current)],
              ]}
            />
          </section>

          <section className="overview-capabilities" aria-label="后续模块">
            <div>
              <strong>基金候选筛选</strong>
              <StatusBadge status={overview.fund_screening.status} />
              <span>{overview.fund_screening.message}</span>
            </div>
            <div>
              <strong>股票候选筛选</strong>
              <StatusBadge status={overview.stock_screening.status} />
              <span>{overview.stock_screening.message}</span>
            </div>
          </section>
        </>
      )}
    </main>
  );
}

function OverviewStatus({
  label,
  status,
  asOf,
}: {
  label: string;
  status: DataStatus;
  asOf: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <StatusBadge status={status} />
      <small>{asOf || "日期待确认"}</small>
    </div>
  );
}

function OverviewCard({
  icon,
  category,
  title,
  code,
  status,
  meta,
  href,
  metrics,
  refreshing,
  refreshError,
  onRefresh,
}: {
  icon: React.ReactNode;
  category: string;
  title: string;
  code?: string;
  status: DataStatus;
  meta: DatasetMeta;
  href: string;
  metrics: Array<[string, string]>;
  refreshing: boolean;
  refreshError?: string;
  onRefresh: () => void;
}) {
  return (
    <article className="overview-module">
      <header>
        <span className="overview-module-icon">{icon}</span>
        <div>
          <span>{category}</span>
          <h2>{title}</h2>
          {code && <code>{code}</code>}
        </div>
        <div className="overview-module-actions">
          <StatusBadge status={status} />
          <button
            type="button"
            aria-label={`刷新${category}`}
            title={`刷新${category}`}
            disabled={refreshing}
            onClick={onRefresh}
          >
            <RefreshCw aria-hidden="true" className={refreshing ? "spin" : ""} />
          </button>
        </div>
      </header>
      <div className="overview-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <footer>
        <div>
          <span>数据日期 {meta.as_of || "—"}</span>
          <span>审计引用 {meta.audit_refs.length}</span>
          <span>警告 {meta.warnings?.length ?? 0}</span>
          {refreshError && <b>{refreshError}</b>}
        </div>
        <Link to={href}>
          查看详情
          <ArrowRight aria-hidden="true" />
        </Link>
      </footer>
    </article>
  );
}

function OverviewLoading() {
  return (
    <section className="overview-loading" role="status">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index}>
          <span />
          <span />
          <span />
        </div>
      ))}
    </section>
  );
}

function withUnit(
  value: number | null | undefined,
  unit: string,
): string {
  return value === null || value === undefined ? "—" : `${String(value)} ${unit}`;
}

function withOverviewModule<K extends OverviewModule>(
  current: OverviewResponse,
  module: K,
  result: OverviewResponse[K],
): OverviewResponse {
  const next = { ...current, [module]: result };
  return {
    ...next,
    status: rollUpOverviewStatus([
      next.index.meta.status,
      next.etf.meta.status,
      next.fund.meta.status,
      next.stock.meta.status,
    ]),
  };
}

function rollUpOverviewStatus(statuses: DataStatus[]): DataStatus {
  if (statuses.length === 0) {
    return "unavailable";
  }
  const available = statuses.filter((status) => status === "available").length;
  const stale = statuses.filter((status) => status === "stale").length;
  const failed = statuses.filter(
    (status) => status === "unavailable" || status === "not_implemented",
  ).length;

  if (failed === statuses.length) {
    return "unavailable";
  }
  if (failed > 0) {
    return "partial";
  }
  if (stale > 0) {
    return "stale";
  }
  if (available === statuses.length) {
    return "available";
  }
  return "partial";
}

function invalidateModuleRefreshes(seq: Record<OverviewModule, number>) {
  for (const module of ["index", "etf", "fund", "stock"] as const) {
    seq[module] += 1;
  }
}
