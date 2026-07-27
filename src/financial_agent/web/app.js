const SVG_NS = "http://www.w3.org/2000/svg";

const elements = {
  form: document.querySelector("#research-form"),
  query: document.querySelector("#query"),
  token: document.querySelector("#api-token"),
  submit: document.querySelector("#submit-button"),
  newConversation: document.querySelector("#new-conversation"),
  conversationList: document.querySelector("#conversation-list"),
  conversationCount: document.querySelector("#conversation-count"),
  conversationTitle: document.querySelector("#conversation-title"),
  state: document.querySelector("#system-state"),
  stateText: document.querySelector("#system-state-text"),
  messageScroll: document.querySelector("#message-scroll"),
  messageList: document.querySelector("#message-list"),
  welcome: document.querySelector("#welcome-card"),
  researchTitle: document.querySelector("#research-title"),
  researchEmpty: document.querySelector("#research-empty"),
  researchLoading: document.querySelector("#research-loading"),
  researchContent: document.querySelector("#research-content"),
  grade: document.querySelector("#evidence-grade"),
  reportSummary: document.querySelector("#report-summary"),
  reportMeta: document.querySelector("#report-meta"),
  valuationCard: document.querySelector("#valuation-card"),
  metricTabs: document.querySelector("#metric-tabs"),
  chartPeriod: document.querySelector("#chart-period"),
  chartEmpty: document.querySelector("#chart-empty"),
  chartContent: document.querySelector("#chart-content"),
  chartStats: document.querySelector("#chart-stats"),
  chart: document.querySelector("#valuation-chart"),
  chartWrap: document.querySelector("#chart-wrap"),
  chartTooltip: document.querySelector("#chart-tooltip"),
  chartSource: document.querySelector("#chart-source"),
  marketPriceLabel: document.querySelector("#market-price-label"),
  factsSection: document.querySelector("#facts-section"),
  facts: document.querySelector("#facts"),
  analysisSection: document.querySelector("#analysis-section"),
  analysis: document.querySelector("#analysis"),
  risksSection: document.querySelector("#risks-section"),
  risks: document.querySelector("#risks"),
  citationsSection: document.querySelector("#citations-section"),
  citations: document.querySelector("#citations"),
  evidenceCount: document.querySelector("#evidence-count"),
  evidenceList: document.querySelector("#evidence-list"),
  disclaimer: document.querySelector("#disclaimer"),
};

const appState = {
  conversations: [],
  conversation: null,
  conversationId: window.localStorage.getItem("finagent.conversation"),
  activeReportId: null,
  valuation: null,
  metric: "pe_ttm",
  busy: false,
};

function authHeaders() {
  const headers = { "Content-Type": "application/json" };
  const token = elements.token.value.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

function readableError(payload, fallback) {
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload.detail === "string") return payload.detail;
  if (payload.detail?.message) return payload.detail.message;
  if (payload.message) return payload.message;
  return fallback;
}

async function api(path, options = {}) {
  const response = await window.fetch(path, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : null;
  if (!response.ok) {
    throw new Error(readableError(payload, `请求失败（HTTP ${response.status}）`));
  }
  return payload;
}

function formatDate(value, withTime = false) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: withTime ? "short" : undefined,
  }).format(parsed);
}

function formatNumber(value, unit = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const number = Number(value);
  const formatted = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: Math.abs(number) >= 100 ? 2 : 3,
  }).format(number);
  return `${formatted}${unit || ""}`;
}

function displayValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function setBusy(busy) {
  appState.busy = busy;
  elements.submit.disabled = busy;
  elements.query.disabled = busy;
}

function scrollMessages() {
  window.requestAnimationFrame(() => {
    elements.messageScroll.scrollTop = elements.messageScroll.scrollHeight;
  });
}

async function loadConversationList() {
  appState.conversations = await api("/v1/conversations");
  elements.conversationCount.textContent = String(appState.conversations.length);
  renderConversationList();
}

function renderConversationList() {
  elements.conversationList.replaceChildren();
  appState.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "conversation-item";
    button.classList.toggle(
      "active",
      conversation.conversation_id === appState.conversationId,
    );

    const title = document.createElement("strong");
    title.textContent = conversation.title;
    const preview = document.createElement("span");
    preview.textContent = conversation.preview;
    button.append(title, preview);
    button.addEventListener("click", () =>
      selectConversation(conversation.conversation_id),
    );
    elements.conversationList.append(button);
  });
}

