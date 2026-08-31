import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Bot,
  CalendarRange,
  CircleHelp,
  Flame,
  GripVertical,
  Layers3,
  LayoutDashboard,
  List,
  Maximize2,
  Minimize2,
  Moon,
  RefreshCw,
  RotateCcw,
  Sun,
  X,
} from "lucide-react";
import {
  type CSSProperties,
  type FormEvent,
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  fetchETFDetail,
  fetchPanelInteractions,
  searchFunds,
  submitPanelInteraction,
} from "../api";
import { warningText } from "../components/display";
import ETFLinkedCharts from "../components/ETFLinkedCharts";
import ETFPriceShareChart from "../components/ETFPriceShareChart";
import ResearchAgentDialog from "../components/ResearchAgentDialog";
import StatusBadge from "../components/StatusBadge";
import {
  TerminalButton,
  TerminalLink,
  TerminalSelect,
} from "../components/TerminalControls";
import type {
  ETFDashboardData,
  ETFDetailResponse,
  ETFRecentRow,
  FundIdentity,
  PanelInteractionKind,
  PanelInteractionSummary,
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

const FEEDBACK_ITEMS = [
  { key: "useful", label: "有用" },
  { key: "unclear", label: "看不懂" },
  { key: "data_question", label: "数据疑问" },
  { key: "want_explanation", label: "想看解释" },
] as const;
const FEATURE_ITEMS = [
  { key: "index_futures", label: "股指期货" },
  { key: "insurance_etf_holdings", label: "险资ETF持仓" },
  { key: "deposit_account_flow", label: "存款搬家&开户指标" },
  { key: "fund_crowding", label: "基金抱团/打埋伏追踪" },
  { key: "other", label: "其他" },
] as const;
const HOT_POLLS = [
  {
    key: "korea_market",
    question: "韩国股市还会继续崩吗？",
  },
  {
    key: "feng_return",
    question: "峰哥还会回来吗？",
  },
] as const;

type TableSortKey =
  | "date"
  | "close"
  | "daily_change_pct"
  | "turnover_yi_cny"
  | "turnover_percentile_pct"
  | "volume_yi_units"
  | "drawdown_pct"
  | "total_shares_change_yi_units"
  | "financing_balance_change_yi_cny";

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
  const [resetVersion, setResetVersion] = useState(0);
  const [selectorFunds, setSelectorFunds] = useState<FundIdentity[]>([]);
  const [draftStart, setDraftStart] = useState("");
  const [draftEnd, setDraftEnd] = useState("");
  const [activeStart, setActiveStart] = useState("");
  const [activeEnd, setActiveEnd] = useState("");
  const [tableSort, setTableSort] = useState<TableSort>({
    key: "date",
    direction: "desc",
  });
  const [darkMode, setDarkMode] = useState(() =>
    storedBoolean("fund-advisor.etf.dark-mode", false),
  );
  const [agentOpen, setAgentOpen] = useState(false);
  const [listOpen, setListOpen] = useState(() =>
    storedBoolean("fund-advisor.etf.list-open", false),
  );
  const [groupFilter, setGroupFilter] = useState(() =>
    storedString("fund-advisor.etf.group-filter", "all"),
  );
  const [interactions, setInteractions] =
    useState<PanelInteractionSummary | null>(null);
  const [interactionPending, setInteractionPending] = useState<string | null>(
    null,
  );
  const [interactionStatus, setInteractionStatus] = useState<string | null>(
    null,
  );
  const [mobileFeedbackOpen, setMobileFeedbackOpen] = useState<
    "feedback" | "features" | null
  >(null);
  const clientId = useMemo(panelClientId, []);
  const selectorLoaded = useRef(false);
  const selectorController = useRef<AbortController | null>(null);

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
    if (!data || selectorLoaded.current) {
      return;
    }
    selectorLoaded.current = true;
    const controller = new AbortController();
    selectorController.current = controller;
    const queries = [
      "沪深300ETF",
      "上证50ETF",
      "中证500ETF",
      "中证1000ETF",
      "创业板ETF",
      "科创ETF",
    ];
    void (async () => {
      const loaded: FundIdentity[] = [];
      for (let index = 0; index < queries.length; index += 3) {
        const results = await Promise.allSettled(
          queries
            .slice(index, index + 3)
            .map((query) => searchFunds(query, controller.signal)),
        );
        if (controller.signal.aborted) {
          return;
        }
        loaded.push(
          ...results.flatMap((result) =>
            result.status === "fulfilled"
              ? result.value.envelope?.data?.results ?? []
              : [],
          ),
        );
        setSelectorFunds(uniqueFunds(loaded));
      }
    })();
  }, [data]);

  useEffect(
    () => () => {
      selectorController.current?.abort();
    },
    [],
  );

  useEffect(() => {
    storePreference("fund-advisor.etf.dark-mode", String(darkMode));
  }, [darkMode]);

  useEffect(() => {
    storePreference("fund-advisor.etf.list-open", String(listOpen));
  }, [listOpen]);

  useEffect(() => {
    storePreference("fund-advisor.etf.group-filter", groupFilter);
  }, [groupFilter]);

  useEffect(() => {
    const controller = new AbortController();
    setInteractions(null);
    setInteractionStatus(null);
    void fetchPanelInteractions(clientId, activeFund, controller.signal)
      .then(setInteractions)
      .catch((reason: unknown) => {
        if (reason instanceof DOMException && reason.name === "AbortError") {
          return;
        }
        setInteractionStatus(
          reason instanceof Error ? reason.message : "互动数据读取失败",
        );
      });
    return () => controller.abort();
  }, [activeFund, clientId]);

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

  async function recordInteraction(
    kind: PanelInteractionKind,
    topicKey: string,
    optionKey: string,
  ) {
    const pendingKey = `${kind}:${topicKey}:${optionKey}`;
    setInteractionPending(pendingKey);
    setInteractionStatus(null);
    try {
      const summary = await submitPanelInteraction({
        kind,
        topic_key: topicKey,
        option_key: optionKey,
        client_id: clientId,
        fund: activeFund,
      });
      setInteractions(summary);
      setInteractionStatus("已记录");
    } catch (reason) {
      setInteractionStatus(
        reason instanceof Error ? reason.message : "互动提交失败",
      );
    } finally {
      setInteractionPending(null);
    }
  }

  function resetPage() {
    setGroupFilter("all");
    setMobileFeedbackOpen(null);
    setTableSort({ key: "date", direction: "desc" });
    setDarkMode(false);
    setListOpen(false);
    setInteractionStatus(null);
    setResetVersion((version) => version + 1);
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
      <header className="etf-reference-header">
        <section className="etf-hot-polls" aria-label="热点站队投票">
          <div className="etf-hot-poll-line">
            <strong>
              <Flame aria-hidden="true" />
              今日站队
            </strong>
            {HOT_POLLS.map((poll, index) => {
              const summary = interactions?.hot_polls[poll.key];
              return (
                <span className="etf-poll-topic" key={poll.key}>
                  {index > 0 && <i aria-hidden="true" />}
                  <span>{poll.question}</span>
                  {(["yes", "no"] as const).map((choice) => {
                    const pendingKey = `hot_poll:${poll.key}:${choice}`;
                    return (
                      <button
                        key={choice}
                        type="button"
                        disabled={interactionPending !== null}
                        aria-pressed={summary?.selected_option === choice}
                        className={
                          summary?.selected_option === choice ? "active" : ""
                        }
                        onClick={() =>
                          void recordInteraction(
                            "hot_poll",
                            poll.key,
                            choice,
                          )
                        }
                      >
                        {choice === "yes" ? "是" : "不是"}
                        <b>
                          {interactionPending === pendingKey
                            ? "…"
                            : summary?.counts[choice] ?? 0}
                        </b>
                      </button>
                    );
                  })}
                </span>
              );
            })}
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

        <p className="etf-meta-line">
          {data
            ? `${data.identity.type} · 数据更新 ${data.summary.latest_date} · ${data.basis_note}`
            : "正在读取经过审计的 ETF 历史行情。"}
        </p>

        <section className="etf-feedback-row" aria-label="反馈与功能入口">
          <div className="etf-mobile-feedback-triggers">
            <button
              type="button"
              aria-expanded={mobileFeedbackOpen === "feedback"}
              onClick={() =>
                setMobileFeedbackOpen((current) =>
                  current === "feedback" ? null : "feedback",
                )
              }
            >
              反馈
            </button>
            <button
              type="button"
              aria-expanded={mobileFeedbackOpen === "features"}
              onClick={() =>
                setMobileFeedbackOpen((current) =>
                  current === "features" ? null : "features",
                )
              }
            >
              下个功能上什么？
            </button>
          </div>
          <div
            className={`etf-feedback-group ${mobileFeedbackOpen === "feedback" ? "mobile-expanded" : ""
              }`}
          >
            <span>反馈</span>
            {FEEDBACK_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                disabled={interactionPending !== null}
                aria-pressed={
                  interactions?.feedback.selected_option === item.key
                }
                className={
                  interactions?.feedback.selected_option === item.key
                    ? "active"
                    : ""
                }
                onClick={() =>
                  void recordInteraction(
                    "feedback",
                    "etf_feedback",
                    item.key,
                  )
                }
              >
                {item.label}
                <b>{interactions?.feedback.counts[item.key] ?? 0}</b>
              </button>
            ))}
            <button type="button" onClick={() => setAgentOpen(true)}>
              提问箱
            </button>
          </div>
          <i />
          <div
            className={`etf-feedback-group ${mobileFeedbackOpen === "features" ? "mobile-expanded" : ""
              }`}
          >
            <strong>下个功能上什么？</strong>
            {FEATURE_ITEMS.map((item) => (
              <button
                key={item.key}
                type="button"
                disabled={interactionPending !== null}
                aria-pressed={
                  interactions?.feature_vote.selected_option === item.key
                }
                className={
                  interactions?.feature_vote.selected_option === item.key
                    ? "active"
                    : ""
                }
                onClick={() =>
                  void recordInteraction(
                    "feature_vote",
                    "next_feature",
                    item.key,
                  )
                }
              >
                {item.label}
                <b>{interactions?.feature_vote.counts[item.key] ?? 0}</b>
              </button>
            ))}
          </div>
          {interactionStatus && (
            <span className="etf-feedback-status">
              {interactionStatus}
            </span>
          )}
        </section>

        <section className="etf-command-row" aria-label="ETF 研究工具栏">
          <section className="etf-selector-toolbar" aria-label="ETF 选择">
            <TerminalButton
              className="etf-list-toggle"
              aria-expanded={listOpen}
              onClick={() => setListOpen((current) => !current)}
            >
              <List aria-hidden="true" />
              {listOpen ? "隐藏列表" : "显示列表"}
            </TerminalButton>
            <TerminalSelect
              label="ETF 分组"
              value={groupFilter}
              onChange={(event) => setGroupFilter(event.target.value)}
            >
              {ETF_GROUPS.map((group) => (
                <option key={group.value} value={group.value}>
                  {group.label}
                </option>
              ))}
            </TerminalSelect>
            <TerminalSelect
              label="ETF"
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
            </TerminalSelect>
          </section>

          <div className="etf-global-controls" aria-label="页面操作">
            <TerminalButton
              tone="primary"
              className="etf-agent-link"
              aria-haspopup="dialog"
              aria-expanded={agentOpen}
              onClick={() => setAgentOpen(true)}
            >
              <Bot aria-hidden="true" />
              问问AI研究
            </TerminalButton>
            <TerminalLink className="etf-utility-button" to="/overview">
              <LayoutDashboard aria-hidden="true" />
              数据总览
            </TerminalLink>
            <TerminalButton
              className="etf-utility-button"
              aria-label="重新读取 ETF 审计数据"
              title="重新读取 ETF 审计数据"
              disabled={loading}
              onClick={() => setRefreshKey((key) => key + 1)}
            >
              <RefreshCw
                aria-hidden="true"
                className={loading ? "spin" : ""}
              />
              {loading ? "刷新中" : "刷新数据"}
            </TerminalButton>
            <TerminalButton
              className="etf-utility-button"
              onClick={resetPage}
            >
              <RotateCcw aria-hidden="true" />
              复位
            </TerminalButton>
            <TerminalButton
              className="etf-utility-button"
              onClick={() => setDarkMode((current) => !current)}
            >
              {darkMode ? (
                <Sun aria-hidden="true" />
              ) : (
                <Moon aria-hidden="true" />
              )}
              {darkMode ? "日间" : "夜间"}
            </TerminalButton>
          </div>
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
          resetVersion={resetVersion}
          onSelectFund={selectFund}
        />
      )}

      <p className="etf-copyright-line" aria-label="版权声明">
        <span>Fund Advisor · 可信金融数据研究工作台</span>
        <span>公开数据仅供个人研究参考，不构成投资建议。</span>
      </p>

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
  resetVersion,
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
  resetVersion: number;
  onSelectFund: (fund: FundIdentity) => void;
}) {
  const warnings = detail.meta.warnings ?? [];
  const supplemental = data.supplemental;
  const [tooltipEnabled, setTooltipEnabled] = useState(() =>
    storedBoolean("fund-advisor.etf.tooltips", true),
  );
  const [mobileView, setMobileView] = useState<"charts" | "trend">("charts");
  const [trendExpanded, setTrendExpanded] = useState(false);
  const [trendWidth, setTrendWidth] = useState(() =>
    storedNumber("fund-advisor.etf.trend-width", 520, 420, 760),
  );
  const [fusionOpen, setFusionOpen] = useState(false);
  const [helpKey, setHelpKey] = useState<string | null>(null);
  const [draggingHandle, setDraggingHandle] = useState<"start" | "end" | null>(
    null,
  );
  const recentDates = useMemo(
    () => data.recent_rows.map((row) => row.date).sort(),
    [data.recent_rows],
  );
  const auditedTrendRange = supplemental?.range_summaries[0];
  const defaultTrendEnd =
    auditedTrendRange?.latest_date ?? recentDates.at(-1) ?? "";
  const defaultTrendStart =
    auditedTrendRange?.actual_start_date ??
    recentDates[Math.max(0, recentDates.length - 5)] ??
    defaultTrendEnd;
  const [trendStart, setTrendStart] = useState(defaultTrendStart);
  const [trendEnd, setTrendEnd] = useState(defaultTrendEnd);
  const [trendDraftStart, setTrendDraftStart] = useState(defaultTrendStart);
  const [trendDraftEnd, setTrendDraftEnd] = useState(defaultTrendEnd);
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
  const dashboardStyle = {
    "--etf-trend-width": `${trendWidth}px`,
  } as CSSProperties;
  const visibleTrendRows = useMemo(
    () =>
      tableRows.filter(
        (row) =>
          (!trendStart || row.date >= trendStart) &&
          (!trendEnd || row.date <= trendEnd),
      ),
    [tableRows, trendEnd, trendStart],
  );
  const supplementalRange = supplemental?.range_summaries.find(
    (range) =>
      range.actual_start_date === trendStart &&
      range.latest_date === trendEnd,
  );

  useEffect(() => {
    document.body.classList.toggle("etf-trend-expanded", trendExpanded);
    return () => document.body.classList.remove("etf-trend-expanded");
  }, [trendExpanded]);

  useEffect(() => {
    setTrendStart(defaultTrendStart);
    setTrendEnd(defaultTrendEnd);
    setTrendDraftStart(defaultTrendStart);
    setTrendDraftEnd(defaultTrendEnd);
  }, [data.identity.code, defaultTrendEnd, defaultTrendStart]);

  useEffect(() => {
    storePreference("fund-advisor.etf.tooltips", String(tooltipEnabled));
  }, [tooltipEnabled]);

  useEffect(() => {
    storePreference("fund-advisor.etf.trend-width", String(trendWidth));
  }, [trendWidth]);

  useEffect(() => {
    if (resetVersion === 0) {
      return;
    }
    setTooltipEnabled(true);
    setMobileView("charts");
    setTrendExpanded(false);
    setTrendWidth(520);
    setFusionOpen(false);
    setHelpKey(null);
    setTrendStart(defaultTrendStart);
    setTrendEnd(defaultTrendEnd);
    setTrendDraftStart(defaultTrendStart);
    setTrendDraftEnd(defaultTrendEnd);
  }, [defaultTrendEnd, defaultTrendStart, resetVersion]);

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
        style={dashboardStyle}
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
            <MetricCard
              label="最新日期"
              value={data.summary.latest_date}
              onHelp={() => setHelpKey("latest_date")}
            />
            <MetricCard
              label="前复权收盘价"
              value={metric(data.summary.latest_close, " 元")}
              asOf={data.summary.latest_date}
              onHelp={() => setHelpKey("adjusted_close")}
            />
            <MetricCard
              label="成交额"
              value={metric(data.summary.latest_turnover_yi_cny, " 亿元")}
              asOf={data.summary.latest_date}
              onHelp={() => setHelpKey("turnover")}
            />
            <MetricCard
              label="交易所总份额"
              value={
                supplemental?.share.latest?.total_shares_yi_units == null
                  ? "待接入"
                  : metric(
                    supplemental.share.latest.total_shares_yi_units,
                    " 亿份",
                  )
              }
              asOf={supplemental?.share.latest_date}
              onHelp={() => setHelpKey("total_shares")}
            />
            <MetricCard
              label="ETF 融资余额"
              value={
                supplemental?.financing.latest
                  ?.financing_balance_yi_cny == null
                  ? "待接入"
                  : metric(
                    supplemental.financing.latest
                      .financing_balance_yi_cny,
                    " 亿元",
                  )
              }
              asOf={supplemental?.financing.latest_date}
              onHelp={() => setHelpKey("financing_balance")}
            />
            <MetricCard
              label="当前回撤"
              value={signed(data.summary.current_drawdown_pct, "%")}
              tone={tone(data.summary.current_drawdown_pct)}
              asOf={data.summary.latest_date}
              onHelp={() => setHelpKey("drawdown")}
            />
          </section>

          {(data.market_snapshot || supplemental) && (
            <section className="etf-spot-strip" aria-label="场内行情快照">
              <span>
                场内快照{" "}
                {displayDate(
                  data.market_snapshot?.date ||
                  supplemental?.financing.latest_date,
                )}
              </span>
              {data.market_snapshot && (
                <>
                  <b>
                    最新价{" "}
                    {metric(data.market_snapshot.latest_price, " 元")}
                  </b>
                  <b>IOPV {metric(data.market_snapshot.iopv, " 元")}</b>
                  <b className={tone(data.market_snapshot.premium_rate_pct)}>
                    溢价 {signed(data.market_snapshot.premium_rate_pct, "%")}
                  </b>
                </>
              )}
              <b
                className={tone(
                  supplemental?.share.latest
                    ?.total_shares_change_yi_units,
                )}
              >
                份额净变动{" "}
                {signed(
                  supplemental?.share.latest
                    ?.total_shares_change_yi_units,
                  " 亿份",
                )}
              </b>
              <b
                className={tone(
                  supplemental?.financing.latest
                    ?.financing_balance_change_yi_cny,
                )}
              >
                融资净新增{" "}
                {signed(
                  supplemental?.financing.latest
                    ?.financing_balance_change_yi_cny,
                  " 亿元",
                )}
              </b>
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
                <button
                  type="button"
                  aria-expanded={fusionOpen}
                  onClick={() => setFusionOpen((current) => !current)}
                >
                  <Layers3 aria-hidden="true" />
                  价格×份额
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

          {fusionOpen && (
            <section
              className="etf-fusion-panel"
              aria-label="ETF 价格与总份额融合图"
            >
              <header>
                <div>
                  <h2>ETF 价格 × 交易所总份额</h2>
                  <span>
                    仅连接最近最多 7 个通过交易所快照审计的真实点
                  </span>
                </div>
                <button
                  type="button"
                  aria-label="关闭价格与份额融合图"
                  title="关闭"
                  onClick={() => setFusionOpen(false)}
                >
                  <X aria-hidden="true" />
                </button>
              </header>
              {supplemental && supplemental.share.chart_series.length >= 2 ? (
                <ETFPriceShareChart
                  price={data.charts.price}
                  supplemental={supplemental}
                  darkMode={darkMode}
                />
              ) : (
                <div className="etf-fusion-unavailable">
                  当前 ETF 没有带统计日期且通过审计的份额序列。
                </div>
              )}
            </section>
          )}

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

        <div
          className="etf-dashboard-resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="调整主图与趋势表宽度"
          tabIndex={0}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              setTrendWidth(
                Math.min(760, Math.max(420, window.innerWidth - event.clientX - 16)),
              );
            }
          }}
          onPointerUp={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              setTrendWidth((width) => Math.min(760, width + 20));
            } else if (event.key === "ArrowRight") {
              setTrendWidth((width) => Math.max(420, width - 20));
            }
          }}
        >
          <GripVertical aria-hidden="true" />
        </div>

        {trendExpanded && (
          <button
            type="button"
            className="etf-trend-backdrop"
            aria-label="关闭趋势表"
            onClick={() => setTrendExpanded(false)}
          />
        )}
        <aside
          id="etf-trend-table"
          className={`etf-trend-panel ${trendExpanded ? "expanded" : ""}`}
          aria-label="最近交易日趋势看板"
        >
          <header>
            <div>
              <h2>{data.identity.name}最近一周趋势</h2>
              <span>点击表头排序</span>
            </div>
            <button
              type="button"
              className="etf-trend-expand"
              aria-expanded={trendExpanded}
              onClick={() => setTrendExpanded((current) => !current)}
            >
              {trendExpanded ? (
                <Minimize2 aria-hidden="true" />
              ) : (
                <Maximize2 aria-hidden="true" />
              )}
              {trendExpanded ? "收起" : "展开"}
            </button>
          </header>
          <form
            className="etf-trend-range-panel"
            onSubmit={(event) => {
              event.preventDefault();
              if (
                !trendDraftStart ||
                !trendDraftEnd ||
                trendDraftStart > trendDraftEnd
              ) {
                return;
              }
              setTrendStart(trendDraftStart);
              setTrendEnd(trendDraftEnd);
            }}
          >
            <label>
              <span>开始</span>
              <input
                type="date"
                min={recentDates[0]}
                max={trendDraftEnd || defaultTrendEnd}
                value={trendDraftStart}
                onChange={(event) => setTrendDraftStart(event.target.value)}
              />
            </label>
            <label>
              <span>结束</span>
              <input
                type="date"
                min={trendDraftStart || recentDates[0]}
                max={defaultTrendEnd}
                value={trendDraftEnd}
                onChange={(event) => setTrendDraftEnd(event.target.value)}
              />
            </label>
            <button
              type="submit"
              disabled={
                !trendDraftStart ||
                !trendDraftEnd ||
                trendDraftStart > trendDraftEnd
              }
            >
              应用
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => {
                setTrendDraftStart(defaultTrendStart);
                setTrendDraftEnd(defaultTrendEnd);
                setTrendStart(defaultTrendStart);
                setTrendEnd(defaultTrendEnd);
              }}
            >
              最近一周
            </button>
          </form>
          <section className="etf-trend-summary" aria-label="趋势合计摘要">
            <div className="etf-trend-summary-main">
              <span>
                {trendStart} 至 {trendEnd}
              </span>
              <strong>{data.identity.name}</strong>
            </div>
            <div>
              <span>区间记录</span>
              <strong>{visibleTrendRows.length} 条</strong>
            </div>
            <div>
              <span>合计份额变动</span>
              <strong
                className={tone(supplementalRange?.share_change_yi_units)}
              >
                {supplementalRange
                  ? signed(
                    supplementalRange.share_change_yi_units,
                    " 亿份",
                  )
                  : "当前区间不可用"}
              </strong>
            </div>
            <div>
              <span>合计净申赎</span>
              <strong>待接入</strong>
            </div>
            <div>
              <span>ETF融资净新增</span>
              <strong
                className={tone(
                  supplementalRange?.financing_net_change_yi_cny,
                )}
              >
                {supplementalRange
                  ? signed(
                    supplementalRange.financing_net_change_yi_cny,
                    " 亿元",
                  )
                  : "当前区间不可用"}
              </strong>
            </div>
            <div>
              <span>成分融资净新增</span>
              <strong>待接入</strong>
            </div>
          </section>
          <div className="etf-trend-table-wrap">
            <table className="etf-trend-table">
              <thead>
                <tr>
                  <ETFStaticHeader
                    label="ETF / 合计"
                    helpKey="etf_scope"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="日期"
                    sortKey="date"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="date"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="价格变动"
                    sortKey="daily_change_pct"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="daily_change"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="成交额"
                    sortKey="turnover_yi_cny"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="turnover"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="成交额分位"
                    sortKey="turnover_percentile_pct"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="turnover_percentile"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="净份额变动"
                    sortKey="total_shares_change_yi_units"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="share_change"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="变动绝对值分位"
                    helpKey="share_change_percentile"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="净申赎金额"
                    helpKey="net_subscription"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="净申赎绝对值分位"
                    helpKey="net_subscription_percentile"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="净申赎/指数成交额"
                    helpKey="net_subscription_ratio"
                    onHelp={setHelpKey}
                  />
                  <ETFSortableHeader
                    label="ETF融资净新增"
                    sortKey="financing_balance_change_yi_cny"
                    sort={tableSort}
                    onSort={setTableSort}
                    helpKey="etf_financing_change"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="ETF融资分位"
                    helpKey="etf_financing_percentile"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="成分融资净新增"
                    helpKey="constituent_financing_change"
                    onHelp={setHelpKey}
                  />
                  <ETFStaticHeader
                    label="成分融资分位"
                    helpKey="constituent_financing_percentile"
                    onHelp={setHelpKey}
                  />
                </tr>
              </thead>
              <tbody>
                {visibleTrendRows.map((row) => (
                  <tr key={row.date}>
                    <TrendCell
                      label="ETF / 合计"
                      value={data.identity.name}
                    />
                    <TrendCell label="日期" value={row.date} />
                    <TrendCell
                      label="价格变动"
                      value={signed(row.daily_change_pct, "%")}
                      className={tone(row.daily_change_pct)}
                    />
                    <TrendCell
                      label="成交额"
                      value={metric(row.turnover_yi_cny, " 亿")}
                    />
                    <TrendCell
                      label="成交额分位"
                      value={metric(row.turnover_percentile_pct, "%")}
                    />
                    <TrendCell
                      label="净份额变动"
                      value={signed(
                        row.total_shares_change_yi_units,
                        " 亿份",
                      )}
                      className={tone(row.total_shares_change_yi_units)}
                    />
                    <TrendCell
                      label="变动绝对值分位"
                      value="待接入"
                    />
                    <TrendCell label="净申赎金额" value="待接入" />
                    <TrendCell
                      label="净申赎绝对值分位"
                      value="待接入"
                    />
                    <TrendCell
                      label="净申赎/指数成交额"
                      value="待接入"
                    />
                    <TrendCell
                      label="ETF融资净新增"
                      value={signed(
                        row.financing_balance_change_yi_cny,
                        " 亿元",
                      )}
                      className={tone(
                        row.financing_balance_change_yi_cny,
                      )}
                    />
                    <TrendCell label="ETF融资分位" value="待接入" />
                    <TrendCell label="成分融资净新增" value="待接入" />
                    <TrendCell label="成分融资分位" value="待接入" />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </aside>
      </section>
      {helpKey && (
        <MetricHelpDialog
          helpKey={helpKey}
          onClose={() => setHelpKey(null)}
        />
      )}
    </>
  );
}

function TrendCell({
  label,
  value,
  className = "",
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <td>
      <span className="etf-mobile-cell-label">{label}</span>
      <span className={`etf-trend-cell-value ${className}`}>{value}</span>
    </td>
  );
}

function MetricCard({
  label,
  value,
  tone: colorTone = "",
  asOf,
  onHelp,
}: {
  label: string;
  value: string;
  tone?: string;
  asOf?: string | null;
  onHelp: () => void;
}) {
  return (
    <div>
      <span className="etf-metric-label">
        {label}
        <button
          type="button"
          aria-label={`说明：${label}`}
          title={`${label}说明`}
          onClick={onHelp}
        >
          <CircleHelp aria-hidden="true" />
        </button>
      </span>
      <strong className={colorTone}>{value}</strong>
      {asOf && <small>截至 {displayDate(asOf)}</small>}
    </div>
  );
}

function ETFSortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  helpKey,
  onHelp,
}: {
  label: string;
  sortKey: TableSortKey;
  sort: TableSort;
  onSort: (sort: TableSort) => void;
  helpKey: string;
  onHelp: (key: string) => void;
}) {
  const active = sort.key === sortKey;
  const Icon = !active
    ? ArrowUpDown
    : sort.direction === "asc"
      ? ArrowUp
      : ArrowDown;
  return (
    <th aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}>
      <div className="etf-table-heading">
        <button
          type="button"
          className="etf-sort-button"
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
        <button
          type="button"
          className="etf-help-button"
          aria-label={`说明：${label}`}
          title={`${label}说明`}
          onClick={() => onHelp(helpKey)}
        >
          <CircleHelp aria-hidden="true" />
        </button>
      </div>
    </th>
  );
}

