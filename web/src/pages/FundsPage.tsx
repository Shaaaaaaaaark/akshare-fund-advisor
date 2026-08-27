import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  CalendarRange,
  Flame,
  List,
  ShieldCheck,
} from "lucide-react";
import {
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { fetchETFDetail, searchFunds } from "../api";
import { warningText } from "../components/display";
import ETFLinkedCharts from "../components/ETFLinkedCharts";
import ResearchAgentDialog from "../components/ResearchAgentDialog";
import StatusBadge from "../components/StatusBadge";
import type {
  ETFDashboardData,
  ETFDetailResponse,
  ETFRecentRow,
  FundIdentity
} from "../types";

const DEFAULT_ETF = "510310";
const ETF_GROUPS = [
  { value: "all", label: "全部", keyword: "" },
  { value: "hs300", label: "宽基 / 沪深300", keyword: "沪深300" },
  { value: "sz50", label: "宽基 / 上证50", keyword: "上证50" },
  { value: "zz500", label: "宽基 / 中证500", keyword: "中证500" },
  { value: "zz1000", label: "宽基 / 中证1000", keyword: "中证1000" },
  { value: "cyb", label: "宽基 / 创业板", keyword: "创业板" },
  { value: "kc", label: "宽基 / 科创", keyword: "科创" },
  { value: "overseas", label: "跨境 / 海外", keyword: "海外" },
] as const;

const FEEDBACK_ITEMS = ["有用", "看不懂", "数据疑问", "想看解释"];
const FEATURE_ITEMS = [
  "股指期货",
  "险资ETF持仓",
  "存款搬家&开户指标",
  "基金抱团/打埋伏追踪",
  "其他",
];
const TOP_POLLS = [
  {
    id: "broad_market",
    question: "本周更关注宽基 ETF 吗？",
    options: [
      { value: "yes", label: "是", count: 126 },
      { value: "no", label: "不是", count: 84 },
    ],
  },
  {
    id: "valuation",
    question: "你更常看估值还是资金趋势？",
    options: [
      { value: "valuation", label: "估值", count: 98 },
      { value: "flow", label: "趋势", count: 112 },
    ],
  },
] as const;

type TableSortKey =
  | "date"
  | "close"
  | "daily_change_pct"
  | "turnover_yi_cny"
  | "volume_yi_units"
  | "drawdown_pct";

interface TableSort {
  key: TableSortKey;
  direction: "asc" | "desc";
}

export default function FundsPage() {
  const { fund } = useParams();
  const navigate = useNavigate();
  const activeFund = fund || DEFAULT_ETF;
  const [detail, setDetail] = useState<ETFDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectorFunds, setSelectorFunds] = useState<FundIdentity[]>([]);
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [activeStart, setActiveStart] = useState("");
  const [activeEnd, setActiveEnd] = useState("");
  const [tableSort, setTableSort] = useState<TableSort>({
    key: "date",
    direction: "desc",
  });
  const [darkMode, setDarkMode] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [listOpen, setListOpen] = useState(
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(min-width: 981px)").matches,
  );
  const [groupFilter, setGroupFilter] = useState("all");
  const [selectedFeedback, setSelectedFeedback] = useState<string | null>(null);
  const [featureStatus, setFeatureStatus] = useState<string | null>(null);
  const [pollVotes, setPollVotes] = useState<Record<string, string>>({});

  const load = useCallback((signal: AbortSignal) => {
    setLoading(true);
    setError(null);
    setDetail(null);
    void fetchETFDetail(activeFund, signal)
      .then((response) => {
        setDetail(response);
        const data = response.envelope?.data;
        if (data) {
          setDraftStart(data.lookback.actual_start_date);
          setDraftEnd(data.lookback.latest_date);
          setActiveStart(data.lookback.actual_start_date);
          setActiveEnd(data.lookback.latest_date);
        }
      })
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          return;
        }
        setError(reason instanceof Error ? reason.message : "ETF 数据请求失败");
      })
      .finally(() => {
        if (!signal.aborted) {
          setLoading(false);
        }
      });
  }, [activeFund]);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load, refreshKey]);

  const data = detail?.envelope?.data ?? null;

  useEffect(() => {
    const controller = new AbortController();
    void Promise.allSettled(
      [
        "沪深300ETF",
        "上证50ETF",
        "中证500ETF",
        "中证1000ETF",
        "创业板ETF",
        "科创ETF",
      ].map((query) => searchFunds(query, controller.signal)),
    )
      .then((results) => {
        if (controller.signal.aborted) {
          return;
        }
        setSelectorFunds(
          uniqueFunds(
            results.flatMap((result) =>
              result.status === "fulfilled"
                ? result.value.envelope?.data?.results ?? []
                : [],
            ),
          ),
        );
      });
    return () => controller.abort();
  }, []);

  const selectorETFs = useMemo(
    () =>
      uniqueFunds([
        ...(data?.identity ? [data.identity] : []),
        ...selectorFunds,
      ]).filter(isExchangeTradedETF),
    [data?.identity, selectorFunds],
  );
  const groupedETFs = useMemo(() => {
    const group = ETF_GROUPS.find((item) => item.value === groupFilter);
    if (!group?.keyword) {
      return selectorETFs;
    }
    return selectorETFs.filter((item) => item.name.includes(group.keyword));
  }, [groupFilter, selectorETFs]);
  const tableRows = useMemo(
    () => sortRows(data?.recent_rows ?? [], tableSort),
    [data?.recent_rows, tableSort],
  );

  function selectFund(item: FundIdentity) {
    navigate(`/funds/${encodeURIComponent(item.code)}`);
  }

  function applyDateRange(event: FormEvent) {
    event.preventDefault();
    if (!draftStart || !draftEnd || draftStart > draftEnd) {
      return;
    }
    setActiveStart(draftStart);
    setActiveEnd(draftEnd);
  }

  function resetPage() {
    setGroupFilter("all");
    setSelectedFeedback(null);
    setFeatureStatus(null);
    setTableSort({ key: "date", direction: "desc" });
    if (data) {
      setDraftStart(data.lookback.actual_start_date);
      setDraftEnd(data.lookback.latest_date);
      setActiveStart(data.lookback.actual_start_date);
      setActiveEnd(data.lookback.latest_date);
    }
    if (activeFund !== DEFAULT_ETF) {
      navigate(`/funds/${DEFAULT_ETF}`);
    }
  }

  return (
    <main
      className={`workbench-page etf-dashboard-page ${darkMode ? "theme-dark" : ""}`}
    >
      <div className="etf-global-controls" aria-label="页面操作">
        <button
          type="button"
          className="etf-agent-link"
          aria-haspopup="dialog"
          aria-expanded={agentOpen}
          onClick={() => setAgentOpen(true)}
        >
          问问AI研究
        </button>
        <Link className="etf-utility-button" to="/overview">
          数据总览页
        </Link>
        <button type="button" className="etf-utility-button" disabled>
          公开只读
        </button>
        <button
          type="button"
          className="etf-utility-button"
          onClick={resetPage}
        >
          复位
        </button>
        <button
          type="button"
          className="etf-utility-button"
          onClick={() => setDarkMode((current) => !current)}
        >
          {darkMode ? "日间" : "夜间"}
        </button>
      </div>

      <header className="etf-reference-header">
        <section className="etf-hot-polls" aria-label="今日站队投票">
          <div className="etf-hot-poll-line">
            <strong>
              <Flame aria-hidden="true" />
              今日站队
            </strong>
            {TOP_POLLS.map((poll, pollIndex) => (
              <div className="etf-poll-topic" key={poll.id}>
                {pollIndex > 0 && <i aria-hidden="true" />}
                <span>{poll.question}</span>
                {poll.options.map((option) => {
                  const selected = pollVotes[poll.id] === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      className={selected ? "active" : ""}
                      aria-pressed={selected}
                      onClick={() =>
                        setPollVotes((current) => ({
                          ...current,
                          [poll.id]: option.value,
                        }))
                      }
                    >
                      {option.label}
                      <b>{option.count + (selected ? 1 : 0)}</b>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </section>

        <div className="etf-brand-line">
          Fund Advisor · ETF 可信数据与审计研究终端
        </div>
        <div className="etf-title-line">
          <h1>
            {data
              ? `${data.identity.code} ${data.identity.name}`
              : `${activeFund} ETF 研究看板`}
          </h1>
        </div>

        <section className="etf-support-row" aria-label="数据来源与审计">
          <div className="etf-featured-source">
            <span>数据工具</span>
            <strong>AKShare</strong>
          </div>
          <div className="etf-source-ticker">
            <span>来源追踪</span>
            <div>
              <b>东方财富 · 新浪证券 · 原始口径</b>
            </div>
          </div>
          <button
            type="button"
            className="etf-audit-jump"
            onClick={() =>
              document
                .querySelector(".etf-data-boundary")
                ?.scrollIntoView({ behavior: "smooth", block: "center" })
            }
          >
            <ShieldCheck aria-hidden="true" />
            查看数据审计
          </button>
        </section>

        <p className="etf-meta-line">
          {data
            ? `${data.identity.type} · 数据更新 ${data.summary.latest_date} · ${data.basis_note}`
            : "正在读取经过审计的 ETF 历史行情。"}
        </p>

        <section className="etf-feedback-row" aria-label="反馈与功能入口">
          <div className="etf-feedback-group">
            <span>反馈</span>
            {FEEDBACK_ITEMS.map((item) => (
              <button
                key={item}
                type="button"
                className={selectedFeedback === item ? "active" : ""}
                onClick={() => setSelectedFeedback(item)}
              >
                {item}
              </button>
            ))}
            <button type="button" onClick={() => setAgentOpen(true)}>
              提问箱
            </button>
          </div>
          <i />
          <div className="etf-feedback-group">
            <strong>下个功能上什么？</strong>
            {FEATURE_ITEMS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() =>
                  setFeatureStatus(`${item} 已记录，当前尚未接入审计数据工具`)
                }
              >
                {item}
              </button>
            ))}
          </div>
          {(selectedFeedback || featureStatus) && (
            <span className="etf-feedback-status">
              {featureStatus || "收到，感谢反馈"}
            </span>
          )}
        </section>

        <section className="etf-selector-toolbar" aria-label="ETF 选择">
          <button
            type="button"
            aria-expanded={listOpen}
            onClick={() => setListOpen((current) => !current)}
          >
            <List aria-hidden="true" />
            {listOpen ? "隐藏列表" : "显示列表"}
          </button>
          <select
            aria-label="ETF 分组"
            value={groupFilter}
            onChange={(event) => setGroupFilter(event.target.value)}
          >
            {ETF_GROUPS.map((group) => (
              <option key={group.value} value={group.value}>
                {group.label}
              </option>
            ))}
          </select>
          <select
            aria-label="ETF"
            value={
              groupedETFs.some((item) => item.code === activeFund)
                ? activeFund
                : ""
            }
            onChange={(event) => {
              const item = selectorETFs.find(
                (candidate) => candidate.code === event.target.value,
              );
              if (item) {
                selectFund(item);
              }
            }}
          >
            {!groupedETFs.some((item) => item.code === activeFund) && (
              <option value="">选择 ETF</option>
            )}
            {groupedETFs.map((item) => (
              <option key={item.code} value={item.code}>
                {item.code} {item.name}
              </option>
            ))}
          </select>
        </section>
      </header>

      {error ? (
        <ETFError message={error} onRetry={() => setRefreshKey((key) => key + 1)} />
      ) : loading && !data ? (
        <ETFLoading />
      ) : !data || !detail?.envelope?.ok ? (
        <ETFError
          message={
            detail?.meta.error?.message ||
            "当前无法确认该 ETF 的历史行情，请稍后重试。"
          }
          onRetry={() => setRefreshKey((key) => key + 1)}
        />
      ) : (
        <ETFContent
          data={data}
          detail={detail}
          activeStart={activeStart}
          activeEnd={activeEnd}
          draftStart={draftStart}
          draftEnd={draftEnd}
          setDraftStart={setDraftStart}
          setDraftEnd={setDraftEnd}
          setActiveStart={setActiveStart}
          setActiveEnd={setActiveEnd}
          applyDateRange={applyDateRange}
          tableRows={tableRows}
          tableSort={tableSort}
          setTableSort={setTableSort}
          darkMode={darkMode}
          funds={groupedETFs}
          activeFund={activeFund}
          listOpen={listOpen}
          onSelectFund={selectFund}
        />
      )}

      <ResearchAgentDialog
        key={activeFund}
        open={agentOpen}
        fundCode={activeFund}
        fundName={data?.identity.name}
        onClose={() => setAgentOpen(false)}
      />
    </main>
  );
}

function ETFContent({
  data,
  detail,
  activeStart,
  activeEnd,
  draftStart,
  draftEnd,
  setDraftStart,
  setDraftEnd,
  setActiveStart,
  setActiveEnd,
  applyDateRange,
  tableRows,
  tableSort,
  setTableSort,
  darkMode,
  funds,
  activeFund,
  listOpen,
  onSelectFund,
}: {
  data: ETFDashboardData;
  detail: ETFDetailResponse;
  activeStart: string;
  activeEnd: string;
  draftStart: string;
  draftEnd: string;
  setDraftStart: (value: string) => void;
  setDraftEnd: (value: string) => void;
  setActiveStart: (value: string) => void;
  setActiveEnd: (value: string) => void;
  applyDateRange: (event: FormEvent) => void;
  tableRows: ETFRecentRow[];
  tableSort: TableSort;
  setTableSort: (sort: TableSort) => void;
  darkMode: boolean;
  funds: FundIdentity[];
  activeFund: string;
  listOpen: boolean;
  onSelectFund: (fund: FundIdentity) => void;
}) {
  const warnings = detail.meta.warnings ?? [];
  const [tooltipEnabled, setTooltipEnabled] = useState(true);
  const [mobileView, setMobileView] = useState<"charts" | "trend">("charts");
  const [draggingHandle, setDraggingHandle] = useState<"start" | "end" | null>(
    null,
  );
  const latestRange = data.range_summaries[0];
  const timelineDates = useMemo(
    () =>
      Array.from(
        new Set(data.charts.price.chart_series.map(([date]) => date)),
      ).sort(),
    [data.charts.price.chart_series],
  );
  const timelineMax = Math.max(timelineDates.length - 1, 0);
  const startIndex = boundedDateIndex(timelineDates, activeStart, "start");
  const endIndex = boundedDateIndex(timelineDates, activeEnd, "end");
  const rangeStyle = {
    "--range-start": `${timelineMax ? (startIndex / timelineMax) * 100 : 0}%`,
    "--range-end": `${timelineMax ? (endIndex / timelineMax) * 100 : 100}%`,
  } as CSSProperties;

  function setTimelineRange(nextStartIndex: number, nextEndIndex: number) {
    const nextStart = timelineDates[nextStartIndex];
    const nextEnd = timelineDates[nextEndIndex];
    if (!nextStart || !nextEnd) {
      return;
    }
    setDraftStart(nextStart);
    setDraftEnd(nextEnd);
    setActiveStart(nextStart);
    setActiveEnd(nextEnd);
  }

  function updateTimelineFromPointer(
    event: Pick<
      ReactPointerEvent<HTMLDivElement>,
      "clientX" | "currentTarget"
    >,
    handle: "start" | "end" | null,
  ): "start" | "end" {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(
      1,
      Math.max(0, (event.clientX - rect.left) / rect.width),
    );
    const nextIndex = Math.round(ratio * timelineMax);
    const nextHandle =
      handle ||
      (Math.abs(nextIndex - startIndex) <= Math.abs(nextIndex - endIndex)
        ? "start"
        : "end");
    if (nextHandle === "start") {
      setTimelineRange(Math.min(nextIndex, endIndex), endIndex);
    } else {
      setTimelineRange(startIndex, Math.max(nextIndex, startIndex));
    }
    return nextHandle;
  }

  return (
    <>
      <nav className="etf-mobile-view-switch" aria-label="手机视图切换">
        <button
          type="button"
          className={mobileView === "charts" ? "active" : ""}
          onClick={() => setMobileView("charts")}
        >
          主图
        </button>
        <button
          type="button"
          className={mobileView === "trend" ? "active" : ""}
          onClick={() => setMobileView("trend")}
        >
          趋势追踪
        </button>
      </nav>

      <section
        className={`etf-dashboard-grid ${listOpen ? "" : "etf-dashboard-grid-rail-collapsed"
          } etf-mobile-view-${mobileView}`}
      >
        {listOpen && (
          <aside className="etf-rail-panel" aria-label="ETF 列表">
            <div className="etf-rail-list">
              {funds.map((fund) => (
                <button
                  key={fund.code}
                  type="button"
                  className={fund.code === activeFund ? "active" : ""}
                  onClick={() => onSelectFund(fund)}
                >
                  <strong>{fund.name}</strong>
                  <span>{fund.code}</span>
                  <small>{fund.type}</small>
                </button>
              ))}
            </div>
          </aside>
        )}

        <section className="etf-main-stage" aria-label="ETF 日度图主视图">
          <section className="etf-metric-grid" aria-label="最新数据摘要">
            <MetricCard label="最新日期" value={data.summary.latest_date} />
            <MetricCard
              label="历史收盘价"
              value={metric(data.summary.latest_close, " 元")}
            />
            <MetricCard
              label="成交额"
              value={metric(data.summary.latest_turnover_yi_cny, " 亿元")}
            />
            <MetricCard
              label="成交量"
              value={metric(data.summary.latest_volume_yi_units, " 亿份")}
            />
            <MetricCard
              label="当日涨跌"
              value={signed(data.summary.latest_change_pct, "%")}
              tone={tone(data.summary.latest_change_pct)}
            />
            <MetricCard
              label="当前回撤"
              value={signed(data.summary.current_drawdown_pct, "%")}
              tone={tone(data.summary.current_drawdown_pct)}
            />
          </section>

          {data.market_snapshot && (
            <section className="etf-spot-strip" aria-label="场内行情快照">
              <span>场内快照 {displayDate(data.market_snapshot.date)}</span>
              <b>
                最新价 {metric(data.market_snapshot.latest_price, " 元")}
              </b>
              <b>IOPV {metric(data.market_snapshot.iopv, " 元")}</b>
              <b className={tone(data.market_snapshot.premium_rate_pct)}>
                溢价 {signed(data.market_snapshot.premium_rate_pct, "%")}
              </b>
              <small>
                {data.market_snapshot.usable_for_current_decision
                  ? "可用于当前观察"
                  : "当前观察不可用"}
              </small>
            </section>
          )}

          <section className="etf-range-strip" aria-label="区间摘要">
            {data.range_summaries.map((item) => (
              <button
                key={item.key}
                type="button"
                className={
                  activeStart === item.actual_start_date &&
                    activeEnd === item.latest_date
                    ? "active"
                    : ""
                }
                onClick={() => {
                  setDraftStart(item.actual_start_date);
                  setDraftEnd(item.latest_date);
                  setActiveStart(item.actual_start_date);
                  setActiveEnd(item.latest_date);
                }}
              >
                <strong>{item.label}</strong>
                <span>
                  价格 <b className={tone(item.price_return_pct)}>
                    {signed(item.price_return_pct, "%")}
                  </b>
                </span>
                <span>
                  成交额 <b>{metric(item.turnover_yi_cny, " 亿")}</b>
                </span>
                <span>
                  最大回撤 <b className={tone(item.maximum_drawdown_pct)}>
                    {signed(item.maximum_drawdown_pct, "%")}
                  </b>
                </span>
              </button>
            ))}
          </section>

          <form className="etf-date-range" onSubmit={applyDateRange}>
            <CalendarRange aria-hidden="true" />
            <label>
              <span>开始</span>
              <input
                type="date"
                min={data.lookback.actual_start_date}
                max={draftEnd || data.lookback.latest_date}
                value={draftStart}
                onChange={(event) => setDraftStart(event.target.value)}
              />
            </label>
            <label>
              <span>结束</span>
              <input
                type="date"
                min={draftStart || data.lookback.actual_start_date}
                max={data.lookback.latest_date}
                value={draftEnd}
                onChange={(event) => setDraftEnd(event.target.value)}
              />
            </label>
            <button type="submit" disabled={!draftStart || !draftEnd || draftStart > draftEnd}>
              应用
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setDraftStart(data.lookback.actual_start_date);
                setDraftEnd(data.lookback.latest_date);
                setActiveStart(data.lookback.actual_start_date);
                setActiveEnd(data.lookback.latest_date);
              }}
            >
              全区间
            </button>
          </form>

          <section className="etf-time-navigator" aria-label="图表时间位置">
            <header>
              <div>
                <strong>
                  {activeStart} 至 {activeEnd}
                </strong>
                <span>
                  {activeStart === data.lookback.actual_start_date &&
                    activeEnd === data.lookback.latest_date
                    ? "全区间"
                    : "自定义区间"}
                </span>
              </div>
              <div className="etf-chart-actions">
                <button
                  type="button"
                  onClick={() => setTooltipEnabled((current) => !current)}
                >
                  {tooltipEnabled ? "关闭悬浮窗" : "打开悬浮窗"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (!latestRange) {
                      return;
                    }
                    setDraftStart(latestRange.actual_start_date);
                    setDraftEnd(latestRange.latest_date);
                    setActiveStart(latestRange.actual_start_date);
                    setActiveEnd(latestRange.latest_date);
                  }}
                >
                  最新
                </button>
                <StatusBadge status={detail.meta.status} />
              </div>
            </header>
            <div
              className="etf-time-track"
              role="group"
              aria-label="当前图表时间窗口"
              style={rangeStyle}
              onPointerDown={(event) => {
                if (timelineMax === 0) {
                  return;
                }
                event.currentTarget.setPointerCapture(event.pointerId);
                setDraggingHandle(updateTimelineFromPointer(event, null));
              }}
              onPointerMove={(event) => {
                if (draggingHandle && event.currentTarget.hasPointerCapture(event.pointerId)) {
                  updateTimelineFromPointer(event, draggingHandle);
                }
              }}
              onPointerUp={(event) => {
                if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                  event.currentTarget.releasePointerCapture(event.pointerId);
                }
                setDraggingHandle(null);
              }}
              onPointerCancel={() => setDraggingHandle(null)}
              onClick={(event) => {
                if (timelineMax > 0) {
                  updateTimelineFromPointer(event, null);
                }
              }}
            >
              <div className="etf-time-window" aria-hidden="true" />
              <input
                className="etf-time-range etf-time-range-start"
                type="range"
                aria-label="图表开始日期"
                min={0}
                max={timelineMax}
                value={startIndex}
                disabled={timelineMax === 0}
                onChange={(event) =>
                  setTimelineRange(
                    Math.min(Number(event.target.value), endIndex),
                    endIndex,
                  )
                }
              />
              <input
                className="etf-time-range etf-time-range-end"
                type="range"
                aria-label="图表结束日期"
                min={0}
                max={timelineMax}
                value={endIndex}
                disabled={timelineMax === 0}
                onChange={(event) =>
                  setTimelineRange(
                    startIndex,
                    Math.max(Number(event.target.value), startIndex),
                  )
                }
              />
            </div>
          </section>

          <section
            id="etf-main-chart"
            className="etf-chart-section"
            aria-label="ETF 五联图"
          >
            <ETFLinkedCharts
              charts={data.charts}
              startDate={activeStart}
              endDate={activeEnd}
              darkMode={darkMode}
              showTooltip={tooltipEnabled}
            />
          </section>

          {warnings.length > 0 && (
            <section className="etf-warning-list" aria-label="数据警告">
              <strong>数据警告</strong>
              {warnings.map((warning, index) => (
                <span key={`${warningText(warning)}-${index}`}>
                  {warningText(warning)}
                </span>
              ))}
            </section>
          )}

          <section className="etf-data-boundary">
            <div>
              <strong>当前未接入</strong>
              <span>{data.missing_or_not_reliably_available.join("、")}</span>
            </div>
            <div>
              <strong>来源与审计</strong>
              <span>
                {data.data_integrity.source_interface} · 查询于{" "}
                {detail.meta.queried_at}
              </span>
              <code>
                {detail.meta.audit_refs.join(" · ") || "无可用审计指纹"}
              </code>
            </div>
          </section>
        </section>

        <aside
          id="etf-trend-table"
          className="etf-trend-panel"
          aria-label="最近交易日趋势看板"
        >
          <header>
            <div>
              <h2>最近交易日趋势</h2>
              <span>点击表头排序</span>
            </div>
          </header>
          <div className="etf-trend-table-wrap">
            <table className="etf-trend-table">
              <thead>
                <tr>
                  <ETFSortableHeader
                    label="日期"
                    sortKey="date"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                  <ETFSortableHeader
                    label="收盘价"
                    sortKey="close"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                  <ETFSortableHeader
                    label="价格变动"
                    sortKey="daily_change_pct"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                  <ETFSortableHeader
                    label="成交额"
                    sortKey="turnover_yi_cny"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                  <ETFSortableHeader
                    label="成交量"
                    sortKey="volume_yi_units"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                  <ETFSortableHeader
                    label="回撤"
                    sortKey="drawdown_pct"
                    sort={tableSort}
                    onSort={setTableSort}
                  />
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row) => (
                  <tr key={row.date}>
                    <td>{row.date}</td>
                    <td>{metric(row.close, " 元")}</td>
                    <td className={tone(row.daily_change_pct)}>
                      {signed(row.daily_change_pct, "%")}
                    </td>
                    <td>{metric(row.turnover_yi_cny, " 亿")}</td>
                    <td>{metric(row.volume_yi_units, " 亿份")}</td>
                    <td className={tone(row.drawdown_pct)}>
                      {signed(row.drawdown_pct, "%")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </aside>
      </section>
    </>
  );
}

