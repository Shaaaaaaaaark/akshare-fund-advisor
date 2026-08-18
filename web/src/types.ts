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

export type DataStatus =
  | "available"
  | "partial"
  | "stale"
  | "unavailable"
  | "not_implemented";

export interface ToolError {
  code: string;
  message: string;
  retryable?: boolean;
  details?: Record<string, unknown>;
}

export interface DatasetMeta {
  as_of: string;
  queried_at: string;
  status: DataStatus;
  source_tools: string[];
  audit_refs: string[];
  warnings?: Array<Record<string, unknown> | string>;
  error?: ToolError;
}

export interface MetricSummary {
  current: number | null;
  percentile: number | null;
  level: string;
}

export interface IndexRow {
  index: string;
  meta: DatasetMeta;
  pe_ttm: MetricSummary | null;
  pb: MetricSummary | null;
  latest_point: number | null;
}

export interface IndicesResponse {
  status: DataStatus;
  rows: IndexRow[];
}

export interface ValuePoint {
  value: number;
  date: string;
}

export interface WindowStatistic {
  actual_start_date: string;
  latest_date: string;
  observations: number;
  current: number;
  percentile: number;
  level: string;
  median: number;
  mean: number;
  p20: number;
  p80: number;
  minimum: number;
  maximum: number;
}

export interface ChartMetric {
  metric: string;
  unit: string;
  current: number;
  percentile: number;
  level: string;
  mean: number;
  median: number;
  standard_deviation: number;
  mean_minus_1_stddev: number;
  mean_plus_1_stddev: number;
  z_score: number;
  current_vs_mean_pct: number;
  quantiles: {
    p10: number;
    p20: number;
    p50: number;
    p80: number;
    p90: number;
  };
  minimum: ValuePoint;
  maximum: ValuePoint;
  latest_date: string;
  latest_age_days: number;
  actual_start_date: string;
  source_observations: number;
  displayed_points: number;
  chart_series: Array<[string, number]>;
  reference_lines: Record<string, number>;
  window_statistics: Record<string, WindowStatistic>;
  data_quality: {
    source_rows: number;
    invalid_rows_dropped: number;
    duplicate_rows: number;
    window_rows: number;
    interpolation: string;
    forward_fill: string;
  };
}

export interface IndexValuationData {
  ok: boolean;
  action: string;
  index: {
    name: string;
    akshare_symbol: string;
    index_code: string;
    qualified_code: string;
  };
  actual_source: {
    provider: string;
    interfaces: string[];
    upstream: string;
    available_metrics: string[];
    available_series: string[];
  };
  lookback: {
    requested_years: number;
    actual_start_date: string;
    latest_date: string;
    statistics_frequency: string;
    chart_max_points: number;
    sampling: string;
  };
  summary: {
    pe_ttm: MetricSummary | null;
    pb: MetricSummary | null;
    combined_percentile: null;
    combined_percentile_policy: string;
    interpretation: string;
  };
  charts: {
    pe_ttm: ChartMetric | null;
    pb: ChartMetric | null;
    index_points: ChartMetric | null;
  };
  limitations: string[];
  data_integrity: {
    ai_generated_market_data: boolean;
    interpolation: string;
    forward_fill: string;
    raw_series_origin: string;
    derived_values: string;
  };
}

export interface ToolEnvelope<T> {
  schema_version: string;
  request_id: string;
  tool: string;
  ok: boolean;
  data: T | null;
  sources: Array<Record<string, unknown>>;
  data_audit: Array<Record<string, unknown>>;
  data_warnings: Array<Record<string, unknown> | string>;
  data_policy: Record<string, unknown>;
  queried_at: string;
  error: ToolError | null;
}

export interface IndexDetailResponse {
  index: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<IndexValuationData>;
}

export interface FundIdentity {
  code: string;
  name: string;
  type: string;
  pinyin_abbr?: string;
}

export interface FundSearchData {
  ok: boolean;
  action: string;
  query: string;
  count: number;
  has_more: boolean;
  results: FundIdentity[];
  guidance?: string | null;
}

export interface FundSearchResponse {
  query: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<FundSearchData>;
}

export interface ETFDashboardChart {
  metric: string;
  unit: string;
  chart_type: "line" | "bar";
  actual_start_date: string | null;
  latest_date: string | null;
  source_observations: number;
  displayed_points: number;
  chart_series: Array<[string, number]>;
}

export interface ETFRangeSummary {
  key: string;
  label: string;
  observations: number;
  actual_start_date: string;
  latest_date: string;
  price_return_pct: number | null;
  turnover_yi_cny: number | null;
  volume_yi_units: number | null;
  maximum_drawdown_pct: number | null;
}

export interface ETFRecentRow {
  date: string;
  close: number | null;
  daily_change_pct: number | null;
  turnover_yi_cny: number | null;
  volume_yi_units: number | null;
  drawdown_pct: number | null;
}

export interface ETFMarketSnapshot {
  date: string | null;
  updated_at: string | null;
  latest_price: number | null;
  iopv: number | null;
  premium_rate_pct: number | null;
  premium_level: string | null;
  turnover_cny: number | null;
  turnover_rate_pct: number | null;
  bid_1: number | null;
  ask_1: number | null;
  usable_for_current_decision: boolean;
}

export interface ETFDashboardData {
  ok: boolean;
  action: string;
  identity: FundIdentity;
  lookback: {
    requested_years: number;
    actual_start_date: string;
    latest_date: string;
    latest_age_days: number;
    source_observations: number;
    chart_max_points: number;
    sampling: string;
  };
  metric_basis: string;
  basis_note: string;
  summary: {
    latest_date: string;
    latest_close: number | null;
    latest_turnover_yi_cny: number | null;
    latest_volume_yi_units: number | null;
    latest_change_pct: number | null;
    current_drawdown_pct: number | null;
  };
  market_snapshot: ETFMarketSnapshot | null;
  range_summaries: ETFRangeSummary[];
  charts: {
    price: ETFDashboardChart;
    turnover: ETFDashboardChart;
    volume: ETFDashboardChart;
    daily_change: ETFDashboardChart;
    drawdown: ETFDashboardChart;
  };
  recent_rows: ETFRecentRow[];
  data_quality: Record<string, unknown>;
  missing_or_not_reliably_available: string[];
  derived_formulas: Record<string, string>;
  data_integrity: {
    ai_generated_market_data: boolean;
    source_interface: string;
    interpolation: string;
    forward_fill: string;
    missing_value_policy: string;
  };
}

export interface ETFDetailResponse {
  fund: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<ETFDashboardData>;
}