function ETFStaticHeader({
  label,
  helpKey,
  onHelp,
}: {
  label: string;
  helpKey: string;
  onHelp: (key: string) => void;
}) {
  return (
    <th>
      <div className="etf-table-heading">
        <span>{label}</span>
        <button
          type="button"
          className="etf-help-button"
          aria-label={`说明：${label}`}
          title={`${label}说明`}
          onClick={() => onHelp(helpKey)}
        >
          <CircleHelp aria-hidden="true" />
        </button>
      </div>
    </th>
  );
}

const METRIC_HELP: Record<string, { title: string; body: string }> = {
  latest_date: {
    title: "最新日期",
    body: "ETF 日线主序列中的最后一个真实交易日期，不等同于页面查询时间。",
  },
  adjusted_close: {
    title: "前复权收盘价",
    body: "来自 ETF 历史行情的前复权日收盘价，用于连续观察，不代表投资者当日实际成交价。",
  },
  turnover: {
    title: "成交额",
    body: "交易所日线源成交额确定性换算为亿元，没有插值或前向填充。",
  },
  total_shares: {
    title: "交易所总份额",
    body: "上交所按统计日期披露的 ETF 基金份额。深交所当前接口缺少可核验统计日期时保持不可用。",
  },
  financing_balance: {
    title: "ETF 融资余额",
    body: "按 ETF 代码从交易所融资融券明细精确匹配的融资余额，不包含成分股融资余额。",
  },
  drawdown: {
    title: "当前回撤",
    body: "当前收盘价相对所选观察窗口内此前运行峰值的跌幅，观察窗口变化会改变该值。",
  },
  etf_scope: {
    title: "ETF / 合计",
    body: "当前行对应选中的单只 ETF。本项目不把其他 ETF 或指数成分数据自动合并进来。",
  },
  date: {
    title: "日期",
    body: "主行情序列中的真实交易日期。补充数据只有日期精确一致时才会合并。",
  },
  daily_change: {
    title: "价格变动",
    body: "相邻真实收盘价计算的日涨跌幅；缺少前一观测时保持为空。",
  },
  turnover_percentile: {
    title: "成交额分位",
    body: "当日成交额在当前 ETF 日线观察窗口内的历史百分位，使用完整有效样本确定性计算。",
  },
  share_change: {
    title: "净份额变动",
    body: "当日交易所总份额减去前一相邻审计交易日总份额，单位为亿份。",
  },
  share_change_percentile: {
    title: "变动绝对值分位",
    body: "当前只有最近最多 7 个份额快照，不足以形成稳定历史分位，因此不计算。",
  },
  net_subscription: {
    title: "净申赎金额",
    body: "份额变化乘价格只能得到估算值，不能等同真实申赎现金流；没有可靠源字段时保持待接入。",
  },
  net_subscription_percentile: {
    title: "净申赎绝对值分位",
    body: "依赖同口径的净申赎金额历史序列，当前没有可审计数据。",
  },
  net_subscription_ratio: {
    title: "净申赎/指数成交额",
    body: "依赖净申赎金额和底层指数成交额两个同日、同口径序列，当前不计算。",
  },
  etf_financing_change: {
    title: "ETF 融资净新增",
    body: "ETF 当日融资余额减去前一相邻审计交易日融资余额，单位为亿元。",
  },
  etf_financing_percentile: {
    title: "ETF 融资分位",
    body: "当前只读取最近最多 7 个真实交易日，样本不足以计算历史分位。",
  },
  constituent_financing_change: {
    title: "成分融资净新增",
    body: "需要先精确确认底层指数和当期成分，再逐证券汇总融资余额；当前尚未接入该完整链路。",
  },
  constituent_financing_percentile: {
    title: "成分融资分位",
    body: "依赖完整、可审计的成分股融资历史序列，当前尚未接入。",
  },
};

