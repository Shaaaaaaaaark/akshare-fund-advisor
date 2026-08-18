import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarDays,
  Database,
  RefreshCw,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { fetchIndices } from "../api";
import {
  displayNumber,
  displayPercent,
  levelLabel,
  warningText,
} from "../components/display";
import StatusBadge from "../components/StatusBadge";
import type {
  IndexRow,
  IndicesResponse,
  MetricSummary,
} from "../types";

type Filter = "all" | "available" | "attention";
type SortKey =
  | "index"
  | "latest_point"
  | "pe_current"
  | "pe_percentile"
  | "pb_current"
  | "pb_percentile"
  | "as_of"
  | "status";
type SortDirection = "asc" | "desc";
interface SortConfig {
  key: SortKey;
  direction: SortDirection;
}

export default function IndicesPage() {
  const [payload, setPayload] = useState<IndicesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<SortConfig | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback((signal: AbortSignal) => {
    setLoading(true);
    setError(null);
    void fetchIndices(signal)
      .then(setPayload)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          return;
        }
        setError(reason instanceof Error ? reason.message : "指数数据请求失败");
      })
      .finally(() => {
        if (!signal.aborted) {
          setLoading(false);
        }
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  const rows = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const filtered = (payload?.rows ?? []).filter((row) => {
      if (normalized && !row.index.toLowerCase().includes(normalized)) {
        return false;
      }
      if (filter === "available") {
        return row.meta.status === "available";
      }
      if (filter === "attention") {
        return (
          row.meta.status !== "available" ||
          Boolean(row.meta.warnings?.length)
        );
      }
      return true;
    });
    return sortRows(filtered, sort);
  }, [filter, payload?.rows, query, sort]);

  const availableCount =
    payload?.rows.filter((row) => row.meta.status === "available").length ?? 0;
  const warningCount =
    payload?.rows.filter((row) => Boolean(row.meta.warnings?.length)).length ??
    0;

  return (
    <main className="workbench-page indices-page">
      <header className="page-heading">
        <div>
          <p className="section-kicker">MARKET DATA</p>
          <h1>指数估值与行情</h1>
          <p>
            当前值、历史分位和日期均来自审计后的工具结果，PE 与 PB
            独立展示。
          </p>
        </div>
        <button
          className="icon-command"
          type="button"
          aria-label="刷新指数数据"
          title="刷新指数数据"
          disabled={loading}
          onClick={() => setRefreshKey((current) => current + 1)}
        >
          <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
        </button>
      </header>

      <section className="dataset-strip" aria-label="数据集状态">
        <div>
          <Database aria-hidden="true" />
          <span>关注指数</span>
          <strong>{payload?.rows.length ?? "—"}</strong>
        </div>
        <div>
          <span>可用</span>
          <strong>{payload ? availableCount : "—"}</strong>
        </div>
        <div>
          <span>警告</span>
          <strong>{payload ? warningCount : "—"}</strong>
        </div>
        <div className="dataset-strip-status">
          <span>数据集状态</span>
          {payload ? <StatusBadge status={payload.status} /> : <span>加载中</span>}
        </div>
      </section>

      <section className="table-section">
        <div className="table-toolbar">
          <label className="search-control">
            <Search aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索指数名称"
              aria-label="搜索指数名称"
            />
          </label>

          <div className="segmented-control" aria-label="状态筛选">
            {(
              [
                ["all", "全部"],
                ["available", "可用"],
                ["attention", "需关注"],
              ] as Array<[Filter, string]>
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={filter === value ? "active" : ""}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>

          <span className="table-sort-hint">
            <ArrowUpDown aria-hidden="true" />
            点击表头排序
          </span>
        </div>

        {error ? (
          <ErrorState message={error} onRetry={() => setRefreshKey((key) => key + 1)} />
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <SortableHeader
                    label="指数"
                    sortKey="index"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="最新点位"
                    sortKey="latest_point"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="PE TTM"
                    sortKey="pe_current"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="PE 分位"
                    sortKey="pe_percentile"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="PB"
                    sortKey="pb_current"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="PB 分位"
                    sortKey="pb_percentile"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="数据日期"
                    sortKey="as_of"
                    sort={sort}
                    onSort={setSort}
                  />
                  <SortableHeader
                    label="状态"
                    sortKey="status"
                    sort={sort}
                    onSort={setSort}
                  />
                </tr>
              </thead>
              <tbody>
                {loading && !payload
                  ? Array.from({ length: 6 }, (_, index) => (
                    <LoadingRow key={index} />
                  ))
                  : rows.map((row) => <IndexTableRow key={row.index} row={row} />)}
              </tbody>
            </table>
            {!loading && rows.length === 0 && (
              <div className="table-empty">没有符合当前条件的指数。</div>
            )}
          </div>
        )}
      </section>

      <footer className="page-data-note">
        <CalendarDays aria-hidden="true" />
        <span>
          日频数据不等同于实时行情。历史分位只描述历史位置，不预测未来收益。
        </span>
      </footer>
    </main>
  );
}

function IndexTableRow({ row }: { row: IndexRow }) {
  const warnings = row.meta.warnings ?? [];
  return (
    <tr className={row.meta.status !== "available" ? "row-muted" : ""}>
      <td>
        <Link className="index-link" to={`/indices/${encodeURIComponent(row.index)}`}>
          <strong>{row.index}</strong>
          <span>查看历史估值</span>
        </Link>
      </td>
      <td className="numeric-cell">
        <strong>{displayNumber(row.latest_point)}</strong>
        <span>点</span>
      </td>
      <td>
        <MetricCurrentCell metric={row.pe_ttm} />
      </td>
      <td>
        <MetricPercentileCell metric={row.pe_ttm} />
      </td>
      <td>
        <MetricCurrentCell metric={row.pb} />
      </td>
      <td>
        <MetricPercentileCell metric={row.pb} />
      </td>
      <td>
        <span className="date-cell">{row.meta.as_of || "—"}</span>
      </td>
      <td>
        <StatusBadge status={row.meta.status} />
        {warnings.length > 0 && (
          <span className="row-warning" title={warnings.map(warningText).join("\n")}>
            {warnings.length} 条警告
          </span>
        )}
      </td>
    </tr>
  );
}

function MetricCurrentCell({ metric }: { metric: MetricSummary | null }) {
  if (!metric || metric.current === null) {
    return <span className="missing-value">无数据</span>;
  }
  return (
    <div className="metric-current-cell">
      <strong>{displayNumber(metric.current)}</strong>
      <span className={`level-label level-${metric.level}`}>
        {levelLabel(metric.level)}
      </span>
    </div>
  );
}

function MetricPercentileCell({ metric }: { metric: MetricSummary | null }) {
  if (!metric || metric.percentile === null) {
    return <span className="missing-value">无数据</span>;
  }
  return (
    <div className="metric-percentile-cell">
      <span>{displayPercent(metric.percentile)}</span>
      <div className="percentile-track" aria-hidden="true">
        <i style={{ width: `${metric.percentile}%` }} />
      </div>
    </div>
  );
}

function LoadingRow() {
  return (
    <tr className="loading-row">
      {Array.from({ length: 8 }, (_, index) => (
        <td key={index}>
          <span />
        </td>
      ))}
    </tr>
  );
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="error-state">
      <strong>当前无法加载指数数据</strong>
      <span>{message}</span>
      <button type="button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortConfig | null;
  onSort: (sort: SortConfig) => void;
}) {
  const active = sort?.key === sortKey;
  const direction = active ? sort.direction : null;
  const Icon =
    direction === "asc"
      ? ArrowUp
      : direction === "desc"
        ? ArrowDown
        : ArrowUpDown;
  return (
    <th aria-sort={active ? (direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        className={active ? "sortable-header active" : "sortable-header"}
        type="button"
        onClick={() =>
          onSort({
            key: sortKey,
            direction:
              active && sort.direction === "asc" ? "desc" : "asc",
          })
        }
        aria-label={`按${label}${direction === "asc" ? "降序" : "升序"}排列`}
      >
        {label}
        <Icon aria-hidden="true" />
      </button>
    </th>
  );
}

function sortRows(
  rows: IndexRow[],
  sort: SortConfig | null,
): IndexRow[] {
  if (!sort) {
    return rows;
  }
  return [...rows].sort((left, right) => {
    const leftValue = sortValue(left, sort.key);
    const rightValue = sortValue(right, sort.key);
    const leftMissing =
      leftValue === null ||
      (sort.key !== "status" && left.meta.status !== "available");
    const rightMissing =
      rightValue === null ||
      (sort.key !== "status" && right.meta.status !== "available");
    if (leftMissing && rightMissing) {
      return 0;
    }
    if (leftMissing) {
      return 1;
    }
    if (rightMissing) {
      return -1;
    }
    const comparison =
      typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue), "zh-CN");
    return sort.direction === "asc" ? comparison : -comparison;
  });
}

function sortValue(
  row: IndexRow,
  key: SortKey,
): number | string | null {
  if (key === "index") {
    return row.index;
  }
  if (key === "as_of") {
    return row.meta.as_of || null;
  }
  if (key === "status") {
    return {
      available: 0,
      partial: 1,
      stale: 2,
      unavailable: 3,
      not_implemented: 4,
    }[row.meta.status];
  }
  if (row.meta.status !== "available") {
    return null;
  }
  if (key === "latest_point") {
    return row.latest_point;
  }
  if (key === "pe_current") {
    return row.pe_ttm?.current ?? null;
  }
  if (key === "pe_percentile") {
    return row.pe_ttm?.percentile ?? null;
  }
  if (key === "pb_current") {
    return row.pb?.current ?? null;
  }
  return row.pb?.percentile ?? null;
}
