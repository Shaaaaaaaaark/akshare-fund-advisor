# AKShare 基金参考咨询 Skill 使用说明

## 1. 环境要求

- macOS 或 Linux。
- Python 3.9 到 3.12。
- 可访问 AKShare 对应公开上游。

Skill 固定使用 `akshare==1.18.64`，并锁定当前验证过的 pandas、NumPy、requests 和 curl_cffi 关键运行版本。脚本检测到 Python 不在 3.9 到 3.12、关键包版本不符或依赖无法导入时会停止运行，避免字段错位或残缺环境直接崩溃。

## 2. 安装

进入 Skill 所在工作区后，将目录保存为环境变量：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
bash "$SKILL_DIR/scripts/setup.sh"
```

默认虚拟环境位于 `$SKILL_DIR/.venv`。需要放到其他位置时：

```bash
export AKSHARE_FUND_VENV="/absolute/path/to/venv"
bash "$SKILL_DIR/scripts/setup.sh"
```

检查命令入口：

```bash
bash "$SKILL_DIR/scripts/run.sh" --help
```

## 3. 命令总览

```text
search      按代码、名称或拼音搜索
status      查询申购、赎回或场内标准时段
analyze     分析历史位置、风险、估值和定投条件
valuation   生成指数历史 PE/PB 图表数据
audit       调用真实接口检查 Schema 和数据指纹
compare     比较 2 到 5 只基金
```

所有结果输出为 JSON。不要从终端提示文本或模型记忆补齐缺失字段。

## 4. 搜索基金

```bash
bash "$SKILL_DIR/scripts/run.sh" search \
  --query "纳斯达克" \
  --limit 10
```

`search` 可能返回 A/C 类、ETF、联接基金或不同币种份额。出现多个结果时，应使用明确代码继续，不能自动选择。

## 5. 分析单只基金

```bash
bash "$SKILL_DIR/scripts/run.sh" analyze \
  --fund "513500" \
  --years 3
```

`--years` 支持 `1`、`3`、`5`，默认 `3`。

重点字段：

| 字段 | 含义 |
| --- | --- |
| `fund_profile` | 基金类型、经理、基准、费用和规模原文 |
| `metrics` | 收益、波动、回撤、历史位置和持有体验 |
| `metric_basis` | 累计净值、单位净值或场内收盘价口径 |
| `index_valuation` | 可精确匹配宽基时的 10 年 PE/PB 摘要 |
| `market_snapshot` | ETF 价格、IOPV 和溢价 |
| `portfolio_snapshot` | 报告期资产配置和股票集中度 |
| `decision_reference` | 条件式买入和卖出参考 |
| `dca_plan` | 基础、减量、等待或暂停渠道等规则 |
| `metric_coverage` | 已取得和可靠缺失的指标 |

`history_position_percentile` 是基金净值或价格位置，不是估值。只有 `index_valuation.pe_ttm.percentile` 和 `index_valuation.pb.percentile` 是匹配指数的估值分位。

## 6. 查询执行状态

```bash
bash "$SKILL_DIR/scripts/run.sh" status --fund "510300"
```

场外基金重点查看：

```text
availability.off_exchange.subscription_status
availability.off_exchange.redemption_status
availability.off_exchange.can_submit_subscription
availability.off_exchange.can_submit_redemption
availability.off_exchange.daily_limit_cny
```

“暂停大额申购”表示仍可能允许限额内提交，因此 `can_submit_subscription` 可为 `true`，具体金额以源限额和销售平台为准。

场内基金重点查看：

```text
availability.exchange.market_session
availability.exchange.standard_market_open_now
availability.exchange.can_submit_standard_session_order
```

`can_buy_now` 和 `can_sell_now` 固定保持 `null`。脚本只能判断交易日和标准时段，不能确认停牌、券商通道、账户权限、流动性或最小交易单位。

## 7. 指数历史估值

仅使用 AKShare：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "沪深300" \
  --years 10 \
  --max-points 600
```

参数：

| 参数 | 可选值 |
| --- | --- |
| `--years` | `3`、`5`、`10`、`20` |
| `--max-points` | `50` 到 `3000` |

指数名称必须精确，并且必须存在 AKShare PE/PB 映射。支持的别名和代码由脚本 `INDEX_ALIASES`、`INDEX_CATALOG` 定义；“沪深300非银行金融”不会模糊映射成“沪深300”。

关键字段：

