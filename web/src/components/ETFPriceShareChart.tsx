import * as echarts from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { ETFDashboardChart, ETFSupplementalData } from "../types";

interface ETFPriceShareChartProps {
  price: ETFDashboardChart;
  supplemental: ETFSupplementalData;
  darkMode: boolean;
}

const UI_FONT_FAMILY =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';

export default function ETFPriceShareChart({
  price,
  supplemental,
  darkMode,
}: ETFPriceShareChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const option = useMemo(
    () => buildOption(price, supplemental, darkMode),
    [darkMode, price, supplemental],
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
      className="etf-price-share-chart"
      role="img"
      aria-label="ETF 价格与交易所总份额融合图"
    />
  );
}

function buildOption(
  price: ETFDashboardChart,
  supplemental: ETFSupplementalData,
  darkMode: boolean,
): echarts.EChartsOption {
  const palette = darkMode
    ? {
      background: "#151a23",
      text: "#dce3ec",
      muted: "#9aa4b2",
      line: "#303949",
      split: "#252d3a",
      tooltip: "rgba(21, 26, 35, 0.97)",
    }
    : {
      background: "#ffffff",
      text: "#303846",
      muted: "#687180",
      line: "#d9dee6",
      split: "#edf0f4",
      tooltip: "rgba(255, 255, 255, 0.97)",
    };
  const shareSeries = supplemental.share.chart_series;
  const firstDate = shareSeries[0]?.[0];
  const lastDate = shareSeries.at(-1)?.[0];
  const priceSeries = price.chart_series.filter(
    ([date]) =>
      (!firstDate || date >= firstDate) && (!lastDate || date <= lastDate),
  );

  return {
    animation: false,
    backgroundColor: palette.background,
    textStyle: { fontFamily: UI_FONT_FAMILY },
    grid: { left: 56, right: 64, top: 42, bottom: 38 },
    legend: {
      top: 10,
      textStyle: {
        color: palette.text,
        fontFamily: UI_FONT_FAMILY,
        fontSize: 11,
      },
    },
    tooltip: {
      trigger: "axis",
      borderColor: palette.line,
      backgroundColor: palette.tooltip,
      textStyle: {
        color: palette.text,
        fontFamily: UI_FONT_FAMILY,
        fontSize: 10,
      },
    },
    xAxis: {
      type: "time",
      axisLabel: { color: palette.muted, fontSize: 10 },
      axisLine: { lineStyle: { color: palette.line } },
    },
    yAxis: [
      {
        type: "value",
        name: "价格 / 元",
        scale: true,
        nameTextStyle: { color: palette.muted, fontSize: 10 },
        axisLabel: { color: palette.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: palette.split } },
      },
      {
        type: "value",
        name: "总份额 / 亿份",
        scale: true,
        nameTextStyle: { color: palette.muted, fontSize: 10 },
        axisLabel: { color: palette.muted, fontSize: 10 },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "ETF 价格",
        type: "line",
        yAxisIndex: 0,
        data: priceSeries,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: "#2563eb" },
        itemStyle: { color: "#2563eb" },
      },
      {
        name: "交易所总份额",
        type: "line",
        yAxisIndex: 1,
        data: shareSeries,
        showSymbol: true,
        symbolSize: 6,
        lineStyle: { width: 2, color: "#118a74" },
        itemStyle: { color: "#118a74" },
      },
    ],
  };
}
