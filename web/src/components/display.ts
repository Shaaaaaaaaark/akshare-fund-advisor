export function displayNumber(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : String(value);
}

export function displayPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${String(value)}%`;
}

export function levelLabel(level: string | null | undefined): string {
  const labels: Record<string, string> = {
    low: "偏低",
    lower_middle: "中低",
    middle: "中位",
    upper_middle: "中高",
    high: "偏高",
  };
  return level ? (labels[level] ?? level) : "无数据";
}

export function warningText(
  warning: Record<string, unknown> | string,
): string {
  if (typeof warning === "string") {
    return warning;
  }
  const code =
    typeof warning.code === "string" ? warning.code : "DATA_WARNING";
  const message =
    typeof warning.message === "string" ? warning.message : null;
  return message ? `${code}：${message}` : code;
}