async function createConversation() {
  const created = await api("/v1/conversations", { method: "POST" });
  await loadConversationList();
  await selectConversation(created.conversation_id);
  elements.query.focus();
}

async function selectConversation(conversationId) {
  appState.conversationId = conversationId;
  appState.activeReportId = null;
  renderValuation(null);
  window.localStorage.setItem("finagent.conversation", conversationId);
  appState.conversation = await api(`/v1/conversations/${conversationId}`);
  elements.conversationTitle.textContent = appState.conversation.title;
  renderConversationList();
  renderMessages();

  const latest = [...appState.conversation.messages]
    .reverse()
    .find((item) => item.role === "assistant" && item.report_id);
  if (latest) {
    await selectReport(latest.report_id, latest.report);
  } else {
    clearResearch();
  }
}

function renderMessages() {
  const messages = appState.conversation?.messages || [];
  elements.welcome.classList.toggle("hidden", messages.length > 0);
  elements.messageList.replaceChildren();
  messages.forEach((message) => {
    const row = document.createElement("article");
    row.className = `message ${message.role}`;

    if (message.role === "assistant") {
      const avatar = document.createElement("span");
      avatar.className = "message-avatar";
      avatar.textContent = "F";
      row.append(avatar);
    }

    const body = document.createElement("div");
    body.className = "message-body";
    if (message.role === "user") {
      body.textContent = message.content;
    } else {
      body.classList.add("assistant-card");
      body.classList.toggle(
        "active",
        message.report_id === appState.activeReportId,
      );
      if (message.report) {
        const meta = document.createElement("div");
        meta.className = "message-report-meta";
        const grade = document.createElement("span");
        grade.className = "message-grade";
        grade.textContent = `证据 ${message.report.evidence_grade}`;
        const status = document.createElement("span");
        status.className = "message-status";
        status.textContent = statusLabel(message.status);
        meta.append(grade, status);
        body.append(meta);
      }
      const content = document.createElement("p");
      content.textContent = message.content;
      body.append(content);
      if (message.report_id) {
        const open = document.createElement("button");
        open.type = "button";
        open.className = "open-report";
        open.textContent = "在右侧查看完整研究数据 →";
        open.addEventListener("click", () =>
          selectReport(message.report_id, message.report),
        );
        body.append(open);
      }
    }
    row.append(body);
    elements.messageList.append(row);
  });
  scrollMessages();
}

function statusLabel(status) {
  return {
    completed: "已完成",
    partial_result: "部分结果",
    cannot_confirm: "无法确认",
    policy_blocked: "策略阻断",
    need_clarification: "需要补充",
    failed: "执行失败",
  }[status] || status;
}

function appendOptimisticMessage(query) {
  elements.welcome.classList.add("hidden");
  const user = document.createElement("article");
  user.className = "message user";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = query;
  user.append(body);

  const assistant = document.createElement("article");
  assistant.className = "message assistant";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = "F";
  const typing = document.createElement("div");
  typing.className = "message-body assistant-card typing-card";
  typing.append(
    document.createElement("span"),
    document.createElement("span"),
    document.createElement("span"),
  );
  assistant.append(avatar, typing);
  elements.messageList.append(user, assistant);
  scrollMessages();
}

function appendLocalError(message) {
  const row = document.createElement("article");
  row.className = "message assistant";
  const avatar = document.createElement("span");
  avatar.className = "message-avatar";
  avatar.textContent = "F";
  const body = document.createElement("div");
  body.className = "message-body assistant-card";
  const content = document.createElement("p");
  content.textContent = message;
  body.append(content);
  row.append(avatar, body);
  elements.messageList.append(row);
  scrollMessages();
}

