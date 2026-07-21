# AKShare 基金参考咨询 Skill 设计

## 1. 目标与边界

本 Skill 将基金名称或代码转换为可审计的数据查询和规则化参考输出，主要回答：

- 基金是什么产品，是否适合当前投资目标。
- 历史收益、波动、回撤和修复时间如何。
- 可精确匹配宽基指数时，当前 PE TTM/PB LF 位于什么历史位置。
- ETF 场内价格是否存在明显溢价。
- 在预算、仓位和风险约束下，应维持、减量、等待或暂停当前场内渠道。

本 Skill 不执行交易，不预测确定收益，不生成市场数据，也不把基金净值位置解释成估值。

## 2. 系统结构

```text
用户或模型
    |
    v
scripts/run.sh
    |
    v
scripts/fund_advisor.py
    |-- CLI 参数与退出码
    |-- 基金/指数精确解析
    |-- AKShare/Wind 数据适配
    |-- Schema、空值和时效校验
    |-- 确定性指标计算
    |-- 条件式买卖与定投规则
    `-- JSON 输出、审计和警告
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `SKILL.md` | 模型调用顺序、回答格式和禁止事项 |
| `scripts/fund_advisor.py` | CLI、数据访问、校验、指标和策略规则 |
| `scripts/run.sh` | 选择 Skill 虚拟环境并启动 CLI |
| `scripts/setup.sh` | 创建虚拟环境并安装锁定依赖 |
| `tests/test_fund_advisor.py` | 指标、降级、审计和错误输出回归测试 |
| `references/akshare_api.md` | 接口、字段和公式契约 |
| `references/professional_metrics.md` | 专业指标解释 |
| `references/valuation_chart.md` | 指数估值图数据和渲染契约 |
| `references/interface_audit.md` | 真实接口审计方法和历史记录 |
| `USAGE.md` | 独立安装、命令和排错说明 |

## 3. 命令模型

| 命令 | 输入 | 主要输出 |
| --- | --- | --- |
| `search` | 模糊名称、代码或拼音 | 候选基金，不自动选择份额 |
| `status` | 唯一基金名称或代码 | 申赎状态或标准交易时段信息 |
| `analyze` | 唯一基金名称或代码 | 产品、历史指标、估值、溢价和策略规则 |
| `valuation` | 精确指数名称、别名或代码 | PE/PB 历史统计和图表点 |
| `compare` | 2 到 5 只基金 | 各基金独立分析及可比性提示 |
| `audit` | 代表性基金和指数 | 真实接口 Schema 与数据指纹审计 |

所有命令输出 JSON。成功时退出码为 `0`，业务或数据错误时为 `1`，Shell 环境缺失时 `run.sh` 返回非零。

## 4. 数据源与降级

### 4.1 基金数据

基金目录、申赎状态、基本资料、净值、持仓、ETF/LOF 行情和交易日历均来自锁定版本 `akshare==1.18.64`。`requirements.txt` 同时固定当前验证过的 pandas、NumPy、requests 和 curl_cffi 关键运行版本；启动前会校验 Python、AKShare 和 pandas，安装后执行 `pip check`。

场内历史数据按以下顺序处理：

1. 名称明确包含 ETF 时调用 `fund_etf_hist_em`。
2. 东财 ETF 历史接口失败时可降级到 `fund_etf_hist_sina`，口径改为未复权收盘价。
3. 名称明确包含 LOF 时只调用 `fund_lof_hist_em`。
4. LOF 专用接口失败时可降级到基金净值，但不得借用 ETF 接口。

场内身份来自基金名称和源状态，不能因可选的申赎状态接口失败而改变历史指标口径。

### 4.2 指数估值

`valuation --source auto` 的选择顺序：

1. 本机存在 WindPy 时尝试一次 Wind WSD。
2. Wind 连接、权限、超时或数据调用失败时记录失败审计和警告。
3. 指数存在 AKShare 映射时，整次估值查询回退到 AKShare。
4. 指数没有公开映射时返回错误，不拼接其他指数或其他数据源。

单次估值不会把 Wind PE 与 AKShare PB 混在一起。AKShare 的 PE 或 PB 单侧失败时，可展示同一 AKShare 数据源中仍通过校验的一侧。

## 5. 数据完整性

每次 AKShare 调用都经过统一 `_call()`：

1. 校验返回对象是 DataFrame。
2. 拒绝重复列名。
3. 校验接口必需字段。
4. 除明确允许外，拒绝空表。
5. 记录接口、参数、行数、字段和内容指纹。
6. 必需接口失败时抛出 `AdvisorError`。
7. 可选接口失败时返回 `null` 并写入 `data_warnings`。

