import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Bot,
  CalendarDays,
  Database,
  RefreshCw,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchFundProduct, searchFunds } from "../api";
import { displayNumber, displayPercent, warningText } from "../components/display";
import StatusBadge from "../components/StatusBadge";
import type {
  DataStatus,
  DatasetMeta,
  FundAnalysisData,
  FundIdentity,
  FundProductResponse,
  FundProductSection,
  FundProfileData,
  FundRatingData,
  FundStatusData,
} from "../types";

const DEFAULT_FUND = "000001";
const BASIC_FIELDS = [
  "基金全称",
  "基金类型",
  "基金公司",
  "基金经理",
  "成立时间",
  "最新规模",
  "托管银行",
  "业绩比较基准",
] as const;
const RATING_LABELS: Record<string, string> = {
  shanghai_securities: "上海证券",
  merchants_securities: "招商证券",
  jian_jin_xin: "济安金信",
  morningstar: "晨星评级",
  five_star_count: "五星评级家数",
};
// 标签只能跟随后端 metric_basis，不得由前端改写口径。
const METRIC_BASIS_LABELS: Record<string, string> = {
  accumulated_nav: "累计净值",
  unit_nav: "单位净值",
  exchange_qfq_daily: "场内收盘价（前复权）",
  exchange_unadjusted_daily_sina: "场内收盘价（未复权）",
};
const NEUTRAL_LATEST_VALUE_LABEL = "最新指标值";

type ProductYears = 1 | 3 | 5;