function MetricCard({
  label,
  value,
  tone: colorTone = "",
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong className={colorTone}>{value}</strong>
    </div>
  );
}

function ETFSortableHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: TableSortKey;
  sort: TableSort;
  onSort: (sort: TableSort) => void;
}) {
  const active = sort.key === sortKey;
  const Icon = !active
    ? ArrowUpDown
    : sort.direction === "asc"
      ? ArrowUp
      : ArrowDown;
  return (
    <th aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() =>
          onSort({
            key: sortKey,
            direction:
              active && sort.direction === "asc" ? "desc" : "asc",
          })
        }
      >
        {label}
        <Icon aria-hidden="true" />
      </button>
    </th>
  );
}

function sortRows(rows: ETFRecentRow[], sort: TableSort): ETFRecentRow[] {
  return [...rows].sort((left, right) => {
    const leftValue = left[sort.key];
    const rightValue = right[sort.key];
    if (leftValue === null && rightValue === null) {
      return 0;
    }
    if (leftValue === null) {
      return 1;
    }
    if (rightValue === null) {
      return -1;
    }
    const comparison =
      typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue));
    return sort.direction === "asc" ? comparison : -comparison;
  });
}

function boundedDateIndex(
  dates: string[],
  target: string,
  boundary: "start" | "end",
): number {
  if (dates.length === 0) {
    return 0;
  }
  const exact = dates.indexOf(target);
  if (exact >= 0) {
    return exact;
  }
  if (boundary === "start") {
    const insertion = dates.findIndex((date) => date > target);
    return insertion < 0 ? dates.length - 1 : insertion;
  }
  for (let index = dates.length - 1; index >= 0; index -= 1) {
    if (dates[index] < target) {
      return index;
    }
  }
  return 0;
}

function uniqueFunds(items: FundIdentity[]): FundIdentity[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    if (!item.code || seen.has(item.code)) {
      return false;
    }
    seen.add(item.code);
    return true;
  });
}

function isExchangeTradedETF(item: FundIdentity): boolean {
  const name = item.name.toUpperCase();
  return name.includes("ETF") && !name.includes("联接");
}

function metric(value: number | null | undefined, unit: string): string {
  return value === null || value === undefined ? "—" : `${String(value)}${unit}`;
}

function displayDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "—";
}

function signed(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return `${value > 0 ? "+" : ""}${String(value)}${unit}`;
}

function tone(value: number | null | undefined): string {
  if (value === null || value === undefined || value === 0) {
    return "";
  }
  return value > 0 ? "value-positive" : "value-negative";
}

function ETFLoading() {
  return (
    <div className="etf-loading" role="status">
      <span />
      <span />
      <span />
      <strong>正在读取 ETF 审计数据</strong>
    </div>
  );
}

function ETFError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="etf-error-state">
      <strong>当前无法确认 ETF 数据</strong>
      <span>{message}</span>
      <button type="button" onClick={onRetry}>
        重试
      </button>
    </div>
  );
}
