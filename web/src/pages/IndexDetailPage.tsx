import {
  ArrowLeft,
  CalendarDays,
  Database,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { fetchIndexDetail } from "../api";
import {
  displayNumber,
  displayPercent,
  levelLabel,
  warningText,
} from "../components/display";
import StatusBadge from "../components/StatusBadge";
import {
  IndexPointChart,
  ValuationCharts,
} from "../components/ValuationCharts";
import type {
  ChartMetric,
  IndexDetailResponse,
  WindowStatistic,
} from "../types";

export default function IndexDetailPage() {
  const { index = "" } = useParams();
  const [payload, setPayload] = useState<IndexDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(
    (signal: AbortSignal) => {
      setLoading(true);
      setError(null);
      setPayload(null);
      void fetchIndexDetail(index, signal)
        .then(setPayload)
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setError(
            reason instanceof Error ? reason.message : "指数详情请求失败",
          );
        })
        .finally(() => {
          if (!signal.aborted) {
            setLoading(false);
          }
        });
    },
    [index],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  if (loading && !payload) {
    return <DetailLoading index={index} />;
  }

  if (error || !payload?.envelope?.ok || !payload.envelope.data) {
    return (
      <DetailFailure
        index={index}
        message={
          error ??
          payload?.envelope?.error?.message ??
          "当前工具没有返回可用的指数详情。"
        }
        status={payload?.meta.status}
        onRetry={() => setRefreshKey((key) => key + 1)}
      />
    );
  }

  const data = payload.envelope.data;
  const { pe_ttm: pe, pb, index_points: points } = data.charts;
  const warnings =
    payload.meta.warnings ?? payload.envelope.data_warnings ?? [];

  return (
    <main className="workbench-page detail-page">
      <div className="detail-breadcrumb">
        <Link to="/indices">
          <ArrowLeft aria-hidden="true" />
          返回指数看板
        </Link>
      </div>

      <header className="detail-heading">
        <div>
          <div className="detail-title-line">
            <h1>{data.index.name}</h1>
            <span>{data.index.qualified_code}</span>
            <StatusBadge status={payload.meta.status} />
          </div>
          <p>
            数据截至 {payload.meta.as_of || data.lookback.latest_date}，来源{" "}
            {data.actual_source.provider} / {data.actual_source.upstream}
          </p>
        </div>
        <button
          className="icon-command"
          type="button"
          aria-label="刷新指数详情"
          title="刷新指数详情"
          disabled={loading}
          onClick={() => setRefreshKey((key) => key + 1)}
        >
          <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
        </button>
      </header>

      <section className="detail-summary-band" aria-label="指数摘要">
        <SummaryMetric
          label="指数点位"
          value={points?.current}
          suffix="点"
          percentile={points?.percentile}
          level={points?.level}
        />
        <SummaryMetric
          label="PE TTM"
          value={pe?.current}
          suffix={pe?.unit}
          percentile={pe?.percentile}
          level={pe?.level}
        />
        <SummaryMetric
          label="PB"
          value={pb?.current}
          suffix={pb?.unit}
          percentile={pb?.percentile}
          level={pb?.level}
        />
        <div className="summary-asof">
          <CalendarDays aria-hidden="true" />
          <span>查询时间</span>
          <strong>{payload.envelope.queried_at}</strong>
        </div>
      </section>

      {warnings.length > 0 && (
        <section className="warning-band" aria-label="数据警告">
          <TriangleAlert aria-hidden="true" />
          <div>
            <strong>数据限制</strong>
            {warnings.map((warning, index) => (
              <span key={`${warningText(warning)}-${index}`}>
                {warningText(warning)}
              </span>
            ))}
          </div>
        </section>
      )}

      {(!pe || !pb) && (
        <section className="warning-band" aria-label="估值指标缺失">
          <TriangleAlert aria-hidden="true" />
          <div>
            <strong>估值指标不完整</strong>
            <span>
              {!pe ? "PE TTM 当前不可用；" : ""}
              {!pb ? "PB 当前不可用；" : ""}
              页面只展示通过校验的一侧，不使用零值占位。
            </span>
          </div>
        </section>
      )}

      {(pe || pb) && (
        <section className="detail-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">VALUATION HISTORY</p>
              <h2>PE / PB 历史估值</h2>
            </div>
            <span>拖动底部区间可同步缩放</span>
          </div>
          <div className="reference-legend" aria-label="估值参考线">
            <span className="reference-mean">均值 / 中位数</span>
            <span className="reference-std">均值 ±1σ</span>
            <span className="reference-p20">P20</span>
            <span className="reference-p80">P80</span>
          </div>
          <div className="chart-panel">
            <ValuationCharts pe={pe} pb={pb} />
          </div>
          <div className="metric-stat-grid">
            {pe && <MetricStatistics title="PE TTM" metric={pe} />}
            {pb && <MetricStatistics title="PB" metric={pb} />}
          </div>
        </section>
      )}

      {(pe || pb) && (
        <section className="detail-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">WINDOW COMPARISON</p>
              <h2>不同历史窗口</h2>
            </div>
            <span>只列出工具实际返回的窗口</span>
          </div>
          <WindowTable pe={pe} pb={pb} />
        </section>
      )}

      {points && (
        <section className="detail-section">
          <div className="section-heading">
            <div>
              <p className="section-kicker">INDEX LEVEL</p>
              <h2>指数点位历史</h2>
            </div>
            <span>独立纵轴，不与估值曲线合成信号</span>
          </div>
          <div className="chart-panel">
            <IndexPointChart metric={points} />
          </div>
          <div className="series-meta">
            <span>原始样本 {displayNumber(points.source_observations)}</span>
            <span>展示点 {displayNumber(points.displayed_points)}</span>
            <span>
              {points.actual_start_date} 至 {points.latest_date}
            </span>
          </div>
        </section>
      )}

      <section className="detail-section provenance-section">
        <div className="section-heading">
          <div>
            <p className="section-kicker">PROVENANCE</p>
            <h2>来源与审计</h2>
          </div>
          <ShieldCheck aria-hidden="true" />
        </div>
        <div className="provenance-grid">
          <div>
            <Database aria-hidden="true" />
            <span>数据提供方</span>
            <strong>{data.actual_source.provider}</strong>
            <small>{data.actual_source.interfaces.join(" / ")}</small>
          </div>
          <div>
            <ShieldCheck aria-hidden="true" />
            <span>数据策略</span>
            <strong>禁止模型生成市场数值</strong>
            <small>不插值 / 不前向填充 / 不补点</small>
          </div>
        </div>
        <AuditTable audit={payload.envelope.data_audit} />
      </section>

      <section className="limitations-section">
        <strong>研究限制</strong>
        {data.limitations.map((limitation) => (
          <p key={limitation}>{limitation}</p>
        ))}
      </section>
    </main>
  );
}