export default function FundProductPage() {
  const { fund = DEFAULT_FUND } = useParams();
  const navigate = useNavigate();
  const [years, setYears] = useState<ProductYears>(3);
  const [payload, setPayload] = useState<FundProductResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<FundIdentity[]>([]);

  const load = useCallback(
    (signal: AbortSignal) => {
      setLoading(true);
      setError(null);
      setPayload(null);
      void fetchFundProduct(fund, years, signal)
        .then(setPayload)
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === "AbortError") {
            return;
          }
          setError(
            reason instanceof Error ? reason.message : "基金产品数据请求失败",
          );
        })
        .finally(() => {
          if (!signal.aborted) {
            setLoading(false);
          }
        });
    },
    [fund, years],
  );

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  const identity = useMemo(() => productIdentity(payload), [payload]);
  const analysis = sectionData(payload?.sections.analysis);
  const profile = sectionData(payload?.sections.profile);
  const rating = sectionData(payload?.sections.rating);
  const trading = sectionData(payload?.sections.trading_status);
  const warnings = useMemo(
    () =>
      payload
        ? Object.values(payload.sections).flatMap(
            (section) => section.meta.warnings ?? [],
          )
        : [],
    [payload],
  );

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    const normalized = query.trim();
    if (!normalized) {
      return;
    }
    setSearching(true);
    setSearchError(null);
    setSearchResults([]);
    try {
      const response = await searchFunds(normalized);
      if (!response.envelope?.ok || !response.envelope.data) {
        throw new Error(
          response.envelope?.error?.message ?? "当前无法确认基金搜索结果",
        );
      }
      setSearchResults(response.envelope.data.results);
    } catch (reason) {
      setSearchError(
        reason instanceof Error ? reason.message : "基金搜索请求失败",
      );
    } finally {
      setSearching(false);
    }
  }

  function selectSearchResult(item: FundIdentity) {
    setSearchResults([]);
    setQuery("");
    if (isExchangeTradedETF(item)) {
      navigate(`/funds/${encodeURIComponent(item.code)}`);
      return;
    }
    navigate(`/funds/${encodeURIComponent(item.code)}/product`);
  }

  return (
    <main className="workbench-page fund-product-page">
      <div className="fund-product-breadcrumb">
        <Link to="/">
          <ArrowLeft aria-hidden="true" />
          数据面板
        </Link>
        <div>
          <Link to="/funds/510300">
            <BarChart3 aria-hidden="true" />
            ETF 终端
          </Link>
          <Link to="/chat">
            <Bot aria-hidden="true" />
            Agent
          </Link>
        </div>
      </div>

      <header className="fund-product-heading">
        <div>
          <p className="section-kicker">FUND PRODUCT PROFILE</p>
          <div className="fund-product-title">
            <h1>{identity?.name ?? `${fund} 基金产品档案`}</h1>
            <span>{identity?.code ?? fund}</span>
            {payload && <StatusBadge status={payload.status} />}
          </div>
          <p>
            {identity?.type ?? "基金类型待确认"}
            {analysis?.basis_note ? ` · ${analysis.basis_note}` : ""}
          </p>
        </div>
        <button
          type="button"
          className="icon-command"
          aria-label="刷新基金产品数据"
          title="刷新基金产品数据"
          disabled={loading}
          onClick={() => setRefreshKey((current) => current + 1)}
        >
          <RefreshCw aria-hidden="true" className={loading ? "spin" : ""} />
        </button>
      </header>

      <section className="fund-product-toolbar" aria-label="基金产品查询">
        <form onSubmit={submitSearch}>
          <Search aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入基金代码或名称"
            aria-label="输入基金代码或名称"
          />
          <button type="submit" disabled={searching || !query.trim()}>
            {searching ? "查询中" : "查询"}
          </button>
        </form>
        <div className="fund-years-control" aria-label="历史窗口">
          <span>历史窗口</span>
          {([1, 3, 5] as ProductYears[]).map((value) => (
            <button
              key={value}
              type="button"
              className={years === value ? "active" : ""}
              onClick={() => setYears(value)}
            >
              {value} 年
            </button>
          ))}
        </div>
        {(searchError || searchResults.length > 0) && (
          <div className="fund-search-popover">
            {searchError ? (
              <span>{searchError}</span>
            ) : (
              searchResults.map((item) => (
                <button
                  key={`${item.code}-${item.type}`}
                  type="button"
                  onClick={() => selectSearchResult(item)}
                >
                  <strong>{item.code}</strong>
                  <span>{item.name}</span>
                  <small>{item.type}</small>
                  <ArrowRight aria-hidden="true" />
                </button>
              ))
            )}
          </div>
        )}
      </section>

      {loading && !payload ? (
        <ProductLoading />
      ) : error || !payload ? (
        <ProductFailure
          message={error ?? "当前无法读取基金产品数据"}
          onRetry={() => setRefreshKey((current) => current + 1)}
        />
      ) : (
        <>
          {payload.status !== "available" && (
            <section className="fund-product-notice">
              <TriangleAlert aria-hidden="true" />
              <div>
                <strong>部分数据需要关注</strong>
                <span>
                  各数据块独立返回，当前只展示可确认的事实，失败块不会使用其他来源补齐。
                </span>
              </div>
            </section>
          )}

          <ProductSummary analysis={analysis} trading={trading} />

          <div className="fund-product-sections">
            <ProductSection
              title="历史表现与风险"
              kicker="PERFORMANCE"
              meta={payload.sections.analysis.meta}
              icon={<BarChart3 aria-hidden="true" />}
            >
              {analysis ? (
                <PerformanceContent data={analysis} />
              ) : (
                <UnavailableSection section={payload.sections.analysis} />
              )}
            </ProductSection>

            <ProductSection
              title="产品基本资料"
              kicker="PROFILE"
              meta={payload.sections.profile.meta}
              icon={<Database aria-hidden="true" />}
            >
              {profile ? (
                <ProfileContent data={profile} />
              ) : (
                <UnavailableSection section={payload.sections.profile} />
              )}
            </ProductSection>

            <ProductSection
              title="申购与赎回状态"
              kicker="TRADING STATUS"
              meta={payload.sections.trading_status.meta}
              icon={<CalendarDays aria-hidden="true" />}
            >
              {trading ? (
                <TradingContent data={trading} />
              ) : (
                <UnavailableSection
                  section={payload.sections.trading_status}
                />
              )}
            </ProductSection>

            <ProductSection
              title="机构评级"
              kicker="RATING"
              meta={payload.sections.rating.meta}
              icon={<ShieldCheck aria-hidden="true" />}
            >
              {rating ? (
                <RatingContent data={rating} />
              ) : (
                <UnavailableSection section={payload.sections.rating} />
              )}
            </ProductSection>
          </div>

          {warnings.length > 0 && (
            <section className="fund-product-warnings" aria-label="数据警告">
              <TriangleAlert aria-hidden="true" />
              <div>
                <strong>数据警告</strong>
                {warnings.map((warning, index) => (
                  <span key={`${warningText(warning)}-${index}`}>
                    {warningText(warning)}
                  </span>
                ))}
              </div>
            </section>
          )}

          <AuditSummary payload={payload} />
        </>
      )}
    </main>
  );
}

