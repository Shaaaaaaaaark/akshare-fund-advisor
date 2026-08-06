# LangGraph 金融数据分析 Agent 低层设计

> 项目定位：面向面试展示可信 Agent 工程；功能聚焦基金、指数和个股数据分析，供个人研究参考。

## 1. 实现状态

### 1.1 已实现

| 能力 | 位置 |
| --- | --- |
| AKShare 数据查询、实体解析和确定性指标 | `skills/akshare-fund-advisor/scripts/fund_advisor.py` |
| Skill CLI 与运行环境 | `skills/akshare-fund-advisor/scripts/` |
| 强类型配置 | `src/fund_advisor_mcp/config.py` |
| Fund MCP Schema / Adapter / Server | `src/fund_advisor_mcp/fund/` |
| Web MCP Schema / Client / Service / Server | `src/fund_advisor_mcp/web/` |
| LangGraph 固定状态图、FactRef、门禁和 CLI | `src/fund_advisor_agent/` |
| Skill 单元测试 | `skills/akshare-fund-advisor/tests/` |
| MCP、Web 与 LangGraph 图级测试 | `tests/` |

### 1.2 验证状态

- 根目录 Ruff 通过；
- 81 个 Skill、MCP、Web、候选接口审计和 LangGraph 测试通过；
- Fund MCP 九工具与 Web MCP 三工具的 stdio 发现通过；
- 最近一次真实 AKShare 审计 13/15 通过，`fund_etf_hist_em` 和 `fund_lof_hist_em`
  上游断连被正确记录为 `DATA_SOURCE_ERROR`；
- 真实 LangGraph → MCP → Skill 指数估值闭环通过；
- 普通基金、ETF、宽基指数和 A 股代表性真实冒烟通过；
- Compose 配置、runtime/test 镜像构建和容器内 Ruff/Pytest 通过；
- 两个 MCP 服务健康检查和 HTTP 9+3 工具发现通过；
- 容器内 LangGraph → HTTP MCP → Skill 指数估值闭环通过；
- OpenAI-compatible Ark thinking 模型的 Pydantic 结构化关联输出和门禁闭环通过。

### 1.3 当前非目标

当前不实现 FastAPI/Web UI、数据库、长期会话、组合分析和回测。

## 2. 当前代码结构

```text
akshare-fund-advisor/
├── src/                          # 仓库级源码根
│   ├── fund_advisor_mcp/
│   │   ├── config.py
│   │   ├── fund/
│   │   │   ├── schemas.py
│   │   │   ├── adapter.py
│   │   │   ├── client.py
│   │   │   ├── cache.py
│   │   │   ├── skill_loader.py
│   │   │   └── server.py
│   │   └── web/
│   │       ├── schemas.py
│   │       ├── client.py
│   │       ├── service.py
│   │       └── server.py
│   └── fund_advisor_agent/
│       ├── state.py
│       ├── graph.py
│       ├── nodes.py
│       ├── clients.py
│       ├── policies.py
│       ├── associations.py
│       ├── validator.py
│       ├── renderer.py
│       ├── model_client.py
│       ├── prompts.py
│       └── cli.py
├── skills/akshare-fund-advisor/  # 纯数据层：SKILL.md + scripts + references
│   ├── scripts/
│   │   ├── fund_advisor.py
│   │   ├── run.sh
│   │   └── setup.sh
│   ├── references/
│   ├── tests/
│   ├── SKILL.md
│   ├── DESIGN.md
│   └── USAGE.md
└── tests/                        # MCP、Web 与 LangGraph 图级测试
```

依赖方向：

```text
LangGraph Agent
  -> MCP Client
     -> Fund MCP Adapter -> FundAdvisor
     -> Web MCP Service

FundAdvisor 不依赖 Agent、MCP 或模型。
```

## 3. Skill 数据处理

### 3.1 命令和方法

