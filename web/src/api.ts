import type {
  CreateWatchlistItem,
  ETFDetailResponse,
  FundProductResponse,
  FundSearchResponse,
  IndexDetailResponse,
  IndicesResponse,
  OverviewResponse,
  PanelInteractionSummary,
  StockDetailResponse,
  StreamEvent,
  StreamEventName,
  SubmitPanelInteraction,
  WatchlistItem,
} from "./types";

const EVENT_NAMES = new Set<StreamEventName>([
  "session",
  "status",
  "result",
  "error",
  "done",
]);
const DASHBOARD_TIMEOUT_MS = 100_000;
const DASHBOARD_AGGREGATE_TIMEOUT_MS = 200_000;
const SEARCH_TIMEOUT_MS = 20_000;
const etfDetailRequests = new Map<string, Promise<ETFDetailResponse>>();
const panelInteractionRequests = new Map<
  string,
  Promise<PanelInteractionSummary>
>();

interface StreamChatOptions {
  message: string;
  sessionId: string | null;
  signal?: AbortSignal;
  onEvent: (event: StreamEvent) => void;
}

export type OverviewModule = "index" | "etf" | "fund" | "stock";

export async function fetchOverview(
  signal?: AbortSignal,
): Promise<OverviewResponse> {
  const response = await fetchWithTimeout(
    "/api/dashboard/overview",
    { signal },
    DASHBOARD_AGGREGATE_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as OverviewResponse;
}

export async function fetchOverviewModule<K extends OverviewModule>(
  module: K,
  signal?: AbortSignal,
): Promise<OverviewResponse[K]> {
  const response = await fetchWithTimeout(
    `/api/dashboard/overview/${module}`,
    { signal },
    DASHBOARD_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as OverviewResponse[K];
}

export async function fetchIndices(
  signal?: AbortSignal,
): Promise<IndicesResponse> {
  const response = await fetchWithTimeout(
    "/api/dashboard/indices",
    { signal },
    DASHBOARD_TIMEOUT_MS,
  );
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
  const response = await fetchWithTimeout(
    `/api/dashboard/indices/${encodeURIComponent(index)}?${query}`,
    { signal },
    DASHBOARD_TIMEOUT_MS,
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
  const response = await fetchWithTimeout(
    `/api/dashboard/funds/search?${params}`,
    { signal },
    SEARCH_TIMEOUT_MS,
  );
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
  const key = `${fund}?${params}`;
  let request = etfDetailRequests.get(key);
  if (!request) {
    request = requestETFDetail(fund, params);
    etfDetailRequests.set(key, request);
    void request.then(
      () => etfDetailRequests.delete(key),
      () => etfDetailRequests.delete(key),
    );
  }
  return waitForSharedRequest(request, signal);
}

async function requestETFDetail(
  fund: string,
  params: URLSearchParams,
): Promise<ETFDetailResponse> {
  const response = await fetchWithTimeout(
    `/api/dashboard/funds/${encodeURIComponent(fund)}?${params}`,
    {},
    DASHBOARD_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as ETFDetailResponse;
}

export async function fetchFundProduct(
  fund: string,
  years: 1 | 3 | 5,
  signal?: AbortSignal,
): Promise<FundProductResponse> {
  const params = new URLSearchParams({ years: String(years) });
  const response = await fetchWithTimeout(
    `/api/dashboard/funds/${encodeURIComponent(fund)}/product?${params}`,
    { signal },
    DASHBOARD_AGGREGATE_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as FundProductResponse;
}

export async function fetchStockDetail(
  stock: string,
  years: 1 | 3 | 5 | 10,
  signal?: AbortSignal,
): Promise<StockDetailResponse> {
  const params = new URLSearchParams({
    years: String(years),
    max_points: "600",
  });
  const response = await fetchWithTimeout(
    `/api/dashboard/stocks/${encodeURIComponent(stock)}?${params}`,
    { signal },
    DASHBOARD_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as StockDetailResponse;
}

export async function fetchWatchlist(
  signal?: AbortSignal,
): Promise<WatchlistItem[]> {
  const response = await fetchWithTimeout(
    "/api/watchlist",
    { signal },
    SEARCH_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as WatchlistItem[];
}

export async function createWatchlistItem(
  item: CreateWatchlistItem,
): Promise<WatchlistItem> {
  const response = await fetchWithTimeout(
    "/api/watchlist",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    },
    SEARCH_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as WatchlistItem;
}

export async function deleteWatchlistItem(id: string): Promise<void> {
  const response = await fetchWithTimeout(
    `/api/watchlist/${encodeURIComponent(id)}`,
    { method: "DELETE" },
    SEARCH_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
}

export async function fetchPanelInteractions(
  clientId: string,
  fund: string,
  signal?: AbortSignal,
): Promise<PanelInteractionSummary> {
  const params = new URLSearchParams({
    client_id: clientId,
    fund,
  });
  const key = params.toString();
  let request = panelInteractionRequests.get(key);
  if (!request) {
    request = requestPanelInteractions(params);
    panelInteractionRequests.set(key, request);
    void request.then(
      () => panelInteractionRequests.delete(key),
      () => panelInteractionRequests.delete(key),
    );
  }
  return waitForSharedRequest(request, signal);
}

async function requestPanelInteractions(
  params: URLSearchParams,
): Promise<PanelInteractionSummary> {
  const response = await fetchWithTimeout(
    `/api/panel/interactions?${params}`,
    {},
    SEARCH_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as PanelInteractionSummary;
}

export async function submitPanelInteraction(
  interaction: SubmitPanelInteraction,
): Promise<PanelInteractionSummary> {
  const response = await fetchWithTimeout(
    "/api/panel/interactions",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(interaction),
    },
    SEARCH_TIMEOUT_MS,
  );
  if (!response.ok) {
    throw new Error(await responseError(response));
  }
  return (await response.json()) as PanelInteractionSummary;
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

function waitForSharedRequest<T>(
  request: Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  if (!signal) {
    return request;
  }
  if (signal.aborted) {
    return Promise.reject(new DOMException("请求已取消", "AbortError"));
  }
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException("请求已取消", "AbortError"));
    signal.addEventListener("abort", abort, { once: true });
    void request.then(
      (value) => {
        signal.removeEventListener("abort", abort);
        resolve(value);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", abort);
        reject(error);
      },
    );
  });
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const parentSignal = init.signal;
  const abortFromParent = () => controller.abort();
  if (parentSignal) {
    if (parentSignal.aborted) {
      clearTimeout(timeout);
      throw new DOMException("请求已取消", "AbortError");
    }
    parentSignal.addEventListener("abort", abortFromParent, { once: true });
  }

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) {
      throw new Error(
        `数据请求超过 ${Math.round(timeoutMs / 1000)} 秒，请稍后重试或切换标的。`,
      );
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    parentSignal?.removeEventListener("abort", abortFromParent);
  }
}