function ProductSummary({
  analysis,
  trading,
}: {
  analysis: FundAnalysisData | null;
  trading: FundStatusData | null;
}) {
  const metrics = analysis?.metrics;
  return (
    <section className="fund-summary-band" aria-label="基金摘要">
      <SummaryItem
        label={latestValueLabel(analysis?.metric_basis)}
        value={displayNumber(metrics?.latest_value)}
        note={metrics?.latest_date ?? "数据日期不可用"}
      />
      <SummaryItem
        label="近 12 月收益"
        value={displayPercent(metrics?.returns_pct?.["12_month"])}
        tone={valueTone(metrics?.returns_pct?.["12_month"])}
        note={analysis?.metric_basis ?? "口径不可用"}
      />
      <SummaryItem
        label="年化波动"
        value={displayPercent(metrics?.annualized_volatility_pct)}
        note={`${analysis?.lookback_years ?? "—"} 年窗口`}
      />
      <SummaryItem
        label="当前回撤"
        value={displayPercent(metrics?.current_drawdown_pct)}
        tone={valueTone(metrics?.current_drawdown_pct)}
        note={`最大回撤 ${displayPercent(metrics?.max_drawdown_pct)}`}
      />
      <SummaryItem
        label="最新净值/收益"
        value={displayNumber(trading?.availability.latest_nav_or_income)}
        note={trading?.availability.source_report_date ?? "报告日期不可用"}
      />
    </section>
  );
}

function latestValueLabel(basis: string | null | undefined): string {
  const normalized = basis?.trim();
  if (!normalized) {
    return NEUTRAL_LATEST_VALUE_LABEL;
  }
  return METRIC_BASIS_LABELS[normalized] ?? NEUTRAL_LATEST_VALUE_LABEL;
}

