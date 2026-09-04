import { ArrowRight, Bot, Plus, Send } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import ReactMarkdown from "react-markdown";
import { useLocation, useNavigate } from "react-router-dom";
import remarkGfm from "remark-gfm";

import { checkBackendHealth, streamChat } from "../api";
import type {
  AgentResponse,
  ChatMessage,
  Conversation,
  StreamEvent,
} from "../types";

const SUGGESTIONS = [
  "分析沪深300指数当前估值",
  "分析贵州茅台的估值与风险",
  "比较 000001 和 110022",
  "510300 现在能申购吗",
];

function createConversation(): Conversation {
  return {
    key: crypto.randomUUID(),
    sessionId: null,
    title: "新对话",
    messages: [],
  };
}

export default function ChatPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const firstConversation = useMemo(createConversation, []);
  const [conversations, setConversations] = useState<Conversation[]>([
    firstConversation,
  ]);
  const [activeKey, setActiveKey] = useState(firstConversation.key);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);
  const busyRef = useRef(false);
  const initialQuestionHandledRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const initialQuestion =
    typeof (location.state as { initialQuestion?: unknown } | null)
      ?.initialQuestion === "string"
      ? (location.state as { initialQuestion: string }).initialQuestion
      : null;

  const activeConversation =
    conversations.find((item) => item.key === activeKey) ?? conversations[0];

  useEffect(() => {
    const controller = new AbortController();
    checkBackendHealth(controller.signal)
      .then((connected) => {
        setApiConnected(connected);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setApiConnected(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) {
      return;
    }
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
  }, [input]);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation.messages, status]);

  useEffect(() => {
    if (
      !initialQuestion ||
      initialQuestionHandledRef.current ||
      busyRef.current
    ) {
      return;
    }
    initialQuestionHandledRef.current = true;
    navigate("/chat", { replace: true, state: null });
    void submitMessageText(initialQuestion);
  }, [initialQuestion, navigate]);

  function updateConversation(
    key: string,
    update: (conversation: Conversation) => Conversation,
  ) {
    setConversations((current) =>
      current.map((conversation) =>
        conversation.key === key ? update(conversation) : conversation,
      ),
    );
  }

  function startConversation() {
    if (busyRef.current) {
      return;
    }
    const conversation = createConversation();
    setConversations((current) => [conversation, ...current]);
    setActiveKey(conversation.key);
    setInput("");
    setStatus(null);
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  function selectConversation(key: string) {
    if (busyRef.current) {
      return;
    }
    setActiveKey(key);
  }

  async function submitMessage(event?: FormEvent) {
    event?.preventDefault();
    await submitMessageText(input);
  }

  async function submitMessageText(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || busyRef.current || !activeConversation) {
      return;
    }

    busyRef.current = true;
    const conversationKey = activeConversation.key;
    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: message,
    };
    updateConversation(conversationKey, (conversation) => ({
      ...conversation,
      title:
        conversation.messages.length === 0
          ? conversationTitle(message)
          : conversation.title,
      messages: [...conversation.messages, userMessage],
    }));
    setInput("");
    setBusy(true);
    setStatus("正在连接研究服务");

    let receivedResult = false;
    let streamError: string | null = null;
    try {
      await streamChat({
        message,
        sessionId: activeConversation.sessionId,
        onEvent: (streamEvent) => {
          const eventError = handleStreamEvent(
            streamEvent,
            conversationKey,
            updateConversation,
            setStatus,
          );
          if (streamEvent.event === "result") {
            receivedResult = true;
          }
          if (eventError) {
            streamError = eventError;
          }
        },
      });
    } catch (error) {
      streamError =
        error instanceof Error ? error.message : "研究请求处理失败。";
    } finally {
      if (!receivedResult && streamError) {
        appendErrorMessage(conversationKey, streamError, updateConversation);
      }
      busyRef.current = false;
      setBusy(false);
      setStatus(null);
      requestAnimationFrame(() => textareaRef.current?.focus());
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void submitMessage();
    }
  }

  return (
    <main className="agent-page">
      <header className="agent-page-header">
        <div>
          <p className="section-kicker">RESEARCH AGENT</p>
          <h1>受控研究助手</h1>
          <span className={apiConnected === false ? "offline" : ""}>
            <i />
            {apiConnected === null
              ? "正在连接 Agent API"
              : apiConnected
                ? "Agent API 已连接"
                : "Agent API 不可用"}
          </span>
        </div>
        <button
          className="agent-new-chat"
          type="button"
          onClick={startConversation}
          disabled={busy}
        >
          <Plus aria-hidden="true" />
          新建对话
        </button>
      </header>

      <nav className="agent-conversation-strip" aria-label="临时对话">
        <span>临时对话</span>
        <div>
          {conversations.map((conversation) => (
            <button
              className={
                conversation.key === activeKey ? "active" : ""
              }
              type="button"
              key={conversation.key}
              onClick={() => selectConversation(conversation.key)}
              disabled={busy && conversation.key !== activeKey}
            >
              <strong>{conversation.title}</strong>
              <small>
                {conversation.messages.length > 0
                  ? `${conversation.messages.length} 条消息`
                  : "尚未开始"}
              </small>
            </button>
          ))}
        </div>
      </nav>

      <section className="chat-stage">
        <div className="message-stream" aria-live="polite">
          {activeConversation.messages.length === 0 ? (
            <Welcome
              disabled={busy}
              onSuggestion={(suggestion) => {
                setInput(suggestion);
                requestAnimationFrame(() =>
                  textareaRef.current?.focus(),
                );
              }}
            />
          ) : (
            activeConversation.messages.map((message) => (
              <Message key={message.id} message={message} />
            ))
          )}

          {status && (
            <div className="progress-row">
              <div className="assistant-avatar" aria-hidden="true">
                F
              </div>
              <div className="progress-copy">
                <span className="thinking-dot" />
                {status}
              </div>
            </div>
          )}
          <div ref={messageEndRef} />
        </div>

        <div className="composer-wrap">
          <form className="composer" onSubmit={submitMessage}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入基金、指数或股票研究问题"
              aria-label="研究问题"
              maxLength={4000}
              rows={1}
              disabled={busy}
            />
            <div className="composer-actions">
              <button
                className="send-button"
                type="submit"
                aria-label="发送"
                disabled={busy || !input.trim()}
              >
                <Send aria-hidden="true" />
              </button>
            </div>
          </form>
          <p className="disclaimer">
            会话只保存在当前进程内。内容仅供个人研究参考，不构成投资建议。
          </p>
        </div>
      </section>
    </main>
  );
}

