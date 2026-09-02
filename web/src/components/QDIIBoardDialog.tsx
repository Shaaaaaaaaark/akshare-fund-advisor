import { Globe, X } from "lucide-react";
import { useEffect, useState } from "react";

import { fetchQDIIPurchaseBoard } from "../api";
import type { QDIIBoardData, QDIIBoardFund, QDIIBoardResponse } from "../types";

interface QDIIBoardDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function QDIIBoardDialog({ open, onClose }: QDIIBoardDialogProps) {
  const [response, setResponse] = useState<QDIIBoardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    if (!open) {
      return;
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchQDIIPurchaseBoard(controller.signal)
      .then((payload) => setResponse(payload))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(reason instanceof Error ? reason.message : "榜单加载失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [open, reloadKey]);

  if (!open) {
    return null;
  }

  const data: QDIIBoardData | null = response?.envelope?.data ?? null;
  const envelopeError = response?.envelope?.error ?? null;
  const auditRefs = response?.meta.audit_refs ?? [];

  return (
    <div
      className="etf-help-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        className="etf-qdii-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="etf-qdii-title"
      >
        <header>
          <div>
            <h2 id="etf-qdii-title">
              <Globe aria-hidden="true" />
              QDII / 海外基金申购限额榜
            </h2>
            {data ? (
              <span className="etf-qdii-subtitle">
                {data.scope} · 最新数据日期 {data.latest_source_report_date ?? "—"}
              </span>
            ) : null}
          </div>
          <button
            type="button"
            aria-label="关闭限额榜"
            title="关闭"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </header>

        <div className="etf-qdii-body">
          {loading && <p className="etf-qdii-hint">正在读取交易所申赎状态…</p>}

          {!loading && error && (
            <div className="etf-qdii-error">
              <strong>当前无法确认榜单</strong>
              <span>{error}</span>
              <button type="button" onClick={() => setReloadKey((key) => key + 1)}>
                重试
              </button>
            </div>
          )}

          {!loading && !error && envelopeError && (
            <div className="etf-qdii-error">
              <strong>当前无法确认榜单</strong>
              <span>{envelopeError.message}</span>
            </div>
          )}

          {!loading && !error && data && (
            <>
              <div className="etf-qdii-summary">
                <span>
                  限大额 <b>{data.summary.limited_large_count}</b> 只
                </span>
                <span>
                  已披露限额{" "}
                  <b>{data.summary.limited_large_amount_disclosed_count}</b> 只
                </span>
                <span>
                  暂停申购 <b>{data.summary.suspended_count}</b> 只
                </span>
                <span>
                  分类 <b>{data.summary.category_count}</b> 个
                </span>
              </div>

              {data.categories.map((category) => (
                <section className="etf-qdii-category" key={category.theme}>
                  <h3>
                    {category.theme}
                    <small>
                      限大额 {category.limited_large_count} · 暂停{" "}
                      {category.suspended_count}
                    </small>
                  </h3>
                  {category.limited_large.length > 0 && (
                    <FundTier label="限大额" funds={category.limited_large} />
                  )}
                  {category.suspended.length > 0 && (
                    <FundTier label="暂停申购" funds={category.suspended} />
                  )}
                </section>
              ))}

              <ul className="etf-qdii-notes">
                {data.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
              <code className="etf-qdii-audit">
                {auditRefs.join(" · ") || "无可用审计指纹"}
              </code>
            </>
          )}
        </div>
      </section>
    </div>
  );
}

function FundTier({ label, funds }: { label: string; funds: QDIIBoardFund[] }) {
  return (
    <div className="etf-qdii-tier">
      <span className="etf-qdii-tier-label">{label}</span>
      <table>
        <thead>
          <tr>
            <th>代码</th>
            <th>名称</th>
            <th>日累计限额</th>
          </tr>
        </thead>
        <tbody>
          {funds.map((fund) => (
            <tr key={fund.code}>
              <td>{fund.code}</td>
              <td title={fund.fund_type}>{fund.name}</td>
              <td>{limitText(fund)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function limitText(fund: QDIIBoardFund): string {
  if (fund.status_tier === "suspended") {
    return "暂停申购";
  }
  if (fund.amount_disclosed && fund.effective_daily_limit_cny !== null) {
    return `${formatCny(fund.effective_daily_limit_cny)} / 日`;
  }
  return "限大额（未披露金额）";
}

function formatCny(value: number): string {
  if (value >= 100_000_000) {
    return `${(value / 100_000_000).toFixed(2)} 亿元`;
  }
  if (value >= 10_000) {
    return `${(value / 10_000).toFixed(2)} 万元`;
  }
  return `${value} 元`;
}
