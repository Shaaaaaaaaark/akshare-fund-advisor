import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import {
  createWatchlistItem,
  deleteWatchlistItem,
  fetchWatchlist,
} from "../api";
import type {
  WatchlistEntityType,
  WatchlistItem,
} from "../types";

const TYPE_LABELS: Record<WatchlistEntityType, string> = {
  index: "指数",
  etf: "ETF",
  fund: "主动基金",
  stock: "股票",
};

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [entityType, setEntityType] = useState<WatchlistEntityType>("fund");
  const [entityCode, setEntityCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fetchWatchlist(controller.signal)
      .then(setItems)
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === "AbortError")) {
          setError(reason instanceof Error ? reason.message : "自选列表加载失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  async function addItem(event: FormEvent) {
    event.preventDefault();
    if (!entityCode.trim() || !displayName.trim() || submitting) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const created = await createWatchlistItem({
        entity_type: entityType,
        entity_code: entityCode.trim(),
        display_name: displayName.trim(),
      });
      setItems((current) => [created, ...current]);
      setEntityCode("");
      setDisplayName("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "添加自选失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function removeItem(item: WatchlistItem) {
    setError(null);
    try {
      await deleteWatchlistItem(item.id);
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "删除自选失败");
    }
  }

  return (
    <main className="workbench-page watchlist-page">
      <header className="page-heading watchlist-heading">
        <div>
          <p className="section-kicker">WATCHLIST</p>
          <h1>研究自选</h1>
          <p>保存关注标的；行情与估值仍在进入详情时实时读取审计数据。</p>
        </div>
        <strong>{items.length} / 100</strong>
      </header>

      <form className="watchlist-form" onSubmit={addItem}>
        <label>
          <span>类型</span>
          <select
            value={entityType}
            onChange={(event) =>
              setEntityType(event.target.value as WatchlistEntityType)
            }
          >
            {Object.entries(TYPE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>代码或指数名</span>
          <input
            value={entityCode}
            maxLength={64}
            placeholder="例如 000001"
            onChange={(event) => setEntityCode(event.target.value)}
          />
        </label>
        <label>
          <span>显示名称</span>
          <input
            value={displayName}
            maxLength={128}
            placeholder="例如 华夏成长"
            onChange={(event) => setDisplayName(event.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={submitting || !entityCode.trim() || !displayName.trim()}
        >
          <Plus aria-hidden="true" />
          添加
        </button>
      </form>

      {error && (
        <div className="watchlist-error" role="alert">
          {error}
        </div>
      )}

      <section className="watchlist-table" aria-label="自选标的">
        <header>
          <span>标的</span>
          <span>类型</span>
          <span>加入时间</span>
          <span>操作</span>
        </header>
        {loading ? (
          <p className="watchlist-empty">正在加载自选列表</p>
        ) : items.length === 0 ? (
          <p className="watchlist-empty">暂无自选标的</p>
        ) : (
          items.map((item) => (
            <div className="watchlist-row" key={item.id}>
              <div>
                <strong>{item.display_name}</strong>
                <code>{item.entity_code}</code>
              </div>
              <span>{TYPE_LABELS[item.entity_type]}</span>
              <time dateTime={item.created_at}>
                {new Date(item.created_at).toLocaleString("zh-CN")}
              </time>
              <div className="watchlist-actions">
                <Link
                  to={detailPath(item)}
                  aria-label={`查看${item.display_name}`}
                  title="查看详情"
                >
                  <ExternalLink aria-hidden="true" />
                </Link>
                <button
                  type="button"
                  aria-label={`删除${item.display_name}`}
                  title="删除"
                  onClick={() => void removeItem(item)}
                >
                  <Trash2 aria-hidden="true" />
                </button>
              </div>
            </div>
          ))
        )}
      </section>
    </main>
  );
}

function detailPath(item: WatchlistItem): string {
  const code = encodeURIComponent(item.entity_code);
  return {
    index: `/indices/${code}`,
    etf: `/funds/${code}`,
    fund: `/funds/${code}/product`,
    stock: `/stocks/${code}`,
  }[item.entity_type];
}
