import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CircleHelp,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { ETFDashboardData, ETFRecentRow } from "../types";
import { displayMetric, displaySigned, valueTone } from "./display";

type TableSortKey =
  | "date"
  | "close"
  | "daily_change_pct"
  | "turnover_yi_cny"
  | "turnover_percentile_pct"
  | "volume_yi_units"
  | "drawdown_pct"
  | "total_shares_change_yi_units"
  | "financing_balance_change_yi_cny"
  | "component_financing_balance_change_yi_cny";

interface TableSort {
  key: TableSortKey;
  direction: "asc" | "desc";
}

export default function ETFTrendPanel({
  data,
  resetVersion,
  onHelp,
}: {
  data: ETFDashboardData;
  resetVersion: number;
  onHelp: (key: string) => void;
}) {
  const supplemental = data.supplemental;
  const recentDates = useMemo(
    () => data.recent_rows.map((row) => row.date).sort(),
    [data.recent_rows],
  );
  const auditedRange = supplemental?.range_summaries[0];
  const defaultEnd = auditedRange?.latest_date ?? recentDates.at(-1) ?? "";
  const defaultStart =
    auditedRange?.actual_start_date ??
    recentDates[Math.max(0, recentDates.length - 5)] ??
    defaultEnd;
  const [expanded, setExpanded] = useState(false);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [draftStart, setDraftStart] = useState(defaultStart);
  const [draftEnd, setDraftEnd] = useState(defaultEnd);
  const [sort, setSort] = useState<TableSort>({
    key: "date",
    direction: "desc",
  });
  const rows = useMemo(
    () =>
      sortRows(data.recent_rows, sort).filter(
        (row) =>
          (!start || row.date >= start) && (!end || row.date <= end),
      ),
    [data.recent_rows, end, sort, start],
  );
  const supplementalRange = supplemental?.range_summaries.find(
    (range) =>
      range.actual_start_date === start && range.latest_date === end,
  );

  useEffect(() => {
    document.body.classList.toggle("etf-trend-expanded", expanded);
    return () => document.body.classList.remove("etf-trend-expanded");
  }, [expanded]);

  useEffect(() => {
    setStart(defaultStart);
    setEnd(defaultEnd);
    setDraftStart(defaultStart);
    setDraftEnd(defaultEnd);
  }, [data.identity.code, defaultEnd, defaultStart]);

  useEffect(() => {
    if (resetVersion === 0) {
      return;
    }
    setExpanded(false);
    setStart(defaultStart);
    setEnd(defaultEnd);
    setDraftStart(defaultStart);
    setDraftEnd(defaultEnd);
    setSort({ key: "date", direction: "desc" });
  }, [defaultEnd, defaultStart, resetVersion]);

  return (
    <>
      {expanded && (
        <button
          type="button"
          className="etf-trend-backdrop"
          aria-label="关闭趋势表"
          onClick={() => setExpanded(false)}
        />
      )}
      <aside
        id="etf-trend-table"
        className={`etf-trend-panel ${expanded ? "expanded" : ""}`}
        aria-label="最近交易日趋势看板"
      >
        <header>
          <div>
            <h2>{data.identity.name}最近一周趋势</h2>
            <span>点击表头排序</span>
          </div>
          <button
            type="button"
            className="etf-trend-expand"
            aria-expanded={expanded}
            onClick={() => setExpanded((current) => !current)}
          >
            {expanded ? (
              <Minimize2 aria-hidden="true" />
            ) : (
              <Maximize2 aria-hidden="true" />
            )}
            {expanded ? "收起" : "展开"}
          </button>
        </header>
        <form
          className="etf-trend-range-panel"
          onSubmit={(event) => {
            event.preventDefault();
            if (!draftStart || !draftEnd || draftStart > draftEnd) {
              return;
            }
            setStart(draftStart);
            setEnd(draftEnd);
          }}
        >
          <label>
            <span>开始</span>
            <input
              type="date"
              min={recentDates[0]}
              max={draftEnd || defaultEnd}
              value={draftStart}
              onChange={(event) => setDraftStart(event.target.value)}
            />
          </label>
          <label>
            <span>结束</span>
            <input
              type="date"
              min={draftStart || recentDates[0]}
              max={defaultEnd}
              value={draftEnd}
              onChange={(event) => setDraftEnd(event.target.value)}
            />
          </label>
          <button
            type="submit"
            disabled={!draftStart || !draftEnd || draftStart > draftEnd}
          >
            应用
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setDraftStart(defaultStart);
              setDraftEnd(defaultEnd);
              setStart(defaultStart);
              setEnd(defaultEnd);
            }}
          >
            最近一周
          </button>
        </form>
        <section className="etf-trend-summary" aria-label="趋势合计摘要">
          <div className="etf-trend-summary-main">
            <span>
              {start} 至 {end}
            </span>
            <strong>{data.identity.name}</strong>
          </div>
          <div>
            <span>区间记录</span>
            <strong>{rows.length} 条</strong>
          </div>
          <div>
            <span>合计份额变动</span>
            <strong className={valueTone(supplementalRange?.share_change_yi_units)}>
              {supplementalRange
                ? displaySigned(
                    supplementalRange.share_change_yi_units,
                    " 亿份",
                  )
                : "当前区间不可用"}
            </strong>
          </div>
          <div>
            <span>合计净申赎</span>
            <strong>待接入</strong>
          </div>
          <div>
            <span>ETF融资余额变动</span>
            <strong
              className={valueTone(
                supplementalRange?.financing_net_change_yi_cny,
              )}
            >
              {supplementalRange
                ? displaySigned(
                    supplementalRange.financing_net_change_yi_cny,
                    " 亿元",
                  )
                : "当前区间不可用"}
            </strong>
          </div>
          <div>
            <span>成分融资余额变动</span>
            <strong
              className={valueTone(
                supplementalRange?.component_financing_net_change_yi_cny,
              )}
            >
              {supplementalRange
                ? componentFinancingValue(
                    supplementalRange.component_financing_net_change_yi_cny,
                    supplemental?.component_financing.latest
                      ?.reported_component_count,
                    supplemental?.component_financing.latest
                      ?.constituent_count,
                  )
                : "当前区间不可用"}
            </strong>
          </div>
        </section>
        <div className="etf-trend-table-wrap">
          <table className="etf-trend-table">
            <thead>
              <tr>
                <StaticHeader
                  label="ETF / 合计"
                  helpKey="etf_scope"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="日期"
                  sortKey="date"
                  sort={sort}
                  onSort={setSort}
                  helpKey="date"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="价格变动"
                  sortKey="daily_change_pct"
                  sort={sort}
                  onSort={setSort}
                  helpKey="daily_change"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="成交额"
                  sortKey="turnover_yi_cny"
                  sort={sort}
                  onSort={setSort}
                  helpKey="turnover"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="成交额分位"
                  sortKey="turnover_percentile_pct"
                  sort={sort}
                  onSort={setSort}
                  helpKey="turnover_percentile"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="净份额变动"
                  sortKey="total_shares_change_yi_units"
                  sort={sort}
                  onSort={setSort}
                  helpKey="share_change"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="变动绝对值分位"
                  helpKey="share_change_percentile"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="净申赎金额"
                  helpKey="net_subscription"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="净申赎绝对值分位"
                  helpKey="net_subscription_percentile"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="净申赎/指数成交额"
                  helpKey="net_subscription_ratio"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="ETF融资余额变动"
                  sortKey="financing_balance_change_yi_cny"
                  sort={sort}
                  onSort={setSort}
                  helpKey="etf_financing_change"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="ETF融资分位"
                  helpKey="etf_financing_percentile"
                  onHelp={onHelp}
                />
                <SortableHeader
                  label="成分融资余额变动"
                  sortKey="component_financing_balance_change_yi_cny"
                  sort={sort}
                  onSort={setSort}
                  helpKey="constituent_financing_change"
                  onHelp={onHelp}
                />
                <StaticHeader
                  label="成分融资分位"
                  helpKey="constituent_financing_percentile"
                  onHelp={onHelp}
                />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.date}>
                  <TrendCell label="ETF / 合计" value={data.identity.name} />
                  <TrendCell label="日期" value={row.date} />
                  <TrendCell
                    label="价格变动"
                    value={displaySigned(row.daily_change_pct, "%")}
                    className={valueTone(row.daily_change_pct)}
                  />
                  <TrendCell
                    label="成交额"
                    value={displayMetric(row.turnover_yi_cny, " 亿")}
                  />
                  <TrendCell
                    label="成交额分位"
                    value={displayMetric(row.turnover_percentile_pct, "%")}
                  />
                  <TrendCell
                    label="净份额变动"
                    value={displaySigned(
                      row.total_shares_change_yi_units,
                      " 亿份",
                    )}
                    className={valueTone(row.total_shares_change_yi_units)}
                  />
                  <TrendCell label="变动绝对值分位" value="待接入" />
                  <TrendCell label="净申赎金额" value="待接入" />
                  <TrendCell label="净申赎绝对值分位" value="待接入" />
                  <TrendCell label="净申赎/指数成交额" value="待接入" />
                  <TrendCell
                    label="ETF融资余额变动"
                    value={displaySigned(
                      row.financing_balance_change_yi_cny,
                      " 亿元",
                    )}
                    className={valueTone(
                      row.financing_balance_change_yi_cny,
                    )}
                  />
                  <TrendCell label="ETF融资分位" value="待接入" />
                  <TrendCell
                    label="成分融资余额变动"
                    value={componentFinancingValue(
                      row.component_financing_balance_change_yi_cny,
                      row.component_financing_reported_count,
                      row.component_financing_constituent_count,
                    )}
                    className={valueTone(
                      row.component_financing_balance_change_yi_cny,
                    )}
                  />
                  <TrendCell label="成分融资分位" value="待接入" />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </aside>
    </>
  );
}

