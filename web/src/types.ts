export type StreamEventName =
  | "session"
  | "status"
  | "result"
  | "error"
  | "done";

export interface StreamEvent {
  event: StreamEventName;
  data: Record<string, unknown>;
}

export interface AgentError {
  code: string;
  message: string;
}

export interface AgentResponse {
  status: string;
  answer: string;
  limitations?: string[];
  warnings?: string[];
  errors?: AgentError[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AgentResponse;
}

export interface Conversation {
  key: string;
  sessionId: string | null;
  title: string;
  messages: ChatMessage[];
}
