# TASK：数据源交叉校验审计

> 状态：`首个接入完成（S0-S2、S5）`
>
> 下一步：后续按 S3/S4 分别接入 ETF/基金净值和指数点位生产校验；现有 React
> 指数和 ETF 页面已经展示工具返回的 warning。
>
> 目标产物：确认 Baostock、efinance 等免费数据源是否适合作为 AKShare 主源的交叉校验源，
> 并定义接入规则。首个生产闭环只接入默认关闭的 A 股不复权收盘价校验。

## 1. 目标

为市场事实增加“多源差异检测”能力：

```text
主源 AKShare
  + 校验源 Baostock / efinance / 其他候选
  -> 同口径对齐
  -> 差异检测
  -> data_audit / data_warnings
```

多源校验用于发现风险，不用于自动修正数值。数据面板以 Data API/Skill 为事实入口；
Agent 以 Skill/Fund MCP 为事实入口；模型、Go 和前端不得判断哪个源“更正确”。

## 2. 非目标

- 不把多源结果做投票、平均或自动覆盖主源值；
- 不让模型读取原始多源数据后生成市场数值；
- 不在 Go BFF、React 或 Agent 中实现数据源选择逻辑；
- 不为了多源校验引入数据库、Redis、任务队列或长期快照；
- 不接入付费、积分受限或授权不清晰的数据源作为默认依赖；
- 不绕过现有 Skill/MCP 审计链路直接供页面使用。

## 3. 候选数据源

| 数据源 | 初始定位 | 主要候选用途 | 风险 |
| --- | --- | --- | --- |
| AKShare | 主源 | 当前市场事实入口 | 覆盖广，但接口来自多个上游，字段可能漂移 |
| Baostock | A 股校验源 | A 股日线、复权价格、部分财务字段 | 覆盖基金/指数估值不足，实时性弱 |
| efinance | 东财系校验源 | 股票/ETF/基金行情和部分基金数据 | 依赖上游网页/接口，字段稳定性需审计 |
| 官方/交易所/巨潮/中证 | 权威核验源 | 少量关键字段或接口审计 | 接口不统一，不适合第一版大规模调用 |
| Tushare | 候选后续 | 标准化行情/财务 | 免费额度和积分限制，不作为默认依赖 |

第一阶段只审计 Baostock 与 efinance。其他源仅记录可行性，不接入代码。

## 4. 适合校验的数据

优先校验原始序列，再由本项目确定性函数计算派生指标。

| 数据 | 第一阶段处理 |
| --- | --- |
| A 股前复权/后复权/不复权价格 | AKShare vs Baostock/efinance，必须明确复权口径 |
| ETF 历史价格、成交量 | AKShare vs efinance |
| 基金单位净值/累计净值 | AKShare vs efinance，必须区分净值口径 |
| 指数点位 | AKShare vs 可用校验源，先审计代码映射 |
| 指数/个股 PE、PB | 只审计口径可比性，不直接默认比较 |

不直接跨源比较：

- 历史分位；
- 收益率；
- 波动率；
- 最大回撤；
- 水下期；
- 估值参考线。

这些指标继续由 Skill 使用同一条已审计序列确定性计算。

## 5. 输出语义

第一阶段不改 `ToolEnvelope` 顶层 Schema，使用现有字段承载：

- `data_audit`：记录每个数据源接口、参数、字段、行数、数据日期和 `frame_sha256`；
- `data_warnings`：记录跨源差异、缺失、过期和口径不可比；
- `data_policy`：继续保持 `ai_may_generate_market_data=false`。

建议 warning 结构：

```json
{
  "code": "SOURCE_DISAGREE",
  "field": "close",
  "primary_source": "akshare",
  "check_source": "baostock",
  "entity": "600519",
  "date": "2026-08-14",
  "primary_value": 123.45,
  "check_value": 123.46,
  "tolerance": "0.1%",
  "metric_basis": "qfq_close"
}
```

初始 warning code：

| code | 含义 |
| --- | --- |
| `SOURCE_UNAVAILABLE` | 校验源接口不可用或未覆盖该实体 |
| `SOURCE_STALE` | 校验源最新日期落后于主源 |
| `SOURCE_SCHEMA_CHANGED` | 校验源字段或类型不符合审计契约 |
| `SOURCE_BASIS_MISMATCH` | 复权、净值、估值或日期口径不可比 |
| `SOURCE_DISAGREE` | 同口径字段超过容忍阈值 |

这些 warning 不改变主结果 `ok`，除非主源本身失败。校验源失败不能让可用的主源事实变成
不存在。

## 6. 实施顺序

### S0：接口与许可审计

主要文件：