function SummaryItem({
  label,
  value,
  note,
  tone = "",
}: {
  label: string;
  value: string;
  note: string;
  tone?: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function ProductSection({
  title,
  kicker,
  meta,
  icon,
  children,
}: {
  title: string;
  kicker: string;
  meta: DatasetMeta;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="fund-product-section">
      <header>
        <div className="fund-section-icon">{icon}</div>
        <div>
          <p>{kicker}</p>
          <h2>{title}</h2>
        </div>
        <div className="fund-section-status">
          <StatusBadge status={meta.status} />
          <span>{meta.as_of || "无统一事实日期"}</span>
        </div>
      </header>
      {children}
      <SectionEvidence meta={meta} />
    </section>
  );
}

function PerformanceContent({ data }: { data: FundAnalysisData }) {
  const metrics = data.metrics;
  const returns = [
    ["近 1 月", metrics?.returns_pct?.["1_month"]],
    ["近 3 月", metrics?.returns_pct?.["3_month"]],
    ["近 6 月", metrics?.returns_pct?.["6_month"]],
    ["近 12 月", metrics?.returns_pct?.["12_month"]],
  ] as const;
  const allocation = data.portfolio_snapshot?.asset_allocation;
  return (
    <div className="fund-section-body">
      <div className="fund-stat-grid">
        {returns.map(([label, value]) => (
          <DataPoint
            key={label}
            label={label}
            value={displayPercent(value)}
            tone={valueTone(value)}
          />
        ))}
        <DataPoint
          label="年化波动"
          value={displayPercent(metrics?.annualized_volatility_pct)}
        />
        <DataPoint
          label="最大回撤"
          value={displayPercent(metrics?.max_drawdown_pct)}
          tone={valueTone(metrics?.max_drawdown_pct)}
        />
        <DataPoint
          label="下行波动"
          value={displayPercent(
            metrics?.holding_experience?.downside_volatility_pct,
          )}
        />
        <DataPoint
          label="最长未创新高"
          value={
            metrics?.holding_experience?.longest_underwater_days == null
              ? "—"
              : `${String(metrics.holding_experience.longest_underwater_days)} 天`
          }
        />
      </div>
      {allocation?.items && allocation.items.length > 0 && (
        <div className="fund-allocation-block">
          <div>
            <strong>报告期资产配置</strong>
            <span>{allocation.report_date || "报告期不可用"}</span>
          </div>
          <div className="fund-allocation-list">
            {allocation.items.map((item) => (
              <div key={item.asset_type}>
                <span>{item.asset_type}</span>
                <strong>{displayPercent(item.weight_pct)}</strong>
              </div>
            ))}
          </div>
          {allocation.note && <small>{allocation.note}</small>}
        </div>
      )}
      <Coverage data={data} />
    </div>
  );
}

function Coverage({ data }: { data: FundAnalysisData }) {
  const available = data.metric_coverage?.available ?? [];
  const missing = data.metric_coverage?.missing_or_not_reliably_available ?? [];
  if (available.length === 0 && missing.length === 0) {
    return null;
  }
  return (
    <div className="fund-coverage-grid">
      <div>
        <strong>已覆盖</strong>
        <span>{available.join("、") || "—"}</span>
      </div>
      <div>
        <strong>未可靠取得</strong>
        <span>{missing.join("、") || "—"}</span>
      </div>
    </div>
  );
}

function ProfileContent({ data }: { data: FundProfileData }) {
  return (
    <div className="fund-section-body">
      <dl className="fund-profile-grid">
        {BASIC_FIELDS.map((key) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{displayRaw(data.basic_info[key])}</dd>
          </div>
        ))}
      </dl>
      {data.fee_rules.length > 0 && (
        <div className="fund-inline-table-wrap">
          <table className="fund-inline-table">
            <thead>
              <tr>
                <th>费用类型</th>
                <th>条件</th>
                <th>工具返回值</th>
              </tr>
            </thead>
            <tbody>
              {data.fee_rules.map((rule, index) => (
                <tr key={`${rule.fee_type}-${rule.condition}-${index}`}>
                  <td>{rule.fee_type || "—"}</td>
                  <td>{rule.condition || "—"}</td>
                  <td>{displayNumber(rule.fee)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.notes && <p className="fund-section-note">{data.notes}</p>}
    </div>
  );
}

function TradingContent({ data }: { data: FundStatusData }) {
  const availability = data.availability;
  if (!availability.confirmed) {
    return (
      <TradingNote
        message={availability.message || "当前无法确认该基金的交易状态。"}
      />
    );
  }
  const mode = availability.mode?.trim() || null;
  const exchange = availability.exchange ?? null;
  const offExchange = availability.off_exchange ?? null;
  const showExchange =
    mode === "exchange" || (mode === null && !offExchange && !!exchange);
  const showOffExchange =
    mode === "off_exchange" || (mode === null && !!offExchange);

  if (showExchange) {
    return exchange ? (
      <ExchangeTradingBlock data={exchange} />
    ) : (
      <TradingNote message="后端标记为场内交易口径，但未返回场内交易明细，当前无法确认。" />
    );
  }
  if (showOffExchange) {
    return offExchange ? (
      <OffExchangeTradingBlock data={offExchange} />
    ) : (
      <TradingNote message="后端标记为场外申赎口径，但未返回申赎明细，当前无法确认。" />
    );
  }
  return (
    <TradingNote
      message={
        availability.message ||
        "后端未返回交易口径（场内/场外），当前无法确认交易与申赎状态。"
      }
    />
  );
}

type FundExchangeStatus = NonNullable<
  FundStatusData["availability"]["exchange"]
>;
type FundOffExchangeStatus = NonNullable<
  FundStatusData["availability"]["off_exchange"]
>;

function ExchangeTradingBlock({ data }: { data: FundExchangeStatus }) {
  return (
    <div className="fund-section-body">
      <div className="fund-stat-grid fund-trading-grid">
        <DataPoint
          label="来源申购状态"
          value={data.source_subscription_status || "—"}
        />
        <DataPoint
          label="来源赎回状态"
          value={data.source_redemption_status || "—"}
        />
        <DataPoint label="交易时段" value={data.market_session || "—"} />
        <DataPoint
          label="标准时段开放"
          value={displayFlag(data.standard_market_open_now)}
        />
        <DataPoint
          label="可提交标准时段委托"
          value={displayFlag(data.can_submit_standard_session_order)}
        />
        <DataPoint label="当前可买入" value={displayFlag(data.can_buy_now)} />
        <DataPoint label="当前可卖出" value={displayFlag(data.can_sell_now)} />
      </div>
      {data.note && <p className="fund-section-note">{data.note}</p>}
    </div>
  );
}

function OffExchangeTradingBlock({ data }: { data: FundOffExchangeStatus }) {
  return (
    <div className="fund-section-body">
      <div className="fund-stat-grid fund-trading-grid">
        <DataPoint label="申购状态" value={data.subscription_status || "—"} />
        <DataPoint label="赎回状态" value={data.redemption_status || "—"} />
        <DataPoint
          label="购买起点"
          value={
            data.minimum_purchase_cny == null
              ? "—"
              : `${String(data.minimum_purchase_cny)} 元`
          }
        />
        <DataPoint
          label="日累计限额"
          value={
            data.daily_limit_cny == null
              ? "未返回有效限额"
              : `${String(data.daily_limit_cny)} 元`
          }
        />
        <DataPoint label="申购费" value={displayPercent(data.purchase_fee_pct)} />
        <DataPoint label="下一开放日" value={data.next_open_date || "—"} />
      </div>
      {data.note && <p className="fund-section-note">{data.note}</p>}
    </div>
  );
}

function TradingNote({ message }: { message: string }) {
  return (
    <div className="fund-section-body">
      <p className="fund-section-note">{message}</p>
    </div>
  );
}

function displayFlag(value: boolean | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value ? "是" : "否";
}

function RatingContent({ data }: { data: FundRatingData }) {
  const entries = Object.entries(data.ratings);
  return (
    <div className="fund-section-body">
      <div className="fund-rating-grid">
        {entries.map(([key, value]) => (
          <DataPoint
            key={key}
            label={RATING_LABELS[key] ?? key}
            value={displayNumber(value)}
          />
        ))}
      </div>
      {data.notes && <p className="fund-section-note">{data.notes}</p>}
    </div>
  );
}

function DataPoint({
  label,
  value,
  tone = "",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="fund-data-point">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function SectionEvidence({ meta }: { meta: DatasetMeta }) {
  return (
    <details className="fund-section-evidence">
      <summary>
        <ShieldCheck aria-hidden="true" />
        来源与审计
      </summary>
      <div>
        <span>工具：{meta.source_tools.join(" / ") || "—"}</span>
        <span>查询时间：{meta.queried_at || "—"}</span>
        <code>{meta.audit_refs.join("\n") || "无可用审计指纹"}</code>
      </div>
    </details>
  );
}

function AuditSummary({ payload }: { payload: FundProductResponse }) {
  const sections = Object.entries(payload.sections);
  return (
    <section className="fund-audit-summary">
      <header>
        <ShieldCheck aria-hidden="true" />
        <div>
          <p className="section-kicker">PROVENANCE</p>
          <h2>四块数据审计</h2>
        </div>
      </header>
      <div>
        {sections.map(([name, section]) => (
          <div key={name}>
            <span>{sectionLabel(name)}</span>
            <StatusBadge status={section.meta.status} />
            <strong>{section.meta.audit_refs.length} 个审计指纹</strong>
            <small>{section.meta.source_tools.join(" / ")}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function UnavailableSection({
  section,
}: {
  section: FundProductSection<unknown>;
}) {
  return (
    <div className="fund-unavailable-section">
      <TriangleAlert aria-hidden="true" />
      <div>
        <strong>当前无法确认该数据块</strong>
        <span>
          {section.envelope?.error?.message ??
            section.meta.error?.message ??
            "数据服务未返回可审计的结果，请稍后重试。"}
        </span>
        {(section.envelope?.error?.code || section.meta.error?.code) && (
          <code>
            {section.envelope?.error?.code || section.meta.error?.code}
          </code>
        )}
      </div>
    </div>
  );
}

function ProductLoading() {
  return (
    <div className="fund-product-loading" role="status">
      <span />
      <span />
      <div>
        <span />
        <span />
        <span />
        <span />
      </div>
      <strong>正在读取基金产品审计数据，首次加载可能需要十几秒</strong>
    </div>
  );
}

function ProductFailure({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="fund-product-failure">
      <TriangleAlert aria-hidden="true" />
      <h2>当前无法确认基金产品数据</h2>
      <p>{message}</p>
      <button type="button" onClick={onRetry}>
        <RefreshCw aria-hidden="true" />
        重试
      </button>
    </div>
  );
}

function productIdentity(
  payload: FundProductResponse | null,
): FundIdentity | null {
  if (!payload) {
    return null;
  }
  return (
    sectionData(payload.sections.analysis)?.fund ??
    sectionData(payload.sections.profile)?.fund ??
    sectionData(payload.sections.rating)?.fund ??
    sectionData(payload.sections.trading_status)?.fund ??
    null
  );
}

function sectionData<T>(
  section: FundProductSection<T> | undefined,
): T | null {
  return section?.envelope?.ok ? (section.envelope.data ?? null) : null;
}

function valueTone(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) {
    return "";
  }
  return value > 0 ? "value-positive" : "value-negative";
}

function displayRaw(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === ""
    ? "—"
    : String(value);
}

function isExchangeTradedETF(item: FundIdentity): boolean {
  const name = item.name.toUpperCase();
  return name.includes("ETF") && !name.includes("联接");
}

function sectionLabel(name: string): string {
  const labels: Record<string, string> = {
    analysis: "历史表现",
    profile: "产品资料",
    rating: "机构评级",
    trading_status: "交易状态",
  };
  return labels[name] ?? name;
}