| 能力 | Skill 方法 | CLI |
| --- | --- | --- |
| 基金搜索 | `search` | `search` |
| 申赎/交易状态 | `status` | `status` |
| 基金分析 | `analyze` | `analyze` |
| 基金档案 | `profile` | `profile` |
| 基金评级 | `rating` | `rating` |
| 指数估值 | `valuation` | `valuation` |
| 个股估值 | `stock_valuation` | 由 MCP 暴露 |
| 基金比较 | `compare` | `compare` |
| 接口审计 | `audit` | `audit` |

### 3.2 统一接口校验

所有 AKShare DataFrame 通过统一调用层处理：

1. 验证返回类型；
2. 拒绝重复列；
3. 校验必需字段；
4. 处理允许或禁止的空表；
5. 规范化日期和数值；
6. 计算 `frame_sha256`；
7. 记录来源、参数、字段、行数和警告；
8. 区分必需接口失败和可选接口降级。

禁止插值、前向填充或跨标的补数。

### 3.3 确定性指标

```text
区间收益 = (latest / prior - 1) * 100
日收益 = value_t / value_t-1 - 1
年化波动 = sample_std(daily_return, ddof=1) * sqrt(250) * 100
下行波动 = sqrt(mean(min(daily_return, 0)^2)) * sqrt(250) * 100
回撤 = (value / running_max - 1) * 100
历史分位 = count(value <= current) / count(value) * 100
ETF 溢价 = (price - IOPV) / IOPV * 100
```

所有公式和舍入口径写入 `references/`，模型不参与计算。

## 4. Fund Advisor MCP

### 4.1 工具集合

| Tool | 输入 Schema |
| --- | --- |
| `fund_search` | `query`, `limit` |
| `fund_status` | `fund` |
| `fund_analyze` | `fund`, `years ∈ {1,3,5}` |
| `fund_profile` | `fund` |
| `fund_rating` | `fund` |
| `index_valuation` | `index`, `years ∈ {3,5,10,20}`, `max_points` |
| `stock_valuation` | `stock`, `years ∈ {1,3,5,10}`, `max_points` |
| `fund_compare` | 2–5 个 `funds`, `years` |
| `interface_audit` | 代表性基金、ETF、LOF、指数 |

### 4.2 ToolEnvelope

```text
schema_version
request_id
tool
ok
data
sources
data_audit
data_warnings
data_policy
queried_at
error
```

Adapter 的职责：

- 用 Pydantic 校验参数；
- 调用 Skill；
- 应用超时、缓存和并发限制；
- 将 Skill 结果封装为 `ToolEnvelope`；
- 原样保留 `sources`、`data_audit`、`data_warnings` 和 `data_policy`。

Adapter 不重算或修改任何金融值。

### 4.3 缓存

缓存只保存完整成功信封。TTL 按数据变化速度区分：

- 搜索、档案、评级：小时级；
- 状态：分钟级；
- 分析、估值、比较：约 30 分钟；
- 接口审计：不使用结果缓存。

缓存键包含工具名、契约版本和规范化参数哈希。

当前阶段只保留进程内缓存。`cache.py` 不包含 Redis 后端，部署也不要求 Redis 服务。

## 5. Web Research MCP

### 5.1 工具

- `web_search`：多供应商搜索；
- `web_fetch`：读取 HTML、文本和 Markdown；
- `document_read`：读取用户给定的 HTML、文本或 PDF URL。

### 5.2 安全边界

- 只允许公网 HTTP/HTTPS；
- 禁止 URL 用户凭证；
- DNS 解析后拒绝本机、私网、链路本地和保留地址；
- 每次重定向重新校验；
- 限制响应大小、正文长度、内容类型和重定向次数；
- 可配置域名 allowlist；
- PDF 使用受限解析；
- 所有返回固定 `numeric_allowed=false`。

### 5.3 搜索降级

默认供应商顺序：

```text
serper -> tavily -> google_cse -> brave -> serpapi
```

只调用配置了凭证的供应商。认证、限流、5xx、无效响应和 `httpx.HTTPError` 都应记录
attempt，并尝试下一个供应商；正常的空结果不是失败。

