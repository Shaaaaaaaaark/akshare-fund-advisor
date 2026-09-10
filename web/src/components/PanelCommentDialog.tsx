import { MessageSquare, RefreshCw, Send, X } from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import { createPanelComment, fetchPanelComments } from "../api";
import type { PanelComment, PanelCommentFeed } from "../types";

interface PanelCommentDialogProps {
  open: boolean;
  clientId: string;
  fund: string;
  onClose: () => void;
}

export default function PanelCommentDialog({
  open,
  clientId,
  fund,
  onClose,
}: PanelCommentDialogProps) {
  const [feed, setFeed] = useState<PanelCommentFeed | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
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
    void fetchPanelComments(clientId, fund, controller.signal)
      .then(setFeed)
      .catch((reason: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setError(reason instanceof Error ? reason.message : "评论读取失败");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [clientId, fund, open, reloadKey]);

  if (!open) {
    return null;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (content.length < 2 || content.length > 280) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const comment = await createPanelComment({
        client_id: clientId,
        fund,
        content,
      });
      setFeed((current) => appendComment(current, fund, comment));
      setDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "评论提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="panel-comment-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        className="panel-comment-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="panel-comment-title"
      >
        <header>
          <div>
            <h2 id="panel-comment-title">
              <MessageSquare aria-hidden="true" />
              ETF 交流区
            </h2>
            <span>{fund} · {feed?.count ?? 0} 条评论</span>
          </div>
          <div className="panel-comment-header-actions">
            <button
              type="button"
              aria-label="刷新评论"
              title="刷新"
              disabled={loading}
              onClick={() => setReloadKey((key) => key + 1)}
            >
              <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
            </button>
            <button
              type="button"
              aria-label="关闭交流区"
              title="关闭"
              onClick={onClose}
            >
              <X aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="panel-comment-feed" aria-live="polite">
          {loading && !feed ? (
            <div className="panel-comment-state">正在读取评论</div>
          ) : feed?.comments.length ? (
            feed.comments.map((comment) => (
              <article
                key={comment.id}
                className={comment.mine ? "mine" : undefined}
              >
                <header>
                  <strong>{comment.visitor_label}</strong>
                  {comment.mine && <span>我的评论</span>}
                  <time dateTime={comment.created_at}>
                    {displayTime(comment.created_at)}
                  </time>
                </header>
                <p>{comment.content}</p>
              </article>
            ))
          ) : (
            <div className="panel-comment-state">暂无评论</div>
          )}
        </div>

        {error && <div className="panel-comment-error">{error}</div>}

        <form onSubmit={submit}>
          <textarea
            value={draft}
            minLength={2}
            maxLength={280}
            rows={3}
            aria-label="评论内容"
            placeholder="写下你的看法"
            disabled={submitting}
            onChange={(event) => setDraft(event.target.value)}
          />
          <footer>
            <span>{draft.length}/280</span>
            <button
              type="submit"
              disabled={
                submitting ||
                draft.trim().length < 2 ||
                draft.trim().length > 280
              }
            >
              <Send aria-hidden="true" />
              {submitting ? "提交中" : "发表"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function appendComment(
  feed: PanelCommentFeed | null,
  fund: string,
  comment: PanelComment,
): PanelCommentFeed {
  const comments = [
    comment,
    ...(feed?.comments ?? []).filter((item) => item.id !== comment.id),
  ].slice(0, 20);
  return {
    fund,
    count: Math.max(comments.length, (feed?.count ?? 0) + 1),
    comments,
  };
}

function displayTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
