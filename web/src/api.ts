import type {
  ETFDetailResponse,
  FundSearchResponse,
  IndexDetailResponse,
  IndicesResponse,
  StreamEvent,
  StreamEventName,
} from "./types";

const EVENT_NAMES = new Set<StreamEventName>([
  "session",
  "status",
  "result",
  "error",
  "done",
]);

interface StreamChatOptions {
  message: string;
  sessionId: string | null;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

export async function fetchIndices(
  signal?: AbortSignal,
): Promise<IndicesResponse> {
  const response = await fetch("/api/dashboard/indices", { signal });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as IndicesResponse;
}

export async function fetchIndexDetail(
  index: string,
  signal?: AbortSignal,
): Promise<IndexDetailResponse> {
  const query = new URLSearchParams({
    years: "10",
    max_points: "600",
  });
  const response = await fetch(
    `/api/dashboard/indices/${encodeURIComponent(index)}?${query}`,
    { signal },
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as IndexDetailResponse;
}

export async function searchFunds(
  query: string,
  signal?: AbortSignal,
): Promise<FundSearchResponse> {
  const params = new URLSearchParams({ query, limit: "20" });
  const response = await fetch(`/api/dashboard/funds/search?${params}`, {
    signal,
  });
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as FundSearchResponse;
}

export async function fetchETFDetail(
  fund: string,
  signal?: AbortSignal,
): Promise<ETFDetailResponse> {
  const params = new URLSearchParams({ years: "3", max_points: "600" });
  const response = await fetch(
    `/api/dashboard/funds/${encodeURIComponent(fund)}?${params}`,
    { signal },
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as ETFDetailResponse;
}

export async function streamChat({
  message,
  sessionId,
  signal,
  onEvent,
}: StreamChatOptions): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      Accept: "text/event-stream",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      session_id: sessionId,
    }),
    signal,
  });

  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  if (!response.body) {
    throw new Error("浏览器没有收到流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    buffer = buffer.replace(/\r\n/g, "\n");

    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseFrame(frame);
      if (event) {
        onEvent(event);
      }
      boundary = buffer.indexOf("\n\n");
    }

    if (done) {
      const event = parseFrame(buffer);
      if (event) {
        onEvent(event);
      }
      return;
    }
  }
}

function parseFrame(frame: string): StreamEvent | null {
  if (!frame.trim()) {
    return null;
  }

  let eventName: StreamEventName = "status";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      const candidate = line.slice(6).trim() as StreamEventName;
      if (EVENT_NAMES.has(candidate)) {
        eventName = candidate;
      }
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }
  const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
  return { event: eventName, data };
}

async function responseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      detail?: string | Array<{ msg?: string }>;
    };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
      return payload.detail[0].msg;
    }
  } catch {
    // Fall back to the HTTP status when the response is not JSON.
  }
  return `请求失败（HTTP ${response.status}）`;
}