`frame_sha256` 是对收到的 DataFrame 复制后，将列名和值规范化为字符串，再通过 pandas 行哈希计算的内容指纹。它用于识别本次表格内容，不是 HTTP 原始响应字节哈希，也不是数据商签名。

时间序列规则：

- 同一日期同值可去重。
- 同一日期不同值直接失败。
- 无效日期或数值可以剔除，但必须计数。
- 不插值、不前向填充、不由模型补点。
- PE/PB 和基金历史最新日期最多允许滞后 10 天。
- ETF 即时行情日期最多允许滞后 3 天。
- 交易日历未覆盖查询日期时，不判断当前市场状态。

失败响应在 `FundAdvisor` 已初始化时仍合并 `common_output()`，保留已经产生的 `sources`、`data_audit`、`data_warnings` 和 `data_policy`。

## 6. 指标层

历史序列先统一为按日期升序的 `date/value`，再确定性计算：

```text
区间收益 = (最新值 / 目标日期前最近观测值 - 1) * 100
当前回撤 = (最新值 / 运行峰值 - 1) * 100
最大回撤 = min(观测值 / 运行峰值 - 1) * 100
年化波动 = 日收益率样本标准差 * sqrt(250) * 100
历史分位 = 小于等于当前值的观测数 / 观测数 * 100
ETF 溢价 = (最新价 - IOPV) / IOPV * 100
```

`analyze.index_valuation` 是固定 10 年窗口的摘要。完整 3/5/10/20 年窗口只存在于：

```text
valuation.charts.pe_ttm.window_statistics
valuation.charts.pb_lf.window_statistics
```

PE 与 PB 独立计算，不生成综合分位。只有一侧通过时，另一侧为 `null`。

## 7. 策略层

策略输出标记为 `rule_based_policy_not_market_data`，不属于行情事实：

- PE TTM 高分位：减量或等待。
- PE TTM 低分位且趋势仍弱：维持基础定投并保留现金。
- PE TTM 低分位且趋势未继续恶化：只做小幅估值倾斜。
- 无可靠估值：按产品质量、现金流和目标仓位执行基础定投。
- ETF 可用溢价率 `> 5%`：暂停当前场内渠道，比较场外份额或等待。

具体金额必须由用户预算、目标仓位、资金期限、应急资金和最大可承受回撤决定。脚本不输出机械倍数。

## 8. 错误模型

`AdvisorError` 的稳定结构：

```json
{
  "ok": false,
  "action": "valuation",
  "error": {
    "code": "DATA_SOURCE_ERROR",
    "message": "当前无法确认",
    "details": {}
  }
}
```

常见错误类别：

| 类别 | 含义 |
| --- | --- |
| `INVALID_ARGUMENT` | 参数为空或超出范围 |
| `FUND_NOT_FOUND` / `AMBIGUOUS_FUND` | 基金无法唯一解析 |
| `INDEX_NOT_SUPPORTED` | 指数名称不是精确映射 |
| `DATA_CONTRACT_ERROR` | 返回类型或字段不符合契约 |
| `DATA_SOURCE_ERROR` | AKShare 上游或网络失败 |
| `STALE_OR_INVALID_DATA` | 日期异常或数据过期 |
| `VALUATION_SOURCE_UNAVAILABLE` | Wind 和公开回退均不可用 |

接口失败不能解释为停牌、暂停申购、休市或数值为零。

## 9. 测试策略

单元测试不访问真实网络，覆盖：

- 状态文本和费率解析。
- 收益、回撤、修复时间和估值分位。
- 子指数拒绝和指数精确解析。
- Wind 超时后 auto 回退。
- PE/PB 单侧降级和过期指标隔离。
- ETF 历史口径不依赖申购状态接口。
- 交易日历时效。
- audit 失败计数和错误响应审计字段。

发布或接口升级前还需运行真实 `audit` 和代表性 `search/analyze/valuation` 冒烟测试。真实审计结果会随网络和上游状态变化，不能由单元测试替代。

## 10. 扩展原则

新增接口时必须同时完成：

1. 在 `INTERFACE_CONTRACTS` 声明必需字段。
2. 通过 `_call()` 接入并定义必需或可选语义。
3. 在 `references/akshare_api.md` 记录真实签名和口径。
4. 增加成功、Schema 失败、空数据和降级测试。
5. 用真实 `audit` 验证当前锁定版本。

新增指数映射必须使用精确名称、代码和 Wind 代码。不能通过包含关系把行业、风格或子指数映射成宽基指数。
