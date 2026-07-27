# AKShare 基金接口映射

本文只记录 Skill 实际使用的接口和口径。AKShare 版本固定为 `1.18.64`，上游网站变更时应重新做真实数据冒烟测试。

官方文档：

- [AKShare 数据字典](https://akshare.akfamily.xyz/)
- [AKShare 公募基金数据](https://akshare.akfamily.xyz/data/fund/fund_public.html)

## 接口

| 用途 | AKShare 接口 | Skill 行为 |
| --- | --- | --- |
| 名称和代码搜索 | `fund_name_em()` | 搜索基金代码、简称、拼音缩写和拼音全称 |
| 申购赎回状态 | `fund_purchase_em()` | 读取申购状态、赎回状态、下一开放日、起购额、限额和手续费 |
| 基金基本资料 | `fund_info_ths()` | 读取投资类型、经理、费率、规模和业绩比较基准 |
| 资产配置 | `fund_individual_detail_hold_xq()` | 读取报告期股票、债券、现金等仓位比例 |
| 股票持仓 | `fund_portfolio_hold_em()` | 读取报告期持仓并计算前十大集中度；接口失败时明确缺失 |
| 开放式基金历史 | `fund_open_fund_info_em()` | 普通基金优先使用累计净值，货币基金使用七日年化收益率 |
| ETF 实时行情 | `fund_etf_spot_em()` | 读取价格、IOPV、成交额、买一和卖一，并自行统一溢价方向 |
| ETF 历史行情 | `fund_etf_hist_em()` | ETF 专用东财接口，使用前复权日收盘价 |
| ETF 历史备用 | `fund_etf_hist_sina()` | 东财接口失败时使用新浪未复权日行情，并单独标注口径 |
| LOF 历史行情 | `fund_lof_hist_em()` | LOF 必须使用专用接口，不能误用 ETF 接口 |
| 宽基指数 PE | `stock_index_pe_lg()` | 对能可靠匹配的宽基指数计算滚动市盈率历史分位 |
| 宽基指数 PB | `stock_index_pb_lg()` | 对能可靠匹配的宽基指数计算市净率历史分位 |
| A 股代码名称 | `stock_info_a_code_name()` | 精确解析沪深 A 股代码和名称，名称多匹配时拒绝自动选择 |
| A 股历史估值 | `stock_zh_valuation_baidu()` | 分别读取个股历史 PE TTM 和 PB，不计算综合估值 |
| A 股历史价格 | `stock_zh_a_daily()` | 读取新浪前复权日收盘价，与 PE/PB 使用独立纵轴 |
| 交易日历 | `tool_trade_date_hist_sina()` | 判断是否交易日；再按沪深市场标准日间时段判断 |

指数历史估值图另见 [valuation_chart.md](valuation_chart.md)。该功能只使用 AKShare 的指数 PE/PB 接口。

## 已验证签名

```python
fund_name_em()
fund_purchase_em()
fund_info_ths(symbol="000001")
fund_individual_detail_hold_xq(symbol="000001", date="20260331")
fund_portfolio_hold_em(symbol="000001", date="2026")
fund_open_fund_info_em(
    symbol="000001",
    indicator="累计净值走势",
    period="成立来",
)
fund_etf_spot_em()
fund_etf_hist_em(
    symbol="513500",
    period="daily",
    start_date="20230101",
    end_date="20261231",
    adjust="qfq",
)
fund_etf_hist_sina(symbol="sh510300")
fund_lof_hist_em(
    symbol="166009",
    period="daily",
    start_date="20230101",
    end_date="20261231",
    adjust="qfq",
)
tool_trade_date_hist_sina()
stock_index_pe_lg(symbol="沪深300")
stock_index_pb_lg(symbol="沪深300")
stock_info_a_code_name()
stock_zh_valuation_baidu(
    symbol="600519",
    indicator="市盈率(TTM)",
    period="近十年",
)
stock_zh_valuation_baidu(
    symbol="600519",
    indicator="市净率",
    period="近十年",
)
stock_zh_a_daily(
    symbol="sh600519",
    start_date="20160101",
    end_date="20261231",
    adjust="qfq",
)
```

`fund_open_fund_info_em()` 的 `period` 只影响部分指标。当前版本获取单位净值或累计净值时可能仍返回成立以来全部数据，所以脚本按日期自行裁剪观察窗口。

## 关键字段

### `fund_purchase_em`

```text
基金代码
基金简称
基金类型
最新净值/万份收益
最新净值/万份收益-报告时间
申购状态
赎回状态
下一开放日
购买起点
日累计限定金额
手续费
```

注意：

- `开放申购`、`开放赎回` 表示业务状态，不代表按当前看到的净值成交。
- `暂停大额申购`、`限额` 等状态表示限额内可能仍可提交，具体额度以源字段和销售平台为准。
- `场内交易` 需要证券账户，并按交易所撮合规则处理。
- 场内输出的 `standard_market_open_now` 只表示交易日和标准时段；`can_buy_now`、`can_sell_now` 保持 `null`，因为脚本不能确认停牌、账户权限或券商通道。
- 很大的 `日累计限定金额` 可能是上游“未显示有效限额”的占位值。脚本保留 `source_daily_limit_cny`，同时将 `daily_limit_cny` 置空。
- 报告时间有时只有月日，脚本不擅自补年份。

### `fund_etf_spot_em`

```text
代码
名称
最新价
IOPV实时估值
基金折价率
涨跌幅
成交额
换手率
买一
卖一
数据日期
更新时间
```

Skill 不直接用原始“基金折价率”判断方向，统一计算：

```text
premium_rate_pct = (latest_price - iopv) / iopv * 100
```

因此：

- 正数表示溢价。
- 负数表示折价。
- IOPV 缺失或非正数时不计算。

## 指标口径

| 输出字段 | 计算方式 | 限制 |
| --- | --- | --- |
| `returns_pct` | 最新值相对目标月份之前最近一个观测值的变化 | 不等于投资者账户实际收益 |
| `current_drawdown_pct` | 最新值相对观察期内历史峰值的回撤 | 受观察窗口影响 |
| `max_drawdown_pct` | 观察期内最小的 `value / running_peak - 1` | 历史最差不代表未来最差 |
| `annualized_volatility_pct` | 日收益标准差乘 `sqrt(250)` | 不适合数据过少的基金 |
| `holding_experience.annualized_return_pct` | 首尾值按实际天数折算复合年化收益 | 强依赖观察区间 |
| `holding_experience.downside_volatility_pct` | 负日收益平方均值开方后年化 | 只衡量下行波动 |
| `holding_experience.max_drawdown_detail` | 最大回撤峰值、谷值和修复日期 | 未修复时恢复日期为空 |
| `holding_experience.longest_underwater_days` | 低于历史高点的最长日历时间 | 衡量持有耐心要求 |
| `holding_experience.monthly_return_statistics` | 月度正收益比例、最好和最差月份 | 不预测未来月份 |
| `holding_experience.rolling_250_observation_return_statistics` | 滚动250个日频观测的收益分布 | 近似一年，不是自然年 |
| `history_position_percentile` | 当前值在观察期所有净值/价格观测中的百分位 | 不是估值分位 |
| `index_valuation.pe_ttm.percentile` | 当前指数滚动 PE 在观察期的位置 | 只适用于成功匹配的指数 |
| `index_valuation.pb.percentile` | 当前指数 PB 在观察期的位置 | 只适用于成功匹配的指数 |
| `trend` | 最新值、20 日均值和 60 日均值的简单关系 | 只是描述，不是预测 |
| `charts.pe_ttm.chart_series` | AKShare `滚动市盈率`历史序列 | 对应 PE TTM，不使用静态或等权 PE |
| `charts.pb.chart_series` | AKShare `市净率`历史序列 | 不使用等权市净率 |
| `charts.stock_price.chart_series` | 新浪 A 股前复权日收盘价 | 仅用于历史可比，不代表当时实际成交价 |
| `reference_lines` | 均值、中位数、±1σ、20/80 分位 | 所有统计均使用完整日频样本 |

普通场外基金优先使用累计净值，场内基金优先使用前复权收盘价。两种口径不同，比较时必须检查 `metric_basis`。

不生成定投收益回测：累计净值不是可成交价格，前复权收盘价也不是投资者每期真实成交记录。定投部分只输出明确标记为策略规则的动作区间。

## 严格数据契约

运行：

```bash
bash "$SKILL_DIR/scripts/run.sh" audit
```

每个成功 AKShare 接口必须产生 `data_audit`：

```text
interface
parameters
row_count
columns
required_columns
frame_sha256
validation=passed
skill_transform_at_ingestion=none
received_from_provider=AKShare DataFrame
```

`frame_sha256` 是规范化 DataFrame 内容指纹，不是 HTTP 原始响应字节哈希。

规则：

- AKShare 版本严格锁定为 `1.18.64`，版本不一致立即失败。
- 缺少约定字段、返回空数据、返回非 DataFrame 或重复列名立即失败。
- 同一日期出现不同值立即失败，不自动选取、平均或覆盖。
- 数值和日期解析失败的行可以剔除，但必须在 `data_quality` 中给出数量。
- 不插值、不前向填充。
- 所有派生指标由脚本确定性计算并标注公式，模型不得修改。
- ETF/LOF 东财历史接口可能被上游主动断开；失败必须进入错误或警告，不得构造行情补齐。
- ETF 可回退到文档明确提供的 `fund_etf_hist_sina`，但必须把口径改为新浪未复权收盘价；LOF 不得借用 ETF 接口。
- 指数匹配要求基金名称或业绩基准紧跟 `ETF/LOF/指数/联接/增强/收益率` 等边界；“沪深300非银”等子指数不得误配为沪深300。

派生公式由输出中的 `derived_formulas` 固定声明：

```text
区间收益 = (最新值 / 目标日期前最近观测值 - 1) * 100
当前回撤 = (最新值 / 运行峰值 - 1) * 100
最大回撤 = min(观测值 / 运行峰值 - 1) * 100
年化波动 = 日收益率样本标准差 * sqrt(250) * 100
历史分位 = 小于等于当前值的观测数 / 总观测数 * 100
场内溢价 = (最新价 - IOPV) / IOPV * 100
```

## 高低位和定投口径

主判断按以下优先级：

1. 能匹配到宽基指数时，优先使用指数 PE/PB 估值分位。
2. 无法匹配时，只使用基金历史净值/价格位置，并降低置信度。
3. 再结合趋势、当前回撤、最大回撤和场内溢价修正。

定投动作只分为：

| 动作 | 解释 |
| --- | --- |
| `base_contribution` | 按用户可持续预算执行基础定投 |
| `base_contribution_no_valuation_signal` | 无可靠估值时按预算和目标仓位执行基础定投 |
| `reduced_contribution_or_wait` | 估值高位或仓位偏高时减量或等待 |
| `pause_current_exchange_venue` | ETF 场内溢价明显时暂停该渠道 |
| `base_or_modest_tilt` | 长期低估、逻辑未变且仓位不足时只做小幅倾斜 |
| `base_contribution_keep_reserve` | 低位但趋势仍弱，维持基础额并保留现金 |

约束：

- 历史净值/价格位置不是估值，只能用于描述。
- 低位但趋势向下时，不把下跌自动解释成加仓机会。
- ETF 可用场内溢价率超过 `5%` 时，暂停当前场内渠道并比较场外份额或等待溢价回落；等于 `5%` 不触发该硬阈值。
- 不输出固定金额倍数；金额必须结合预算、目标仓位和最大可承受回撤。

## 失败语义

AKShare 聚合公开网页，接口可能因网络、反爬或上游改版失败：

- 必需接口失败：脚本返回 `ok=false` 和 `DATA_SOURCE_ERROR`。
- 可选接口失败：主结果继续返回，并在 `data_warnings` 中说明缺失影响。
- `FundAdvisor` 已初始化后发生失败时，错误响应仍保留已收集的 `sources`、`data_audit`、`data_warnings` 和 `data_policy`。
- 接口失败永远不等于“暂停申购”“暂停赎回”“休市”或“价格为零”。
