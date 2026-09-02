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

export type WatchlistEntityType = "index" | "etf" | "fund" | "stock";

export interface WatchlistItem {
  id: string;
  entity_type: WatchlistEntityType;
  entity_code: string;
  display_name: string;
  created_at: string;
}

export interface CreateWatchlistItem {
  entity_type: WatchlistEntityType;
  entity_code: string;
  display_name: string;
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

export interface QDIIBoardFund {
  code: string;
  name: string;
  fund_type: string;
  theme: string;
  subscription_status: string;
  status_tier: "limited_large" | "suspended";
  effective_daily_limit_cny: number | null;
  amount_disclosed: boolean;
  source_daily_limit_cny: number | null;
  no_effective_limit_placeholder: boolean;
  minimum_purchase_cny: number | null;
  purchase_fee_pct: number | null;
  next_open_date: string | null;
  source_report_date: string | null;
}

export interface QDIIBoardCategory {
  theme: string;
  limited_large_count: number;
  suspended_count: number;
  limited_large: QDIIBoardFund[];
  suspended: QDIIBoardFund[];
}

export interface QDIIBoardData {
  ok: boolean;
  action: string;
  scope: string;
  latest_source_report_date: string | null;
  source_report_date_span: { earliest: string; latest: string } | null;
  summary: {
    limited_large_count: number;
    limited_large_amount_disclosed_count: number;
    suspended_count: number;
    category_count: number;
  };
  categories: QDIIBoardCategory[];
  notes: string[];
}

export interface QDIIBoardResponse {
  board: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<QDIIBoardData>;
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

export interface StockValuationData {
  ok: boolean;
  action: string;
  stock: {
    code: string;
    name: string;
    qualified_code: string;
  };
  actual_source: {
    provider: string;
    interfaces: string[];
    available_series: string[];
    price_adjustment: string;
  };
  lookback: {
    requested_years: number;
    actual_start_date: string | null;
    latest_date: string | null;
    statistics_frequency: string;
    chart_max_points: number;
  };
  summary: {
    pe_ttm: MetricSummary;
    pb: MetricSummary;
    stock_price: {
      current: number | null;
      unit: string;
      adjustment: string;
    };
    combined_percentile: null;
    combined_percentile_policy: string;
  };
  charts: {
    pe_ttm: ChartMetric | null;
    pb: ChartMetric | null;
    stock_price: ChartMetric | null;
  };
  data_quality: {
    pe_ttm_available: boolean;
    pb_available: boolean;
    price_available: boolean;
    available_series: string[];
    missing_series: string[];
    latest_date: string | null;
    warnings: Array<Record<string, unknown> | string>;
  };
  limitations: string[];
  data_integrity: {
    ai_generated_market_data: boolean;
    interpolation: string;
    forward_fill: string;
    raw_series_origin: string;
  };
}

export interface StockDetailResponse {
  stock: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<StockValuationData>;
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

export interface FundAnalysisData {
  ok: boolean;
  action: string;
  fund: FundIdentity;
  lookback_years: number;
  metric_basis?: string | null;
  basis_note?: string | null;
  fund_profile?: {
    full_name?: string | null;
    investment_type?: string | null;
    manager?: string | null;
    inception_date?: string | null;
    share_scale?: string | null;
    management_fee?: string | null;
    custodian_fee?: string | null;
    benchmark?: string | null;
    fund_company?: string | null;
  } | null;
  metrics?: {
    latest_date?: string | null;
    latest_value?: number | null;
    observations?: number | null;
    actual_start_date?: string | null;
    returns_pct?: Record<string, number | null>;
    current_drawdown_pct?: number | null;
    max_drawdown_pct?: number | null;
    annualized_volatility_pct?: number | null;
    positive_day_ratio_pct?: number | null;
    history_position_percentile?: number | null;
    history_position_level?: string | null;
    trend?: string | null;
    holding_experience?: {
      annualized_return_pct?: number | null;
      downside_volatility_pct?: number | null;
      calmar_ratio?: number | null;
      longest_underwater_days?: number | null;
    } | null;
  } | null;
  portfolio_snapshot?: {
    asset_allocation?: {
      report_date?: string | null;
      items?: Array<{
        asset_type: string;
        weight_pct: number | null;
      }>;
      note?: string | null;
    } | null;
  } | null;
  metric_coverage?: {
    available?: string[];
    missing_or_not_reliably_available?: string[];
    rule?: string;
  } | null;
}

export interface FundProfileData {
  ok: boolean;
  action: string;
  fund: FundIdentity;
  basic_info: Record<string, string | number | null>;
  fee_rules: Array<{
    fee_type: string | null;
    condition: string | null;
    fee: number | null;
  }>;
  asset_allocation: Array<{
    asset_type: string | null;
    weight_pct: number | null;
  }>;
  notes?: string | null;
}

export interface FundRatingData {
  ok: boolean;
  action: string;
  fund: FundIdentity;
  fund_type?: string | null;
  fund_company?: string | null;
  ratings: {
    shanghai_securities?: number | null;
    merchants_securities?: number | null;
    jian_jin_xin?: number | null;
    morningstar?: number | null;
    five_star_count?: number | null;
  };
  notes?: string | null;
}

export interface FundStatusData {
  ok: boolean;
  action: string;
  fund: FundIdentity;
  availability: {
    confirmed: boolean;
    mode?: string | null;
    source_report_date?: string | null;
    latest_nav_or_income?: number | null;
    off_exchange?: {
      subscription_status?: string | null;
      redemption_status?: string | null;
      can_submit_subscription?: boolean | null;
      can_submit_redemption?: boolean | null;
      next_open_date?: string | null;
      minimum_purchase_cny?: number | null;
      daily_limit_cny?: number | null;
      purchase_fee_pct?: number | null;
      note?: string | null;
    } | null;
    exchange?: {
      source_subscription_status?: string | null;
      source_redemption_status?: string | null;
      market_session?: string | null;
      standard_market_open_now?: boolean | null;
      can_submit_standard_session_order?: boolean | null;
      can_buy_now?: boolean | null;
      can_sell_now?: boolean | null;
      note?: string | null;
    } | null;
    message?: string | null;
  };
}

export interface FundProductSection<T> {
  meta: DatasetMeta;
  envelope?: ToolEnvelope<T>;
}

export interface FundProductResponse {
  fund: string;
  status: DataStatus;
  sections: {
    analysis: FundProductSection<FundAnalysisData>;
    profile: FundProductSection<FundProfileData>;
    rating: FundProductSection<FundRatingData>;
    trading_status: FundProductSection<FundStatusData>;
  };
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
  turnover_percentile_pct?: number | null;
  volume_yi_units: number | null;
  drawdown_pct: number | null;
  total_shares?: number | null;
  total_shares_yi_units?: number | null;
  total_shares_change?: number | null;
  total_shares_change_yi_units?: number | null;
  financing_balance_cny?: number | null;
  financing_balance_yi_cny?: number | null;
  financing_balance_change_cny?: number | null;
  financing_balance_change_yi_cny?: number | null;
  component_financing_balance_cny?: number | null;
  component_financing_balance_yi_cny?: number | null;
  component_financing_balance_change_cny?: number | null;
  component_financing_balance_change_yi_cny?: number | null;
  component_financing_reported_count?: number | null;
  component_financing_constituent_count?: number | null;
  component_financing_coverage_pct?: number | null;
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

export interface ETFShareSupplementRow {
  date: string;
  total_shares: number;
  total_shares_yi_units: number;
  previous_date: string | null;
  total_shares_change: number | null;
  total_shares_change_yi_units: number | null;
}

export interface ETFFinancingSupplementRow {
  date: string;
  financing_balance_cny: number;
  financing_balance_yi_cny: number;
  previous_date: string | null;
  financing_balance_change_cny: number | null;
  financing_balance_change_yi_cny: number | null;
}

export interface ETFConstituentFinancingSupplementRow
  extends ETFFinancingSupplementRow {
  constituent_count: number;
  reported_component_count: number;
  coverage_pct: number;
}

export interface ETFSupplementSeries<T> {
  status: "available" | "partial" | "unavailable";
  source_observations: number;
  actual_start_date: string | null;
  latest_date: string | null;
  unit: string;
  scaled_unit: string;
  latest: T | null;
  rows: T[];
  chart_series: Array<[string, number]>;
  derived_formulas: Record<string, string>;
}

export interface ETFConstituentFinancingSeries
  extends ETFSupplementSeries<ETFConstituentFinancingSupplementRow> {
  tracking_index_name: string | null;
  tracking_index_code: string | null;
  constituent_as_of: string | null;
  constituent_count: number;
  scope_note: string;
}

export interface ETFSupplementalData {
  fund_code: string;
  requested_trading_dates: string[];
  share: ETFSupplementSeries<ETFShareSupplementRow>;
  financing: ETFSupplementSeries<ETFFinancingSupplementRow>;
  component_financing: ETFConstituentFinancingSeries;
  range_summaries: Array<{
    key: string;
    actual_start_date: string;
    latest_date: string;
    share_change_yi_units: number | null;
    financing_net_change_yi_cny: number | null;
    component_financing_net_change_yi_cny: number | null;
  }>;
  unavailable_metrics: string[];
  data_integrity: {
    ai_generated_market_data: boolean;
    interpolation: string;
    forward_fill: string;
    coverage: string;
  };
}

export interface ETFDashboardData {
  ok: boolean;
  action: string;
  identity: FundIdentity;
  tracking_index?: {
    name: string;
    index_code: string;
    match_basis: string;
  } | null;
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
  source_validation?: {
    status: "disabled" | "passed" | "warning" | "unavailable";
    scope: string;
    policy: string;
    primary_source?: string;
    checks?: Array<{
      status: "disabled" | "passed" | "warning" | "not_comparable" | "unavailable";
      scope: string;
      policy: string;
    }>;
    sources: Array<{
      source: string;
      interface?: string;
      status: "passed" | "warning" | "not_comparable" | "unavailable";
      error_code?: string;
      warning_codes?: Array<string | null>;
      summary?: Record<string, unknown>;
    }>;
  };
  supplemental?: ETFSupplementalData;
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
    source_validation_policy?: string;
    supplemental_source_interfaces?: string[];
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

export type PanelInteractionKind =
  | "hot_poll"
  | "feedback"
  | "feature_vote";

export interface PanelTopicSummary {
  counts: Record<string, number>;
  selected_option: string | null;
}

export interface PanelInteractionSummary {
  fund: string;
  hot_polls: Record<string, PanelTopicSummary>;
  feedback: PanelTopicSummary;
  feature_vote: PanelTopicSummary;
}

export interface SubmitPanelInteraction {
  kind: PanelInteractionKind;
  topic_key: string;
  option_key: string;
  client_id: string;
  fund: string;
}

export interface OverviewCapability {
  status: DataStatus;
  message: string;
}

export interface FundOverviewResponse {
  fund: string;
  meta: DatasetMeta;
  envelope?: ToolEnvelope<FundAnalysisData>;
}

export interface OverviewResponse {
  status: DataStatus;
  index: IndexDetailResponse;
  etf: ETFDetailResponse;
  fund: FundOverviewResponse;
  stock: StockDetailResponse;
  fund_screening: OverviewCapability;
  stock_screening: OverviewCapability;
}