```text
actual_source.provider
actual_source.available_metrics
charts.pe_ttm
charts.pb
charts.<metric>.window_statistics
charts.<metric>.chart_series
```

只有一侧估值通过时，另一侧为 `null`。调用方应先判空，再读取 `chart_series`。完整 3/5/10/20 年分位位于 `window_statistics`；`analyze.index_valuation` 不包含多窗口统计。

PE 使用 `stock_index_pe_lg` 的 `滚动市盈率`，PB 使用 `stock_index_pb_lg` 的 `市净率`。不得改用静态 PE、等权 PE 或等权 PB。`actual_source.provider` 固定为 `AKShare`，上游来源和具体接口仍应保留在报告中。

## 8. 比较基金

```bash
bash "$SKILL_DIR/scripts/run.sh" compare \
  --funds "000001" "110022" \
  --years 3
```

支持 2 到 5 只基金，也可使用逗号分隔。比较前检查：

- `comparability.same_reported_fund_type`
- `comparability.same_metric_basis`
- 各基金的跟踪标的或业绩基准

不同类型或不同口径不能只按收益率排序。

## 9. 真实接口审计

```bash
bash "$SKILL_DIR/scripts/run.sh" audit
```

也可以指定代表输入：

```bash
bash "$SKILL_DIR/scripts/run.sh" audit \
  --fund "000001" \
  --etf "510300" \
  --lof "166009" \
  --index "沪深300"
```

检查：

- `ok`
- `checks`
- `summary`
- `data_audit`
- `data_warnings`

`audit` 调用真实网络接口，结果受当前网络、反爬和上游状态影响。历史审计记录只能说明当时的状态，不能替代本次运行。

## 10. 通用审计字段

成功和已初始化后的失败响应都可能包含：

```text
queried_at
timezone
akshare_version
sources
data_audit
data_warnings
data_policy
derived_formulas
disclaimer
```

`data_audit[].frame_sha256` 是规范化 DataFrame 内容指纹，不是原始 HTTP 响应哈希。失败调用没有指纹，但会记录 `validation=failed` 和错误信息。

引用任何数值前应确认：

1. `data_policy.ai_may_generate_market_data == false`。
2. 对应接口的 `data_audit.validation == "passed"`。
3. 指标自己的日期和 `latest_age_days` 合格。
4. `data_warnings` 中没有声明该数据不可用于结论。

## 11. 定投规则

当前规则不输出固定金额倍数：

- 无可靠估值时执行基础定投，但先确认产品质量和目标仓位。
- PE TTM 长期高分位时减量或等待。
- PE TTM 低分位但趋势仍弱时保留现金。
- PE TTM 低分位且趋势未继续恶化时只做小幅倾斜。
- 可用 ETF 场内溢价率 `> 5%` 时暂停当前场内渠道。

具体金额需要用户提供每期预算、当前与目标仓位、资金期限、应急资金和最大可承受回撤。

## 12. 常见错误

### `MISSING_DEPENDENCY`

运行：

```bash
bash "$SKILL_DIR/scripts/setup.sh"
```

### `AKSHARE_VERSION_MISMATCH`

删除或更换自定义虚拟环境后重新执行安装。不要直接升级 AKShare。

### `AMBIGUOUS_FUND`

先执行 `search`，再使用唯一基金代码。

### `INDEX_NOT_SUPPORTED`

使用 `INDEX_CATALOG` 中 AKShare 已支持的精确指数名称、别名或代码。不要依赖子串匹配。

### `DATA_SOURCE_ERROR`

当前网络或上游失败。检查 `data_audit` 和 `data_warnings`，稍后重试；不能把失败解释成暂停申购或无行情。

### `STALE_OR_INVALID_DATA`

数据日期未通过时效校验。不要继续生成当前买卖或估值结论。

### `VALUATION_SOURCE_UNAVAILABLE`

AKShare 的 PE/PB 接口均未返回可用数据。检查 `data_audit` 与 `data_warnings` 后再重试。

## 13. 开发验证

```bash
"$SKILL_DIR/.venv/bin/python" -m py_compile \
  "$SKILL_DIR/scripts/fund_advisor.py"

"$SKILL_DIR/.venv/bin/python" -m unittest discover \
  -s "$SKILL_DIR/tests" \
  -v

sh -n "$SKILL_DIR/scripts/run.sh"
sh -n "$SKILL_DIR/scripts/setup.sh"
```

接口或字段发生变化时，更新代码和文档后必须重新运行 `audit`。不得用 Mock 审计结果替代真实接口验证。