## 6. 基金数据分析输出

`fund_analyze.analysis` 已稳定为以下逻辑分组：

```text
identity
product_profile
performance
holding_experience
valuation
trading_context
data_quality
```

`product_profile`、`performance`、`valuation`、`trading_context` 和 `data_quality`
均包含 `metric_basis`、`as_of`、精简 `data_audit` 引用和分组 `warnings`。旧顶层字段
继续保留以兼容现有调用方。

### 6.1 `identity`

- 基金代码和名称；
- 产品类型；
- 场内/场外身份；
- 跟踪标的或业绩基准。

### 6.2 `performance`

- 1、3、6、12 个月区间收益；
- 年化收益（仅作为观察区间历史统计）；
- 年化波动、下行波动；
- 当前和最大回撤。

### 6.3 `holding_experience`

- 最大回撤峰值、谷值和修复日期；
- 最长水下天数；
- 月度正收益比例；
- 最好和最差月份；
- 滚动 250 个观测期收益分布。

### 6.4 `valuation`

只有精确解析跟踪指数时才提供：

- PE TTM 当前值和历史分位；
- PB 当前值和历史分位；
- 观察区间和数据日期。

无法可靠匹配时保持 unavailable，不用基金净值位置替代。

### 6.5 `trading_context`

- 场外申购、赎回和限额；
- ETF 最新价格、IOPV 和溢价；
- LOF/ETF/普通基金历史序列口径。

### 6.6 产品评级和比较表

- `fund_rating` 按基金代码精确匹配，可用时并入 `product_profile`；
- 未收录或上游失败时保持缺失并写入覆盖说明，不用其他基金评级替代；
- `fund_compare.comparison_table` 并列展示收益、回撤、波动、费率、评级和资产配置；
- 只有类型、份额、指标口径和基准均一致时才生成排序视图，缺失值不按零排序。

## 7. 指数和个股分析输出

### 7.1 指数

PE TTM 与 PB 各自包含：

- 当前值；
- 历史分位；
- 均值、中位数、P20、P80；
- 图表序列；
- 数据日期和样本量。

两者不得合成总分。

### 7.2 个股

个股分别返回：

- PE TTM 历史；
- PB 历史；
- 前复权价格历史；
- 每条序列的数据日期和可用性。

价格、PE、PB 只能并列展示和关联说明，不能互相替代。

## 8. 最小 LangGraph Agent 设计

### 8.1 框架边界

第一版直接使用 LangGraph `StateGraph`，不使用 LangChain AgentExecutor、开放式 ReAct、
LangChain Tool 包装、长期 Memory 或数据库 checkpoint。

LangGraph 只负责：

- 节点注册和固定边；
- 条件路由；
- `AgentState` 的显式传递；
- 图级路径测试。

业务真实性仍由 MCP、Skill 和代码门禁负责。LangGraph 本身不判断金融事实是否可信。

依赖策略：

- 只安装并锁定验证过的 LangGraph 1.x 版本；
- 不直接依赖 `langchain` 聚合包；
- `langchain-core` 只有在 LangGraph 或模型消息接口确实需要时才保留；
- 首版只接一个模型供应商，不引入 LiteLLM 路由层。

### 8.2 AgentState

`AgentState` 使用 Pydantic 定义，节点返回状态增量，不原地修改共享对象：

```text
question
intent
entities
tool_plan
tool_results
facts
associations
limitations
warnings
errors
status
final_answer
```

`status` 只允许：

```text
running
need_clarification
not_found
unsupported
cannot_confirm
stale_data
partial_result
completed
failed
```

第一版图编译时不传 checkpointer，不保存长期会话、用户画像或跨请求 Memory。

### 8.3 固定状态图

```text
START
  -> CLASSIFY
  -> PLAN_REGISTERED_TOOLS
  -> CALL_MCP
  -> VALIDATE_TOOL_ENVELOPES
  -> BUILD_ASSOCIATIONS
  -> VALIDATE_RESPONSE
  -> RENDER_ANSWER
  -> END
```