function TrendCell({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <td>
      <span className="etf-mobile-cell-label">{label}</span>
      <span className={`etf-trend-cell-value ${className}`}>{value}</span>
    </td>
  );
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  helpKey,
  onHelp,
}: {
  label: string;
  sortKey: TableSortKey;
  sort: TableSort;
  onSort: (sort: TableSort) => void;
  helpKey: string;
  onHelp: (key: string) => void;
}) {
  const active = sort.key === sortKey;
  const Icon = !active
    ? ArrowUpDown
    : sort.direction === "asc"
      ? ArrowUp
      : ArrowDown;
  return (
    <th
      aria-sort={
        active
          ? sort.direction === "asc"
            ? "ascending"
            : "descending"
          : "none"
      }
    >
      <div className="etf-table-heading">
        <button
          type="button"
          className="etf-sort-button"
          onClick={() =>
            onSort({
              key: sortKey,
              direction: active && sort.direction === "asc" ? "desc" : "asc",
            })
          }
        >
          {label}
          <Icon aria-hidden="true" />
        </button>
        <button
          type="button"
          className="etf-help-button"
          aria-label={`说明：${label}`}
          title={`${label}说明`}
          onClick={() => onHelp(helpKey)}
        >
          <CircleHelp aria-hidden="true" />
        </button>
      </div>
    </th>
  );
}

