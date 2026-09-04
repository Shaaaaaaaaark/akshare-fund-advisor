import { X } from "lucide-react";
import { useEffect } from "react";

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
    title: "ETF 融资余额变动",
    body: "ETF 当日融资余额减去前一相邻审计交易日融资余额，单位为亿元。",
  },
  etf_financing_percentile: {
    title: "ETF 融资分位",
    body: "当前只读取最近最多 7 个真实交易日，样本不足以计算历史分位。",
  },
  constituent_financing_change: {
    title: "成分融资余额变动",
    body: "仅在 ETF 精确映射到底层指数时，按中证指数官网最新成份快照汇总沪深交易所逐证券融资余额，再与前一相邻审计交易日比较。未在交易所明细中返回的证券不补零。",
  },
  constituent_financing_percentile: {
    title: "成分融资分位",
    body: "当前只读取最近最多 7 个真实交易日，样本不足以形成稳定历史分位。",
  },
};

export default function ETFMetricHelpDialog({
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
