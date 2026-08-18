import type { DataStatus } from "../types";

const LABELS: Record<DataStatus, string> = {
  available: "可用",
  partial: "部分可用",
  stale: "已过期",
  unavailable: "不可用",
  not_implemented: "未实现",
};

export default function StatusBadge({ status }: { status: DataStatus }) {
  return (
    <span className={`data-status data-status-${status}`}>
      <i aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}