节点职责：

| 节点 | 职责 | 模型参与 |
| --- | --- | --- |
| `CLASSIFY` | 规则优先识别意图和实体候选 | 仅低置信度时允许结构化补充 |
| `PLAN_REGISTERED_TOOLS` | 按代码白名单生成工具计划 | 否 |
| `CALL_MCP` | 通过 MCP Client 执行工具 | 否 |
| `VALIDATE_TOOL_ENVELOPES` | 校验成功、审计、时效、错误和 Web 数据策略 | 否 |
| `BUILD_ASSOCIATIONS` | 基于允许的事实引用生成非因果关联草稿 | 是 |
| `VALIDATE_RESPONSE` | 校验引用、数字、因果词和禁止指令 | 否 |
| `RENDER_ANSWER` | 从事实引用确定性注入数值、单位和日期 | 否 |

图保持无环，不在节点间运行自治反思或无限重试。

### 8.4 条件边和终止状态

`VALIDATE_TOOL_ENVELOPES` 后只允许以下路由：

| 工具语义 | 图状态 | 输出 |
| --- | --- | --- |
| 成功且审计通过 | `running` | 继续构建关联 |
| 成功但存在非关键 warning | `partial_result` | 带限制继续 |
| `AMBIGUOUS` | `need_clarification` | 返回候选并结束 |
| `NOT_FOUND` | `not_found` | 明确未找到并结束 |
| `UNSUPPORTED` | `unsupported` | 说明能力边界并结束 |
| `UPSTREAM_ERROR` | `cannot_confirm` | 当前无法确认并结束 |
| `STALE_DATA` | `stale_data` | 数据过期，不生成当前判断 |

模型不能设置 `status`，条件边只读取代码节点产生的枚举。

### 8.5 意图与工具白名单

| 意图 | 工具 |
| --- | --- |
| 基金搜索 | `fund_search` |
| 基金分析 | `fund_analyze` + 两次可选 `web_search` |
| 基金状态 | `fund_status` |
| 基金比较 | `fund_compare` |
| 指数估值 | `index_valuation` |
| 个股估值 | `stock_valuation` + 两次可选 `web_search` |
| 网页背景 | `web_search` |
| 指定文档 | `document_read` |

工具计划由代码枚举生成并裁剪。`fund_profile`、`fund_rating`、`interface_audit` 和
`web_fetch` 已在 MCP/工具枚举中注册，但当前固定意图路由不自动调用。模型不能创建工具名、
修改工具参数 Schema 或把 Web 工具替换为市场事实工具。

单标分析的两条 Web 查询由代码固定构造：一条面向研究报告和财经媒体，一条面向雪球、
知乎等博主/社区公开观点。二者均为 `required=false`，在 `CALL_MCP` 中受并发上限约束。
Web 失败产生 `partial_result`；必需的市场工具失败仍按其原始错误语义终止。

### 8.6 事实引用和关联 Schema

`VALIDATE_TOOL_ENVELOPES` 将允许使用的字段转换为稳定引用：

```text
FactRef
  fact_id
  tool
  field_path
  value
  unit
  as_of
  audit_ref
  source_kind        # market | entity | background
```

模型只接收必要的 `FactRef` 和非数值解释元数据，输出：

```text
AssociationDraft
  evidence_refs      # 至少两个 fact_id
  relationship       # co_occurrence | contrast | consistency | data_limit
  explanation
  causal_claim=false
  confidence         # high | medium | low
```

`confidence` 只描述数据完整性和口径一致性，不表示未来收益概率。`explanation` 不允许写入
任何未出现在 `FactRef` 中的金融数字。

### 8.7 模型客户端

定义项目内 `AssociationModel` Protocol，业务节点不直接依赖供应商 SDK：

```text
build_associations(facts, question) -> list[AssociationDraft]
```

首版要求：