function MetricHelpDialog({
  helpKey,
  onClose,
}: {
  helpKey: string;
  onClose: () => void;
}) {
  const help = METRIC_HELP[helpKey] ?? {
    title: "指标说明",
    body: "当前指标说明暂不可用。",
  };

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      className="etf-help-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        className="etf-help-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="etf-help-title"
      >
        <header>
          <h2 id="etf-help-title">{help.title}</h2>
          <button
            type="button"
            aria-label="关闭指标说明"
            title="关闭"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </header>
        <p>{help.body}</p>
        <small>缺失值不会被补零、插值或由模型生成。</small>
      </section>
    </div>
  );
}

function sortRows(rows: ETFRecentRow[], sort: TableSort): ETFRecentRow[] {
  return [...rows].sort((left, right) => {
    const leftValue = left[sort.key];
    const rightValue = right[sort.key];
    if (leftValue == null && rightValue == null) {
      return 0;
    }
    if (leftValue == null) {
      return 1;
    }
    if (rightValue == null) {
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

function storedString(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function storedBoolean(key: string, fallback: boolean): boolean {
  const value = storedString(key, String(fallback));
  return value === "true";
}

function storedNumber(
  key: string,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  const parsed = Number(storedString(key, String(fallback)));
  return Number.isFinite(parsed)
    ? Math.min(maximum, Math.max(minimum, parsed))
    : fallback;
}

function storePreference(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Private browsing or storage policies may reject persistence.
  }
}

function panelClientId(): string {
  const storageKey = "fund-advisor.panel.client-id";
  const existing = storedString(storageKey, "");
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(existing)) {
    return existing;
  }
  const generated = crypto.randomUUID();
  storePreference(storageKey, generated);
  return generated;
}

function ETFLoading() {
  return (
    <div className="etf-loading" role="status">
      <span />
      <span />
      <span />
      <strong>正在读取 ETF 审计数据</strong>
      <small>首次查询交易所数据通常需要 10–30 秒</small>
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
