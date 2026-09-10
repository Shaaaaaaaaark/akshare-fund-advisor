import { Bot, Send, X } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { streamChat } from "../api";
import type { AgentResponse, ChatMessage } from "../types";

interface ResearchAgentDialogProps {
  open: boolean;
  fundCode: string;
  fundName?: string;
  onClose: () => void;
}

export default function ResearchAgentDialog({
  open,
  fundCode,
  fundName,
  onClose,
}: ResearchAgentDialogProps) {
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const answerEndRef = useRef<HTMLDivElement>(null);

  const suggestions = [
    `分析 ${fundCode} 当前行情与回撤`,
    `${fundCode} 最近一周发生了什么`,
    `${fundCode} 最近一个月表现如何`,
    `${fundCode} 当前能否申购`,
    `解释 ${fundCode} 的成交额和成交量`,
    `这只 ETF 的数据更新到哪天`,
    `当前数据有哪些限制`,
    `价格上涨但成交额下降怎么看`,
    `比较 ${fundCode} 的短期和中期表现`,
    `为什么当前无法确认部分数据`,
    `如何使用这些数据做研究`,
    `下一步还应核对哪些事实`,
  ];

  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.body.classList.add("research-agent-dialog-open");
    document.addEventListener("keydown", handleKeyDown);
    requestAnimationFrame(() => textareaRef.current?.focus());
    return () => {
      document.body.classList.remove("research-agent-dialog-open");
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    answerEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, status]);

  useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  if (!open) {
    return null;
  }

  function closeDialog() {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setStatus(null);
    onClose();
  }

  async function submitQuestion(event?: FormEvent) {
    event?.preventDefault();
    const normalized = question.trim();
    if (!normalized || busy) {
      return;
    }

    const controller = new AbortController();
    abortRef.current = controller;
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        content: normalized,
      },
    ]);
    setQuestion("");
    setBusy(true);
    setStatus("正在连接研究服务");

    let receivedResult = false;
    let streamError: string | null = null;
    try {
      await streamChat({
        message: normalized,
        sessionId,
        signal: controller.signal,
        onEvent: (event) => {
          if (event.event === "session") {
            const nextSessionId = event.data.session_id;
            if (typeof nextSessionId === "string") {
              setSessionId(nextSessionId);
            }
          } else if (event.event === "status") {
            const message = event.data.message;
            if (typeof message === "string") {
              setStatus(message);
            }
          } else if (event.event === "result") {
            const response = parseAgentResponse(event.data.response);
            if (response) {
              receivedResult = true;
              setMessages((current) => [
                ...current,
                {
                  id: crypto.randomUUID(),
                  role: "assistant",
                  content: response.answer,
                  response,
                },
              ]);
              setStatus(null);
            } else {
              streamError = "研究服务返回了无法识别的结果。";
            }
          } else if (event.event === "error") {
            const message = event.data.message;
            streamError =
              typeof message === "string" ? message : "研究请求处理失败。";
          }
        },
      });
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError")) {
        streamError =
          error instanceof Error ? error.message : "研究请求处理失败。";
      }
    } finally {
      if (!receivedResult && streamError) {
        setMessages((current) => [
          ...current,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            content: `当前无法完成请求：${streamError}`,
          },
        ]);
      }
      abortRef.current = null;
      setBusy(false);
      setStatus(null);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void submitQuestion();
    }
  }

  return (
    <div className="research-agent-backdrop" onMouseDown={closeDialog}>
      <section
        className="research-agent-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="research-agent-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          className="research-agent-close"
          type="button"
          aria-label="关闭 Agent"
          title="关闭"
          onClick={closeDialog}
        >
          <X aria-hidden="true" />
        </button>

        <header className="research-agent-heading">
          <span className="research-agent-logo" aria-hidden="true">
            <Bot />
          </span>
          <div>
            <div className="research-agent-title-line">
              <span>Fund Advisor</span>
              <b>审计模式</b>
            </div>
            <h2 id="research-agent-title">问问研究 Agent</h2>
          </div>
        </header>

        <div className="research-agent-note">
          <strong>受控研究模式</strong>
          <span>
            受控研究工作流只调用已注册工具；回答引用审计事实，不生成市场数值。
          </span>
        </div>

        <div className="research-agent-model-row">
          <label>
            <span>研究模型</span>
            <select aria-label="选择研究模型" value="ark" disabled>
              <option value="ark">Ark 结构化研究模型</option>
            </select>
          </label>
          <b>研究链路已连接</b>
        </div>
        <p className="research-agent-context">
          当前上下文：{fundCode} {fundName || "ETF"}。市场事实会由 Agent
          重新调用工具确认。
        </p>

        {messages.length > 0 && (
          <div className="research-agent-answer" aria-live="polite">
            {messages.map((message) => (
              <AgentDialogMessage key={message.id} message={message} />
            ))}
            {status && (
              <div className="research-agent-progress">
                <i />
                {status}
              </div>
            )}
            <div ref={answerEndRef} />
          </div>
        )}

        <form onSubmit={submitQuestion}>
          <label className="research-agent-field">
            <span>你想知道什么</span>
            <textarea
              ref={textareaRef}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`例如：分析 ${fundCode} 最近一个月的行情、回撤与数据限制`}
              rows={4}
              maxLength={4000}
              disabled={busy}
            />
          </label>

          <div className="research-agent-suggestions" aria-label="常用问题">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={busy}
                onClick={() => {
                  setQuestion(suggestion);
                  requestAnimationFrame(() => textareaRef.current?.focus());
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>

          <div className="research-agent-actions">
            <span>{busy ? status || "正在研究" : "会话仅保存在当前进程内"}</span>
            <button type="submit" disabled={busy || !question.trim()}>
              <Send aria-hidden="true" />
              {busy ? "研究中" : "开始回答"}
            </button>
          </div>
        </form>

        <p className="research-agent-risk">
          Agent 回答仅供个人研究参考，不构成投资建议，不预测未来收益。
        </p>
      </section>
    </div>
  );
}

function AgentDialogMessage({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return <div className="research-agent-question">{message.content}</div>;
  }

  return (
    <article className="research-agent-response">
      {message.response && (
        <span className={`status-tag status-${message.response.status}`}>
          {statusLabel(message.response.status)}
        </span>
      )}
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {message.content}
      </ReactMarkdown>
    </article>
  );
}

function parseAgentResponse(value: unknown): AgentResponse | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const candidate = value as Record<string, unknown>;
  if (
    typeof candidate.status !== "string" ||
    typeof candidate.answer !== "string"
  ) {
    return null;
  }
  return candidate as unknown as AgentResponse;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: "分析完成",
    partial_result: "部分结果",
    need_clarification: "需要确认",
    not_found: "未找到",
    unsupported: "暂不支持",
    cannot_confirm: "当前无法确认",
    stale_data: "数据过期",
    failed: "校验失败",
  };
  return labels[status] ?? status;
}