function StaticHeader({
  label,
  helpKey,
  onHelp,
}: {
  label: string;
  helpKey: string;
  onHelp: (key: string) => void;
}) {
  return (
    <th>
      <div className="etf-table-heading">
        <span>{label}</span>
        <button
          type="button"
          className="etf-help-button"
          aria-label={`说明：${label}`}
          title={`${label}说明`}
          onClick={() => onHelp(helpKey)}
        >
          <CircleHelp aria-hidden="true" />
        </button>
      </div>
    </th>
  );
}

function componentFinancingValue(
  value: number | null | undefined,
  reportedCount: number | null | undefined,
  constituentCount: number | null | undefined,
): string {
  const amount = displaySigned(value, " 亿元");
  if (
    amount === "—" ||
    reportedCount === null ||
    reportedCount === undefined ||
    constituentCount === null ||
    constituentCount === undefined
  ) {
    return amount;
  }
  return `${amount} · 覆盖 ${reportedCount}/${constituentCount}`;
}

function sortRows(rows: ETFRecentRow[], sort: TableSort): ETFRecentRow[] {
  return [...rows].sort((left, right) => {
    const leftValue = left[sort.key];
    const rightValue = right[sort.key];
    if (leftValue == null && rightValue == null) {
      return 0;
    }
    if (leftValue == null) {
      return 1;
    }
    if (rightValue == null) {
      return -1;
    }
    const comparison =
      typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue));
    return sort.direction === "asc" ? comparison : -comparison;
  });
}
