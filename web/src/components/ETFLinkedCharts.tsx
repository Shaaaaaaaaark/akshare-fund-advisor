import * as echarts from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { ETFDashboardData } from "../types";

interface ETFLinkedChartsProps {
  charts: ETFDashboardData["charts"];
  startDate: string;
  endDate: string;
  darkMode: boolean;
  showTooltip: boolean;
}

const PANELS = [
  { key: "price", title: "日线价格走势", color: "#2563eb", type: "line" },
  { key: "turnover", title: "日度 ETF 成交额", color: "#6b8fdc", type: "bar" },
  { key: "volume", title: "日度 ETF 成交量", color: "#118a74", type: "bar" },
  { key: "daily_change", title: "日度价格变动", color: "#c64949", type: "bar" },
  { key: "drawdown", title: "观察窗口回撤", color: "#b7791f", type: "line" },
] as const;

export default function ETFLinkedCharts({
  charts,
  startDate,
  endDate,
  darkMode,
  showTooltip,
}: ETFLinkedChartsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const option = useMemo(
    () => buildOption(charts, startDate, endDate, darkMode, showTooltip),
    [charts, darkMode, endDate, showTooltip, startDate],
  );

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const chart = echarts.init(container, undefined, { renderer: "canvas" });
    chart.setOption(option, { notMerge: true });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [option]);

  return (
    <div
      ref={containerRef}
      className="etf-linked-charts"
      role="img"
      aria-label="ETF 价格、成交额、成交量、涨跌幅和回撤五联图"
    />
  );
}

function buildOption(
  charts: ETFDashboardData["charts"],
  startDate: string,
  endDate: string,
  darkMode: boolean,
  showTooltip: boolean,
): echarts.EChartsOption {
  const palette = darkMode
    ? {
      background: "#151a23",
      text: "#dce3ec",
      muted: "#9aa4b2",
      line: "#303949",
      split: "#252d3a",
      tooltip: "rgba(21, 26, 35, 0.97)",
      zoom: "#1e2633",
    }
    : {
      background: "#ffffff",
      text: "#303846",
      muted: "#87909e",
      line: "#d9dee6",
      split: "#edf0f4",
      tooltip: "rgba(255, 255, 255, 0.96)",
      zoom: "#f0f4f7",
    };
  const panelHeight = 15;
  const panelGap = 4;
  const firstTop = 4;
  const xAxis: echarts.XAXisComponentOption[] = [];
  const yAxis: echarts.YAXisComponentOption[] = [];
  const grid: echarts.GridComponentOption[] = [];
  const titles: echarts.TitleComponentOption[] = [];
  const series: echarts.SeriesOption[] = [];

  PANELS.forEach((panel, index) => {
    const metric = charts[panel.key];
    const top = firstTop + index * (panelHeight + panelGap);
    const data = metric.chart_series.filter(
      ([date]) =>
        (!startDate || date >= startDate) && (!endDate || date <= endDate),
    );
    grid.push({
      left: 58,
      right: 22,
      top: `${top}%`,
      height: `${panelHeight}%`,
    });
    titles.push({
      text: panel.title,
      subtext: `${metric.source_observations} 个真实观测 · ${metric.unit}`,
      left: 12,
      top: `${Math.max(top - 2.2, 0)}%`,
      textStyle: {
        color: palette.text,
        fontSize: 12,
        fontWeight: 650,
      },
      subtextStyle: {
        color: palette.muted,
        fontSize: 9,
      },
    });
    xAxis.push({
      type: "time",
      gridIndex: index,
      axisLabel: {
        color: palette.muted,
        fontSize: 9,
        formatter: "{yyyy}-{MM}",
      },
      axisLine: { lineStyle: { color: palette.line } },
      axisTick: { show: false },
      splitLine: { show: false },
    });
    yAxis.push({
      type: "value",
      gridIndex: index,
      scale: true,
      axisLabel: { color: palette.muted, fontSize: 9 },
      splitLine: { lineStyle: { color: palette.split } },
    });
    series.push({
      name: panel.title,
      type: panel.type,
      xAxisIndex: index,
      yAxisIndex: index,
      data,
      showSymbol: false,
      symbolSize: 5,
      lineStyle: { width: 1.5, color: panel.color },
      itemStyle: { color: panel.color },
      areaStyle:
        panel.key === "drawdown"
          ? { color: "rgba(183, 121, 31, 0.10)" }
          : undefined,
      barMaxWidth: 8,
      sampling: "lttb",
      emphasis: { focus: "series" },
    } as echarts.SeriesOption);
  });

  return {
    animation: false,
    backgroundColor: palette.background,
    title: titles,
    grid,
    axisPointer: {
      link: [{ xAxisIndex: "all" }],
      label: { backgroundColor: "#394150" },
    },
    tooltip: {
      show: showTooltip,
      trigger: "axis",
      axisPointer: { type: "cross" },
      borderColor: palette.line,
      backgroundColor: palette.tooltip,
      textStyle: { color: palette.text, fontSize: 10 },
    },
    xAxis,
    yAxis,
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0, 1, 2, 3, 4],
        filterMode: "none",
      },
      {
        type: "slider",
        xAxisIndex: [0, 1, 2, 3, 4],
        bottom: 8,
        height: 22,
        borderColor: palette.line,
        backgroundColor: palette.zoom,
        fillerColor: "rgba(37, 99, 235, 0.16)",
        handleStyle: { color: "#2563eb" },
        textStyle: { color: palette.muted, fontSize: 9 },
      },
    ],
    visualMap: {
      show: false,
      seriesIndex: 3,
      dimension: 1,
      pieces: [
        { gt: 0, color: "#c64949" },
        { lte: 0, color: "#118a74" },
      ],
    },
    series,
  };
}
