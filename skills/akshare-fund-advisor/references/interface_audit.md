# AKShare 接口审计

审计版本：`akshare==1.18.64`

审计原则：

- 只调用真实接口，不使用 Mock、示例行情或硬编码市场数据。
- 对照 AKShare 安装包源码核对函数签名、上游来源、参数和返回列。
- 每次运行重新检查 Schema，并记录参数、行数、列名和 DataFrame SHA-256。
- 接口失败如实记录；失败不等于零值、停牌、暂停申购或无行情。

## 源码契约

| 接口 | 上游 | 已验证输入 | 关键输出 |
| --- | --- | --- | --- |
| `fund_name_em` | 东方财富 | 无 | 基金代码、简称、类型、拼音 |
| `fund_purchase_em` | 东方财富 | 无 | 申购/赎回状态、净值报告时间、起购额、限额、手续费 |
| `fund_info_ths` | 同花顺 | `symbol=基金代码` | 字段、值；额外核对返回基金代码 |
| `fund_open_fund_info_em` | 东方财富 | `symbol`、`indicator`、`period` | 单位净值、累计净值或七日年化收益率 |
| `fund_individual_detail_hold_xq` | 雪球基金 | 基金代码、报告日期 | 股票、债券、现金等资产仓位 |
| `fund_portfolio_hold_em` | 东方财富 | 基金代码、年份 | 定期报告股票持仓及占净值比例 |
| `fund_etf_spot_em` | 东方财富 | 无 | ETF 价格、IOPV、原始折价率、成交额和更新时间 |
| `fund_etf_hist_em` | 东方财富 | ETF 代码、日频、日期、复权 | ETF OHLC、成交量额、涨跌幅 |
| `fund_etf_hist_sina` | 新浪 | 带 `sh/sz` 前缀 ETF 代码 | 未复权 ETF OHLC、成交量额 |
| `fund_lof_hist_em` | 东方财富 | LOF 代码、日频、日期、复权 | LOF OHLC、成交量额、涨跌幅 |
| `tool_trade_date_hist_sina` | 新浪 | 无 | `trade_date` |
| `stock_index_pe_lg` | 乐咕乐股 | 文档枚举内指数名称 | 加权/等权静态与滚动 PE |
| `stock_index_pb_lg` | 乐咕乐股 | 文档枚举内指数名称 | 加权/等权 PB 与 PB 中位数 |
| `stock_info_a_code_name` | AKShare 聚合目录 | 无 | A 股代码和名称 |
| `stock_zh_valuation_baidu` | 百度股市通 | 股票代码、指标、周期 | 日期和 PE TTM 或 PB 值 |
| `stock_zh_a_daily` | 新浪财经 | 市场前缀代码、日期区间、前复权 | A 股前复权 OHLC 和成交量 |

## 口径确认

- 指数 PE 使用 AKShare 输出列 `滚动市盈率`，对应滚动 PE，不使用静态 PE 或等权 PE。
- 指数 PB 使用 AKShare 输出列 `市净率`，不使用 `等权市净率`。
- 个股 PE 使用 `市盈率(TTM)`，PB 使用 `市净率`，两者分别统计，禁止生成综合分位。
- 个股价格使用 `stock_zh_a_daily(adjust="qfq")` 的前复权收盘价，与估值序列使用独立纵轴。
- ETF 溢价不直接相信列名方向，统一按 `(最新价 - IOPV) / IOPV * 100` 计算；原始 `基金折价率` 同时保留。
- 场内 ETF 使用 `fund_etf_hist_em`；LOF 使用 `fund_lof_hist_em`，两者不混用。
- ETF 东财历史接口失败时，可使用文档明确提供的 `fund_etf_hist_sina`，并把口径改为“新浪未复权收盘价”。
- LOF 东财历史接口失败时只能明确降级为基金净值口径，不调用 ETF 专用接口冒充 LOF 行情。
- 累计净值不是可成交价格，因此不生成虚拟定投收益。
- 资产配置和持仓集中度仅代表报告期，不解释为实时仓位。
- 所有时间序列都禁止插值和前向填充。

## 历史审计记录（非当前结论）

以下记录仅用于说明一次真实运行中观察到的上游状态，不能代表当前接口健康度。

历史审计日期：2026-07-21

代表输入：

```text
基金：000001
ETF：510300
LOF：166009
指数：沪深300
```

当时结果：

| 状态 | 数量 | 说明 |
| --- | ---: | --- |
| 通过 | 14 | 基金目录、代码存在性、申购状态、基金资料、单位/累计净值、ETF 东财/新浪历史、ETF 实时、交易日历、指数 PE/PB |
| 失败 | 1 | `fund_lof_hist_em` 被东方财富上游断开连接 |

失败原因为：

```text
Connection aborted: Remote end closed connection without response
```

该次运行说明：

- 函数签名和字段契约正确。
- `fund_etf_hist_em(510300)` 在本次运行通过，而 `fund_lof_hist_em(166009)` 失败，符合上游接口可用性波动而非 ETF/LOF 参数混用的特征。
- `checks`、`summary` 和 `data_audit` 都将 LOF 失败记为失败，没有把可选包装结果误报为通过。
- 生产回答必须查看本次请求的 `data_audit` 和 `data_warnings`，不能引用旧审计快照替代实时查询。

获取当前状态必须重新运行：

```bash
bash "$SKILL_DIR/scripts/run.sh" audit
```

`checks`、`summary` 和 `data_audit` 使用同一失败语义：可选包装接口返回 `null` 时，对应审计检查也必须标记为 `failed`，不能因异常被降级处理而误报通过。

## 强制失败条件

以下任一情况必须停止生成数值结论：

- AKShare 版本不是 `1.18.64`。
- 返回值不是 DataFrame。
- 缺少约定字段或出现重复列名。
- 必需接口返回空数据。
- 同一日期存在不同数值。
- 最新日期无效、来自未来或超过允许时效。
- 基金详情返回代码与请求代码不一致。
- 指数名称只能模糊匹配到其他子指数。

缺失值允许剔除，但必须在 `data_quality.invalid_rows_dropped` 中披露。模型不得补齐任何缺失值。