- 只配置一个 OpenAI-compatible 模型客户端；
- 使用 Pydantic 结构化输出；
- Prompt 和输出 Schema 版本化；
- 超时或结构化输出失败时回退为无关联说明的确定性事实报告；
- 测试使用 Fake Model，不访问真实模型；
- 只有出现两个以上模型供应商时才评估 LiteLLM。

### 8.8 关联规则示例

```text
基金股票仓位较高 + 历史波动较高
  -> 可说明两项风险特征同时存在
  -> 不得说明股票仓位必然导致历史波动

指数 PE 高分位 + PB 中位
  -> 说明盈利估值与净资产估值给出不同历史位置
  -> 禁止平均为综合分

ETF 溢价上升 + 场内价格上涨
  -> 提示场内执行风险
  -> 不得说明基金净值必然回落

个股价格高位 + PE 高分位
  -> 描述价格和盈利估值都处于各自历史较高位置
  -> 不预测后续涨跌
```

### 8.9 输出校验与渲染

第一版不恢复复杂 Evidence/Claim 平台，但必须实现确定性门禁：

- 市场数值必须逐项来自成功且审计通过的 `FactRef`；
- 渲染器从引用注入数值、单位和日期，模型文本不能新增数字；
- Web 数字不能进入市场事实；
- Web 背景只确定性展示标题、链接、域名和来源类别；分类不表示身份认证；
- association 至少引用两个存在的事实字段；
- association 不得包含确定性因果词；
- 错误终止状态使用固定模板，不调用模型改写错误语义；
- 不输出确定性买卖指令；
- 响应校验失败时返回 `failed`，不返回未校验草稿。

### 8.10 运行入口

第一版只提供 CLI，不增加 FastAPI：

```text
fund-advisor-agent ask --question "分析 510300 的风险和估值"
```

CLI 创建一次图实例，执行单轮 `ainvoke`，输出结构化 JSON 和用户可读文本。

## 9. 错误处理

错误按三层传播：

```text
Skill AdvisorError
  -> MCP ToolError
  -> VALIDATE_TOOL_ENVELOPES
  -> LangGraph 条件边
  -> 固定用户表达
```

LangGraph 节点不吞掉工具错误，也不把失败转换为空值或实体不存在。详细错误码见
[ERROR_HANDLING.md](ERROR_HANDLING.md)。

## 10. 测试

### 10.1 当前测试

- Skill：实体解析、接口契约、指标公式、降级和审计；
- Fund MCP：参数校验、缓存、超时和审计透传；
- Web MCP：供应商降级、SSRF、重定向、HTML/PDF 抽取。

### 10.2 LangGraph Agent 测试

- 主要 Pydantic Schema 的未知字段、未知工具和 `causal_claim` 约束；
- 规则意图、低置信度结构化意图补充和工具白名单；
- 成功路径、部分结果路径和五类错误终止状态；
- 固定节点集合且不配置 checkpointer；
- 市场数值逐项来自 FactRef，并绑定到对应接口审计哈希；
- Web 数值不能升级为市场事实；
- 单标分析的文章/博主双查询、链接渲染和可选搜索失败降级；
- PE/PB 单侧缺失不互相替代；
- 缺少审计、无效引用、模型数字、因果表达和交易指令被阻断；
- 模型超时回退为确定性事实报告；
- Fake MCP 下的完整成功和错误图路径。

## 11. 后续按需验证

更换模型端点、模型 ID 或 thinking 参数后，重新执行 Pydantic 结构化输出冒烟。

财务、行业和基金质量候选接口已通过独立 discovery audit 盘点，但尚未进入生产
`INTERFACE_CONTRACTS`、MCP Tool 或 Agent Intent。复现脚本：

```text
skills/akshare-fund-advisor/scripts/audit_quality_interfaces.py
```

接口分级和后续接入任务见：

- [候选接口审计](../skills/akshare-fund-advisor/references/quality_interface_audit.md)
- [候选筛选任务](tasks/TASK_asset_screening.md)

实现明细见 [TASK_langgraph_agent.md](tasks/TASK_langgraph_agent.md)。