interface WelcomeProps {
  disabled: boolean;
  onSuggestion: (suggestion: string) => void;
}

function Welcome({ disabled, onSuggestion }: WelcomeProps) {
  return (
    <div className="welcome">
      <div className="welcome-mark" aria-hidden="true">
        <Bot />
      </div>
      <p className="eyebrow">AUDITED RESEARCH AGENT</p>
      <h1>今天想研究什么？</h1>
      <p className="welcome-copy">
        查询基金、ETF、指数与 A 股的可信数据，并把事实、公开观点和限制分开说明。
      </p>
      <div className="suggestion-grid">
        {SUGGESTIONS.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            onClick={() => onSuggestion(suggestion)}
            disabled={disabled}
          >
            <span>{suggestion}</span>
            <ArrowRight aria-hidden="true" />
          </button>
        ))}
      </div>
      <div className="boundary-row">
        <span>不预测收益</span>
        <span>不执行交易</span>
        <span>不生成市场数值</span>
      </div>
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <article className="message user-message">
        <div className="user-bubble">{message.content}</div>
      </article>
    );
  }

  return (
    <article className="message assistant-message">
      <div className="assistant-avatar" aria-hidden="true">
        F
      </div>
      <div className="assistant-content">
        {message.response && (
          <span className={`status-tag status-${message.response.status}`}>
            {statusLabel(message.response.status)}
          </span>
        )}
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ node: _node, ...props }) => (
              <a {...props} target="_blank" rel="noreferrer" />
            ),
          }}
        >
          {message.content}
        </ReactMarkdown>
      </div>
    </article>
  );
}

type ConversationUpdater = (
  key: string,
  update: (conversation: Conversation) => Conversation,
) => void;

function handleStreamEvent(
  event: StreamEvent,
  conversationKey: string,
  updateConversation: ConversationUpdater,
  setStatus: (status: string | null) => void,
): string | null {
  if (event.event === "session") {
    const sessionId = event.data.session_id;
    if (typeof sessionId === "string") {
      updateConversation(conversationKey, (conversation) => ({
        ...conversation,
        sessionId,
      }));
    }
    return null;
  }

  if (event.event === "status") {
    const message = event.data.message;
    if (typeof message === "string") {
      setStatus(message);
    }
    return null;
  }

  if (event.event === "result") {
    const response = parseAgentResponse(event.data.response);
    if (response) {
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.answer,
        response,
      };
      updateConversation(conversationKey, (conversation) => ({
        ...conversation,
        messages: [...conversation.messages, assistantMessage],
      }));
      setStatus(null);
      return null;
    }
    return "研究服务返回了无法识别的结果。";
  }

  if (event.event === "error") {
    const message = event.data.message;
    return typeof message === "string" ? message : "研究请求处理失败。";
  }
  return null;
}

function appendErrorMessage(
  conversationKey: string,
  message: string,
  updateConversation: ConversationUpdater,
) {
  updateConversation(conversationKey, (conversation) => ({
    ...conversation,
    messages: [
      ...conversation.messages,
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: `当前无法完成请求：${message}`,
      },
    ],
  }));
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

function conversationTitle(message: string): string {
  const normalized = message.replace(/\s+/g, " ").trim();
  return normalized.length > 24
    ? `${normalized.slice(0, 24)}…`
    : normalized;
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
