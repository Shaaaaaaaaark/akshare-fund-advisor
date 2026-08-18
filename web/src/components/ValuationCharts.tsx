import * as echarts from "echarts";
import { useEffect, useMemo, useRef } from "react";

import type { ChartMetric } from "../types";

interface ValuationChartsProps {
  pe: ChartMetric | null;
  pb: ChartMetric | null;
}

const REFERENCE_LABELS: Record<string, string> = {
  mean: "均值",
  median: "中位数",
  mean_minus_1_stddev: "均值 -1σ",
  mean_plus_1_stddev: "均值 +1σ",
  p20: "P20",
  p80: "P80",
};

export function ValuationCharts({ pe, pb }: ValuationChartsProps) {
  const metrics = [
    pe ? { title: "PE TTM 历史", color: "#176b54", metric: pe } : null,
    pb ? { title: "PB 历史", color: "#3f63a8", metric: pb } : null,
  ].filter(Boolean) as Array<{
    title: string;
    color: string;
    metric: ChartMetric;
  }>;

  const option = useMemo(() => {
    const dual = metrics.length === 2;
    const grid = metrics.map((_, index) => ({
      left: 62,
      right: 28,
      top: dual ? (index === 0 ? 54 : 320) : 58,
      height: dual ? 190 : 280,
      containLabel: false,
    }));
    const xAxis = metrics.map(({ metric }, index) => ({
      type: "category",
      gridIndex: index,
      boundaryGap: false,
      data: metric.chart_series.map(([date]) => date),
      axisLine: { lineStyle: { color: "#cfd4d0" } },
      axisTick: { show: false },
      axisLabel: {
        color: "#77807c",
        fontSize: 10,
        hideOverlap: true,
        margin: 12,
      },
      axisPointer: { show: true, snap: true },
    }));
    const yAxis = metrics.map(({ metric }, index) => ({
      type: "value",
      gridIndex: index,
      scale: true,
      name: metric.unit,
      nameTextStyle: { color: "#8a928e", fontSize: 10 },
      axisLabel: { color: "#77807c", fontSize: 10 },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: "#eceeeb", type: "dashed" } },
    }));

    return {
      animation: false,
      title: metrics.map(({ title }, index) => ({
        text: title,
        left: 16,
        top: dual ? (index === 0 ? 8 : 274) : 10,
        textStyle: {
          color: "#27302c",
          fontSize: 13,
          fontWeight: 650,
        },
      })),
      grid,
      xAxis,
      yAxis,
      axisPointer: {
        link: [{ xAxisIndex: metrics.map((_, index) => index) }],
        lineStyle: { color: "#82918a", width: 1 },
      },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "rgba(29, 35, 32, 0.94)",
        borderWidth: 0,
        textStyle: { color: "#f4f6f4", fontSize: 11 },
      },
      dataZoom: [
        {
          type: "inside",
          xAxisIndex: metrics.map((_, index) => index),
          filterMode: "none",
        },
        {
          type: "slider",
          xAxisIndex: metrics.map((_, index) => index),
          filterMode: "none",
          bottom: 8,
          height: 18,
          borderColor: "#d7dbd7",
          backgroundColor: "#f1f2ef",
          fillerColor: "rgba(23, 107, 84, 0.13)",
          handleStyle: { color: "#176b54" },
          textStyle: { color: "#737b77", fontSize: 9 },
        },
      ],
      series: metrics.map(({ metric, color }, index) => ({
        name: metric.metric,
        type: "line",
        xAxisIndex: index,
        yAxisIndex: index,
        data: metric.chart_series.map(([, value]) => value),
        showSymbol: false,
        connectNulls: false,
        lineStyle: { color, width: 1.7 },
        itemStyle: { color },
        emphasis: { focus: "series" },
        markPoint: {
          symbol: "circle",
          symbolSize: 8,
          label: { show: false },
          itemStyle: { color, borderColor: "#ffffff", borderWidth: 2 },
          data:
            metric.chart_series.length > 0
              ? [
                {
                  coord:
                    metric.chart_series[metric.chart_series.length - 1],
                },
              ]
              : [],
        },
        markLine: {
          silent: true,
          symbol: ["none", "none"],
          label: { show: false },
          data: Object.entries(metric.reference_lines)
            .filter(([key]) => key in REFERENCE_LABELS)
            .map(([key, value]) => ({
              name: REFERENCE_LABELS[key],
              yAxis: value,
              lineStyle: {
                color:
                  key === "mean" || key === "median"
                    ? "#79847f"
                    : key === "p20"
                      ? "#46a27e"
                      : key === "p80"
                        ? "#c36e58"
                        : "#c69b47",
                type:
                  key === "mean" || key === "median" ? "dashed" : "dotted",
                width: 1,
                opacity: 0.75,
              },
            })),
        },
      })),
    };
  }, [metrics]);

  if (metrics.length === 0) {
    return null;
  }

  return (
    <EChart
      className="valuation-chart"
      option={option as echarts.EChartsOption}
      height={metrics.length === 2 ? 590 : 400}
      ariaLabel="PE TTM 与 PB 历史估值双图"
    />
  );
}

export function IndexPointChart({ metric }: { metric: ChartMetric }) {
  const option = useMemo(
    () => ({
      animation: false,
      grid: { left: 62, right: 24, top: 30, bottom: 55 },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: "rgba(29, 35, 32, 0.94)",
        borderWidth: 0,
        textStyle: { color: "#f4f6f4", fontSize: 11 },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: metric.chart_series.map(([date]) => date),
        axisLine: { lineStyle: { color: "#cfd4d0" } },
        axisTick: { show: false },
        axisLabel: { color: "#77807c", fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        scale: true,
        name: metric.unit,
        nameTextStyle: { color: "#8a928e", fontSize: 10 },
        axisLabel: { color: "#77807c", fontSize: 10 },
        splitLine: { lineStyle: { color: "#eceeeb", type: "dashed" } },
      },
      dataZoom: [
        { type: "inside", filterMode: "none" },
        {
          type: "slider",
          filterMode: "none",
          bottom: 8,
          height: 18,
          borderColor: "#d7dbd7",
          backgroundColor: "#f1f2ef",
          fillerColor: "rgba(63, 99, 168, 0.12)",
          handleStyle: { color: "#3f63a8" },
          textStyle: { color: "#737b77", fontSize: 9 },
        },
      ],
      series: [
        {
          name: "指数点位",
          type: "line",
          data: metric.chart_series.map(([, value]) => value),
          showSymbol: false,
          connectNulls: false,
          lineStyle: { color: "#3f63a8", width: 1.6 },
          areaStyle: { color: "rgba(63, 99, 168, 0.06)" },
        },
      ],
    }),
    [metric],
  );

  return (
    <EChart
      className="index-point-chart"
      option={option as echarts.EChartsOption}
      height={360}
      ariaLabel="指数点位历史曲线"
    />
  );
}

function EChart({
  option,
  height,
  className,
  ariaLabel,
}: {
  option: echarts.EChartsOption;
  height: number;
  className: string;
  ariaLabel: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const chart = echarts.init(container, undefined, { renderer: "svg" });
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
      className={className}
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", height }}
    />
  );
}