async function submitResearch(event) {
  event.preventDefault();
  const query = elements.query.value.trim();
  if (!query || appState.busy || !appState.conversationId) return;

  setBusy(true);
  appendOptimisticMessage(query);
  elements.query.value = "";
  resizeComposer();
  try {
    const accepted = await api(
      `/v1/conversations/${appState.conversationId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ content: query }),
      },
    );
    await loadConversationList();
    appState.conversation = await api(
      `/v1/conversations/${appState.conversationId}`,
    );
    elements.conversationTitle.textContent = appState.conversation.title;
    appState.activeReportId = accepted.report_id || null;
    renderMessages();
    if (accepted.report_id) {
      const message = [...appState.conversation.messages]
        .reverse()
        .find((item) => item.report_id === accepted.report_id);
      await selectReport(accepted.report_id, message?.report);
    } else {
      clearResearch();
    }
  } catch (error) {
    renderMessages();
    appendLocalError(error.message || "请求失败，请检查服务状态。");
  } finally {
    setBusy(false);
    elements.query.focus();
  }
}

function clearResearch() {
  appState.activeReportId = null;
  renderValuation(null);
  elements.researchEmpty.classList.remove("hidden");
  elements.researchLoading.classList.add("hidden");
  elements.researchContent.classList.add("hidden");
  elements.grade.classList.add("hidden");
  elements.researchTitle.textContent = "研究面板";
}

async function selectReport(reportId, embeddedReport) {
  const selectedConversation = appState.conversationId;
  appState.activeReportId = reportId;
  renderMessages();
  elements.researchEmpty.classList.add("hidden");
  elements.researchContent.classList.add("hidden");
  elements.researchLoading.classList.remove("hidden");
  try {
    const [report, evidencePayload, currentValuation] = await Promise.all([
      embeddedReport || api(`/v1/reports/${reportId}`),
      api(`/v1/reports/${reportId}/evidence`),
      api(`/v1/reports/${reportId}/valuation-chart`),
    ]);
    if (selectedConversation !== appState.conversationId) return;
    const valuation = currentValuation?.available
      ? currentValuation
      : await findConversationValuation(reportId);
    renderResearch(report, evidencePayload.evidence || [], valuation);
  } catch (error) {
    clearResearch();
    elements.researchEmpty.querySelector("h3").textContent = "研究数据加载失败";
    elements.researchEmpty.querySelector("p").textContent = error.message;
  }
}

async function findConversationValuation(excludedReportId) {
  const messages = [...(appState.conversation?.messages || [])].reverse();
  for (const message of messages) {
    if (
      message.role !== "assistant"
      || !message.report_id
      || message.report_id === excludedReportId
    ) {
      continue;
    }
    const candidate = await api(
      `/v1/reports/${message.report_id}/valuation-chart`,
    );
    if (candidate?.available) {
      return { ...candidate, from_previous_turn: true };
    }
  }
  return null;
}

function renderResearch(report, evidence, valuation) {
  elements.researchLoading.classList.add("hidden");
  elements.researchContent.classList.remove("hidden");
  elements.researchTitle.textContent = report.title;
  elements.grade.classList.remove("hidden");
  elements.grade.textContent = report.evidence_grade;
  elements.grade.dataset.grade = report.evidence_grade;
  elements.reportSummary.textContent = report.summary;
  elements.reportMeta.textContent =
    `${formatDate(report.generated_at, true)} · ${statusLabel(report.status)}`;
  elements.disclaimer.textContent = report.disclaimer;

  renderFacts(report.facts || []);
  const analysis = [
    ...(report.analysis || []),
    ...(report.buy_conditions || []),
    ...(report.sell_or_rebalance_conditions || []),
  ];
  renderList(elements.analysis, elements.analysisSection, analysis);
  const risks = [
    ...(report.risks || []),
    ...(report.missing_information || []),
    ...(report.warnings || []),
  ];
  renderList(elements.risks, elements.risksSection, risks);
  renderCitations(report.citations || []);
  renderEvidence(evidence);
  renderValuation(valuation);
}

function renderFacts(facts) {
  elements.facts.replaceChildren();
  facts.forEach((fact) => {
    const card = document.createElement("div");
    card.className = "fact-card";
    const label = document.createElement("span");
    label.className = "fact-label";
    label.textContent = fact.label;
    const value = document.createElement("strong");
    value.className = "fact-value";
    value.textContent = fact.display_value || displayValue(fact.value);
    const date = document.createElement("span");
    date.className = "fact-date";
    date.textContent = fact.as_of
      ? `数据日期 ${formatDate(fact.as_of)}`
      : "已通过证据校验";
    card.append(label, value, date);
    elements.facts.append(card);
  });
  elements.factsSection.classList.toggle("hidden", facts.length === 0);
}

function renderList(container, section, items) {
  container.replaceChildren();
  items.forEach((text) => {
    const item = document.createElement("li");
    item.textContent = text;
    container.append(item);
  });
  section.classList.toggle("hidden", items.length === 0);
}

function renderCitations(citations) {
  elements.citations.replaceChildren();
  citations.forEach((citation) => {
    const sourceUrl = validSourceUrl(citation.url);
    const item = document.createElement(sourceUrl ? "a" : "div");
    item.className = "citation";
    if (sourceUrl) {
      item.href = sourceUrl;
      item.target = "_blank";
      item.rel = "noopener noreferrer";
    }
    const title = document.createElement("span");
    title.textContent = citation.title;
    const location = document.createElement("span");
    location.textContent = citation.page ? `第 ${citation.page} 页` : "来源";
    item.append(title, location);
    elements.citations.append(item);
  });
  elements.citationsSection.classList.toggle("hidden", citations.length === 0);
}

function validSourceUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function renderEvidence(evidence) {
  elements.evidenceList.replaceChildren();
  elements.evidenceCount.textContent = `${evidence.length} 条`;
  evidence.forEach((record) => {
    const item = document.createElement("div");
    item.className = "evidence-item";
    const field = document.createElement("strong");
    field.textContent = record.field || "未命名字段";
    const type = document.createElement("span");
    type.textContent = record.type || "EVIDENCE";
    const value = document.createElement("div");
    value.className = "evidence-value";
    value.textContent = record.display_value || displayValue(record.value);
    item.append(field, type, value);
    elements.evidenceList.append(item);
  });
}

function renderValuation(payload) {
  if (!payload?.available) {
    appState.valuation = null;
    elements.chartEmpty.classList.remove("hidden");
    elements.chartContent.classList.add("hidden");
    elements.metricTabs.replaceChildren();
    elements.chartPeriod.textContent = "等待唯一标的";
    return;
  }
  appState.valuation = payload;
  elements.chartEmpty.classList.add("hidden");
  elements.chartContent.classList.remove("hidden");

  const available = ["pe_ttm", "pb"].filter(
    (name) => appState.valuation.metrics[name],
  );
  if (!available.length && appState.valuation.metrics.market_price) {
    available.push("market_price");
  }
  if (!available.includes(appState.metric)) appState.metric = available[0];
  elements.metricTabs.replaceChildren();
  available.forEach((name) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent =
      name === "pe_ttm" ? "PE TTM" : name === "pb" ? "PB" : "价格";
    button.classList.toggle("active", name === appState.metric);
    button.addEventListener("click", () => {
      appState.metric = name;
      renderValuation(appState.valuation);
    });
    elements.metricTabs.append(button);
  });

  const lookback = appState.valuation.lookback || {};
  elements.chartPeriod.textContent =
    `${lookback.requested_years || "-"} 年 · 截至 ${lookback.latest_date || "-"}`
    + (appState.valuation.from_previous_turn ? " · 本对话最近标的" : "");
  const source = appState.valuation.source || {};
  elements.chartSource.textContent =
    `数据源：${source.provider || "AKShare"} · ${(
      source.interfaces || []
    ).join(" / ")} · 审计 ${source.audit_hashes?.length || 0} 项`;
  drawValuationChart();
}

function drawValuationChart() {
  const metric = appState.valuation.metrics[appState.metric];
  const points =
    appState.metric === "market_price"
      ? null
      : appState.valuation.metrics.market_price;
  const isStock = appState.valuation.subject_type === "stock";
  elements.marketPriceLabel.textContent = isStock ? "前复权股价" : "指数点位";
  const reference = metric.reference_lines || {};
  renderChartStats(metric, reference);
  elements.chart.replaceChildren();

  const primary = parseSeries(metric.chart_series);
  const secondary = parseSeries(points?.chart_series || []);
  if (!primary.length) return;

  const width = 720;
  const height = 330;
  const margin = { top: 18, right: 54, bottom: 36, left: 47 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const allDates = [...primary, ...secondary].map((item) => item.time);
  let minTime = Math.min(...allDates);
  let maxTime = Math.max(...allDates);
  if (minTime === maxTime) maxTime += 86400000;

  const referenceValues = [reference.opportunity, reference.danger]
    .map(Number)
    .filter(Number.isFinite);
  const primaryValues = [...primary.map((item) => item.value), ...referenceValues];
  const [primaryMin, primaryMax] = paddedDomain(primaryValues);
  const [pointMin, pointMax] = paddedDomain(
    secondary.length ? secondary.map((item) => item.value) : [0, 1],
  );
  const x = (time) =>
    margin.left + ((time - minTime) / (maxTime - minTime)) * plotWidth;
  const y = (value) =>
    margin.top + ((primaryMax - value) / (primaryMax - primaryMin)) * plotHeight;
  const yPoint = (value) =>
    margin.top + ((pointMax - value) / (pointMax - pointMin)) * plotHeight;

  for (let index = 0; index <= 4; index += 1) {
    const yPosition = margin.top + (plotHeight * index) / 4;
    elements.chart.append(
      svgElement("line", {
        x1: margin.left,
        x2: width - margin.right,
        y1: yPosition,
        y2: yPosition,
        class: "chart-grid",
      }),
    );
    const value = primaryMax - ((primaryMax - primaryMin) * index) / 4;
    elements.chart.append(
      svgElement(
        "text",
        {
          x: margin.left - 7,
          y: yPosition + 3,
          "text-anchor": "end",
          class: "chart-axis-label",
        },
        formatNumber(value),
      ),
    );
    if (secondary.length) {
      const pointValue = pointMax - ((pointMax - pointMin) * index) / 4;
      elements.chart.append(
        svgElement(
          "text",
          {
            x: width - margin.right + 7,
            y: yPosition + 3,
            "text-anchor": "start",
            class: "chart-axis-label",
          },
          formatNumber(pointValue),
        ),
      );
    }
  }

  for (let index = 0; index <= 3; index += 1) {
    const time = minTime + ((maxTime - minTime) * index) / 3;
    elements.chart.append(
      svgElement(
        "text",
        {
          x: x(time),
          y: height - 12,
          "text-anchor": index === 0 ? "start" : index === 3 ? "end" : "middle",
          class: "chart-axis-label",
        },
        new Date(time).toISOString().slice(0, 10),
      ),
    );
  }

  addReferenceLine(reference.opportunity, "机会值", "opportunity", y, width, margin);
  addReferenceLine(reference.danger, "危险值", "danger", y, width, margin);
  if (secondary.length) {
    elements.chart.append(
      svgElement("path", {
        d: seriesPath(secondary, x, yPoint),
        class: "chart-points-line",
      }),
    );
  }
  elements.chart.append(
    svgElement("path", {
      d: seriesPath(primary, x, y),
      class: "chart-valuation-line",
    }),
  );

  const crosshair = svgElement("line", {
    y1: margin.top,
    y2: height - margin.bottom,
    class: "chart-crosshair hidden",
  });
  const dot = svgElement("circle", {
    r: 4,
    class: "chart-hover-dot hidden",
  });
  const overlay = svgElement("rect", {
    x: margin.left,
    y: margin.top,
    width: plotWidth,
    height: plotHeight,
    fill: "transparent",
  });
  overlay.addEventListener("mousemove", (event) => {
    const bounds = elements.chart.getBoundingClientRect();
    const svgX = ((event.clientX - bounds.left) / bounds.width) * width;
    const time = minTime + ((svgX - margin.left) / plotWidth) * (maxTime - minTime);
    const nearest = nearestPoint(primary, time);
    const nearestIndex = secondary.length ? nearestPoint(secondary, time) : null;
    const xPosition = x(nearest.time);
    crosshair.setAttribute("x1", xPosition);
    crosshair.setAttribute("x2", xPosition);
    dot.setAttribute("cx", xPosition);
    dot.setAttribute("cy", y(nearest.value));
    crosshair.classList.remove("hidden");
    dot.classList.remove("hidden");
    elements.chartTooltip.classList.remove("hidden");
    elements.chartTooltip.textContent =
      `${nearest.date}\n${metric.metric}: ${formatNumber(nearest.value, metric.unit)}`
      + (nearestIndex
        ? `\n${isStock ? "前复权股价" : "指数点位"}: ${formatNumber(
          nearestIndex.value,
          points.unit,
        )}`
        : "");
    const tooltipX = Math.min(bounds.width - 145, Math.max(4, event.clientX - bounds.left + 10));
    const tooltipY = Math.max(4, event.clientY - bounds.top - 56);
    elements.chartTooltip.style.left = `${tooltipX}px`;
    elements.chartTooltip.style.top = `${tooltipY}px`;
    elements.chartTooltip.style.whiteSpace = "pre-line";
  });
  overlay.addEventListener("mouseleave", () => {
    crosshair.classList.add("hidden");
    dot.classList.add("hidden");
    elements.chartTooltip.classList.add("hidden");
  });
  elements.chart.append(crosshair, dot, overlay);
}

function renderChartStats(metric, reference) {
  const stats = [
    ["当前值", formatNumber(metric.current, metric.unit)],
    ["历史分位", formatNumber(metric.percentile, "%")],
    ["机会值 P20", formatNumber(reference.opportunity, metric.unit)],
    ["危险值 P80", formatNumber(reference.danger, metric.unit)],
  ];
  elements.chartStats.replaceChildren();
  stats.forEach(([label, value]) => {
    const item = document.createElement("div");
    item.className = "chart-stat";
    const caption = document.createElement("span");
    caption.textContent = label;
    const number = document.createElement("strong");
    number.textContent = value;
    item.append(caption, number);
    elements.chartStats.append(item);
  });
}

function parseSeries(series) {
  return (series || [])
    .map(([date, value]) => ({
      date,
      time: new Date(`${date}T00:00:00Z`).getTime(),
      value: Number(value),
    }))
    .filter((item) => Number.isFinite(item.time) && Number.isFinite(item.value))
    .sort((left, right) => left.time - right.time);
}

function paddedDomain(values) {
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) {
    const padding = Math.abs(minimum || 1) * 0.08;
    return [minimum - padding, maximum + padding];
  }
  const padding = (maximum - minimum) * 0.08;
  return [minimum - padding, maximum + padding];
}

function seriesPath(series, x, y) {
  return series
    .map((item, index) => `${index ? "L" : "M"}${x(item.time).toFixed(2)},${y(item.value).toFixed(2)}`)
    .join(" ");
}

function nearestPoint(series, targetTime) {
  return series.reduce((best, item) =>
    Math.abs(item.time - targetTime) < Math.abs(best.time - targetTime)
      ? item
      : best,
  );
}

function addReferenceLine(value, label, className, y, width, margin) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return;
  const yPosition = y(numeric);
  elements.chart.append(
    svgElement("line", {
      x1: margin.left,
      x2: width - margin.right,
      y1: yPosition,
      y2: yPosition,
      class: `chart-reference-line ${className}`,
    }),
    svgElement(
      "text",
      {
        x: width - margin.right - 3,
        y: yPosition - 4,
        "text-anchor": "end",
        class: "chart-axis-label",
      },
      `${label} ${formatNumber(numeric)}`,
    ),
  );
}

function svgElement(name, attributes, text) {
  const element = document.createElementNS(SVG_NS, name);
  Object.entries(attributes).forEach(([key, value]) =>
    element.setAttribute(key, String(value)),
  );
  if (text !== undefined) element.textContent = text;
  return element;
}

function resizeComposer() {
  elements.query.style.height = "auto";
  elements.query.style.height = `${Math.min(elements.query.scrollHeight, 150)}px`;
}

async function checkHealth() {
  try {
    const health = await api("/health/ready");
    const ready = health.status === "ok";
    elements.state.classList.toggle("ready", ready);
    elements.state.classList.toggle("degraded", !ready);
    elements.stateText.textContent = ready ? "服务可用" : "部分服务未就绪";
  } catch {
    elements.state.classList.add("degraded");
    elements.stateText.textContent = "无法连接服务";
  }
}

async function initialize() {
  checkHealth();
  try {
    await loadConversationList();
    const selected = appState.conversations.find(
      (item) => item.conversation_id === appState.conversationId,
    );
    if (selected) {
      await selectConversation(selected.conversation_id);
    } else if (appState.conversations.length) {
      await selectConversation(appState.conversations[0].conversation_id);
    } else {
      await createConversation();
    }
  } catch (error) {
    clearResearch();
    appendLocalError(error.message || "初始化失败，请检查服务状态。");
  }
}

elements.form.addEventListener("submit", submitResearch);
elements.newConversation.addEventListener("click", createConversation);
elements.query.addEventListener("input", resizeComposer);
elements.query.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});
elements.token.addEventListener("change", initialize);
document.querySelectorAll("[data-query]").forEach((button) => {
  button.addEventListener("click", () => {
    elements.query.value = button.dataset.query;
    resizeComposer();
    elements.query.focus();
  });
});

initialize();
