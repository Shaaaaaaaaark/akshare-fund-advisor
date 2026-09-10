import { Activity } from "lucide-react";

import type { MarketPulseData } from "../types";

interface MarketPulsePanelProps {
  data: MarketPulseData | null;
  loading: boolean;
  error: string | null;
}

export default function MarketPulsePanel({
  data,
  loading,
  error,
}: MarketPulsePanelProps) {
  return (
    <section className="market-pulse-panel" aria-label="当前股市热门板块">
      <header>
        <strong>
          <Activity aria-hidden="true" />
          热门板块
        </strong>
        <span>{snapshotText(data?.snapshot_at)}</span>
      </header>

      {loading && !data ? (
        <div className="market-pulse-state" role="status">
          正在读取市场快照
        </div>
      ) : error || !data ? (
        <div className="market-pulse-state market-pulse-error">
          热门板块暂不可用
        </div>
      ) : (
        <ol className="market-pulse-list">
          {data.sectors.slice(0, 5).map((sector) => (
            <li key={sector.name}>
              <span className="market-pulse-rank">{sector.rank}</span>
              <strong title={sector.name}>{sector.name}</strong>
              <span
                className={
                  sector.change_pct >= 0
                    ? "market-pulse-up"
                    : "market-pulse-down"
                }
              >
                {signedPercent(sector.change_pct)}
              </span>
              <small title={leaderTitle(sector.leading_stock, sector.leading_stock_change_pct)}>
                {sector.leading_stock || "暂无领涨股"}
              </small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function signedPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function snapshotText(value?: string): string {
  if (!value) {
    return "实时快照";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "实时快照";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function leaderTitle(
  name: string | null,
  changePct: number | null,
): string {
  if (!name) {
    return "暂无领涨股";
  }
  return changePct === null
    ? `领涨：${name}`
    : `领涨：${name} ${signedPercent(changePct)}`;
}