```text
skills/akshare-fund-advisor/references/
skills/akshare-fund-advisor/scripts/
```

- [x] 确认 Baostock、efinance 的安装方式、许可证、版本锁定方式。
- [x] 记录每个候选接口的函数签名、参数、返回字段、日期字段和更新频率。
- [x] 对代表性标的做真实调用：
  - A 股：`600519`、`000001`、`300750`；
  - ETF：`510300`、`159915`；
  - 场外基金：`000001`、`110022`；
  - 指数：沪深 300、中证 500、创业板 50。
- [x] 记录失败、限流、字段漂移、日期覆盖和缺失场景。
- [x] 生成 `references/source_cross_validation.md` 审计报告。

### S1：Provider 边界设计

- [x] 在 Skill 层定义数据源 Provider 边界，不暴露给 MCP/Agent/Go 选择。
- [x] 主源 Provider 与校验 Provider 分离。
- [x] Provider 输出必须包含：
  - `source_name`
  - `interface`
  - `parameters`
  - `columns`
  - `as_of`
  - `metric_basis`
  - 原始 DataFrame 指纹
- [x] 不改变现有公开 CLI/MCP 输出，除非同步更新 Schema、测试和文档。

### S2：A 股价格校验

- [x] 选取一个小范围函数，对 A 股日线价格做 AKShare vs Baostock/efinance 对齐。
- [x] 明确复权口径：前复权、后复权或不复权不能混比。
- [x] 日期按交易日交集比较，不做前向填充。
- [x] 容忍阈值由代码常量定义，不能由模型生成。
- [x] 差异进入 `data_warnings`，主源值不被覆盖。
- [x] 增加固定夹具单元测试和至少一次真实接口冒烟。

### S3：ETF 与基金净值校验

- [ ] ETF 历史价格优先校验收盘价、成交量和日期。
- [ ] 基金净值区分单位净值、累计净值、估算净值和货币基金收益。
- [ ] 不同净值口径只输出 `SOURCE_BASIS_MISMATCH`，不比较数值大小。
- [ ] LOF/ETF 备用源切换仍按现有错误语义，不因校验源存在而自动替代。

### S4：指数点位与估值口径审计

- [x] 审计可用校验源的指数代码、指数名称和日期映射。
- [ ] 指数点位可同口径比较时再纳入差异检测。
- [ ] PE/PB 必须区分：
  - TTM vs 静态；
  - 加权 vs 等权；
  - 均值 vs 中位数；
  - 指数口径 vs 成分股横截面口径。
- [ ] 口径不完全一致时只记录不可比，不输出 `SOURCE_DISAGREE`。

### S5：MCP 与 Agent 展示

- [x] Fund MCP 只透传 Skill 产生的多源 audit/warning，不做比较。
- [x] Agent FactRef 仍只绑定主源事实字段；校验源只能作为 warning/限制。
- [x] 响应中可以说明“校验源存在差异/不可用”，不能声明某源一定正确。
- [x] Go BFF 原样透传 warning，不参与源选择或修正。
- [x] React 在指数列表/详情和 ETF 详情展示工具 warning。

## 7. 接入原则

- 默认只把 AKShare 作为主源；其他源先作为可选校验源。
- 校验源必须可关闭，避免上游不稳定拖垮主分析。
- 校验源失败不改变主源错误语义。
- 差异阈值必须按字段和口径显式定义。
- 所有多源接口必须记录 `frame_sha256` 或等价内容指纹。
- 任一新增依赖必须同步 Docker、requirements、版本锁定和测试。

## 8. Definition of Done

### 审计完成

- [x] `source_cross_validation.md` 记录候选源覆盖范围、字段、口径、失败和许可证。
- [x] 至少完成 A 股价格、ETF 价格、基金净值、指数点位四类代表性调用。
- [x] 明确哪些字段可比、哪些不可比、哪些暂不接入。

### 首个代码接入完成

- [x] 只在 Skill 层新增 Provider/Comparator。
- [x] 主源事实值不被校验源覆盖。
- [x] 差异通过 `data_warnings` 输出，审计通过 `data_audit` 输出。
- [x] 固定夹具测试覆盖一致、缺失、过期、字段漂移和超阈值差异。
- [x] Docker Python 测试通过。
- [x] 真实接口冒烟通过，失败时错误语义可区分。

### 全链路验收

- [x] MCP `ToolEnvelope` 保留多源 audit/warning。
- [x] Agent 不把校验源 warning 写成市场事实。
- [x] Go BFF 透传 warning，不修正或重算数字。
- [x] React 在已接入的指数和 ETF 页面展示 warning。
- [x] 文档同步 `ERROR_HANDLING.md`、Skill references 和本任务状态。