function SummaryMetric({
  label,
  value,
  suffix,
  percentile,
  level,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  percentile?: number;
  level?: string;
}) {
  return (
    <div className="detail-summary-item">
      <span>{label}</span>
      <div>
        <strong>{displayNumber(value)}</strong>
        {value !== null && value !== undefined && <small>{suffix}</small>}
      </div>
      <p>
        {percentile === undefined
          ? "历史分位无数据"
          : `历史分位 ${displayPercent(percentile)}`}
        {level ? <b className={`level-${level}`}>{levelLabel(level)}</b> : null}
      </p>
    </div>
  );
}

function MetricStatistics({
  title,
  metric,
}: {
  title: string;
  metric: ChartMetric;
}) {
  const items = [
    ["当前", metric.current],
    ["历史分位", `${displayPercent(metric.percentile)}`],
    ["均值", metric.mean],
    ["中位数", metric.median],
    ["最低", `${displayNumber(metric.minimum.value)} / ${metric.minimum.date}`],
    ["最高", `${displayNumber(metric.maximum.value)} / ${metric.maximum.date}`],
    ["P20", metric.quantiles.p20],
    ["P80", metric.quantiles.p80],
  ];
  return (
    <article className="metric-stat-block">
      <header>
        <strong>{title}</strong>
        <span>
          {metric.source_observations} 个样本 / {metric.displayed_points} 个展示点
        </span>
      </header>
      <dl>
        {items.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{typeof value === "number" ? displayNumber(value) : value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function WindowTable({
  pe,
  pb,
}: {
  pe: ChartMetric | null;
  pb: ChartMetric | null;
}) {
  const windows = useMemo(() => {
    const keys = new Set([
      ...Object.keys(pe?.window_statistics ?? {}),
      ...Object.keys(pb?.window_statistics ?? {}),
    ]);
    return [...keys].sort((left, right) => windowYears(left) - windowYears(right));
  }, [pb?.window_statistics, pe?.window_statistics]);

  return (
    <div className="data-table-wrap">
      <table className="data-table window-table">
        <thead>
          <tr>
            <th>窗口</th>
            <th>PE 当前 / 分位</th>
            <th>PE 中位 / P20-P80</th>
            <th>PB 当前 / 分位</th>
            <th>PB 中位 / P20-P80</th>
            <th>实际区间</th>
          </tr>
        </thead>
        <tbody>
          {windows.map((key) => (
            <tr key={key}>
              <td>
                <strong>{windowLabel(key)}</strong>
              </td>
              <WindowCells statistic={pe?.window_statistics[key]} />
              <WindowCells statistic={pb?.window_statistics[key]} />
              <td>
                {(
                  pe?.window_statistics[key] ?? pb?.window_statistics[key]
                )?.actual_start_date ?? "—"}
                <br />
                <span>
                  至{" "}
                  {(
                    pe?.window_statistics[key] ?? pb?.window_statistics[key]
                  )?.latest_date ?? "—"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WindowCells({ statistic }: { statistic?: WindowStatistic }) {
  if (!statistic) {
    return (
      <>
        <td className="missing-value">无数据</td>
        <td className="missing-value">无数据</td>
      </>
    );
  }
  return (
    <>
      <td>
        <strong>{displayNumber(statistic.current)}</strong>
        <br />
        <span>{displayPercent(statistic.percentile)}</span>
      </td>
      <td>
        <strong>{displayNumber(statistic.median)}</strong>
        <br />
        <span>
          {displayNumber(statistic.p20)} - {displayNumber(statistic.p80)}
        </span>
      </td>
    </>
  );
}

function AuditTable({ audit }: { audit: Array<Record<string, unknown>> }) {
  return (
    <details className="audit-details">
      <summary>查看 {audit.length} 条接口审计记录</summary>
      <div className="audit-table-wrap">
        <table className="audit-table">
          <thead>
            <tr>
              <th>接口</th>
              <th>校验</th>
              <th>行数</th>
              <th>frame_sha256</th>
            </tr>
          </thead>
          <tbody>
            {audit.map((item, index) => (
              <tr key={`${String(item.interface)}-${index}`}>
                <td>{String(item.interface ?? "—")}</td>
                <td>{String(item.validation ?? "—")}</td>
                <td>{String(item.row_count ?? "—")}</td>
                <td>
                  <code>{String(item.frame_sha256 ?? "—")}</code>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function DetailLoading({ index }: { index: string }) {
  return (
    <main className="workbench-page detail-page">
      <div className="detail-breadcrumb">
        <Link to="/indices">
          <ArrowLeft aria-hidden="true" />
          返回指数看板
        </Link>
      </div>
      <div className="detail-loading">
        <span className="loading-block loading-title" />
        <span className="loading-block" />
        <div className="loading-chart" />
        <strong>正在加载 {index} 的十年审计数据</strong>
      </div>
    </main>
  );
}

function DetailFailure({
  index,
  message,
  status,
  onRetry,
}: {
  index: string;
  message: string;
  status?: IndexDetailResponse["meta"]["status"];
  onRetry: () => void;
}) {
  return (
    <main className="workbench-page detail-page">
      <div className="detail-breadcrumb">
        <Link to="/indices">
          <ArrowLeft aria-hidden="true" />
          返回指数看板
        </Link>
      </div>
      <div className="detail-failure">
        <TriangleAlert aria-hidden="true" />
        <h1>{index}</h1>
        {status && <StatusBadge status={status} />}
        <p>{message}</p>
        <button type="button" onClick={onRetry}>
          重试
        </button>
      </div>
    </main>
  );
}

function windowYears(key: string): number {
  return Number.parseInt(key, 10) || Number.MAX_SAFE_INTEGER;
}

function windowLabel(key: string): string {
  const years = Number.parseInt(key, 10);
  return Number.isFinite(years) ? `${years} 年` : key;
}
