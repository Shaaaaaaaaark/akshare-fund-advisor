# 系统架构

## 1. 目标

系统提供可信投研数据工作台和受控研究 Agent，重点展示：

- AKShare 数据接入、口径校验和内容指纹审计；
- MCP 工具契约与错误传播；
- LangGraph 固定流程和模型输出门禁；
- Go 网页后端与 Python 数据/Agent 能力的清晰边界；
- Docker 黑盒可验证的端到端链路。

产品范围见 [PRODUCT.md](PRODUCT.md)。当前实施进度见
[TASK_research_dashboard.md](tasks/TASK_research_dashboard.md)。

## 2. 当前架构

```text
Browser
  |
  v
React Web
  |
  v
Go Web Backend (BFF)                     # 对外唯一 HTTP 入口
  |-- 静态托管 React
  |-- Dashboard API
  |     `-> Data API (Python REST)
  |           `-> AKShare Skill
  |
  `-- Agent SSE 反向代理
        `-> Agent API (Python)
              `-> LangGraph StateGraph
                    |-> Fund MCP -> AKShare Skill
                    `-> Web MCP  -> 公网搜索/页面/文档
```

Compose 当前包含五个服务：

| 服务 | 语言 | 对外端口 | 职责 |
| --- | --- | --- | --- |
| `web-backend` | Go | 是 | BFF、静态托管、Dashboard 取数、SSE 代理 |
| `data-api` | Python | 否 | 数据面板 REST、确定性数据调用和审计透传 |
| `agent-api` | Python | 否 | Agent HTTP/SSE、临时会话 |
| `fund-advisor-mcp` | Python | 否 | 十个市场事实工具 |
| `web-research-mcp` | Python | 否 | 三个非数值背景工具 |

## 3. 两条读取链路

### 3.1 数据工作台链路

```text
React -> Go Dashboard API -> Data API -> Skill
```

- 不调用模型、LangGraph 或 MCP 协议。
- Go 只做有界并发、聚合、状态映射和展示字段选择。
- 市场数字、审计字段和错误码来自 `ToolEnvelope`。
- Go 不重算、四舍五入、插值、补点或合成金融数值。
- 当前 Go BFF 不包含结果缓存、请求去重、业务限流或 TLS 终止。

当前已实现：

```text
GET /api/dashboard/indices
GET /api/dashboard/indices/{index}
GET /api/dashboard/funds/search
GET /api/dashboard/funds/{fund}
```

研究动态页尚未实现；若后续接入，必须先定义独立的非数值 REST 契约，Dashboard 不能
直接调用 Agent MCP，也不能把网页数字升级为市场事实。

### 3.2 Agent 研究链路

```text
React -> Go SSE proxy -> Agent API -> LangGraph -> MCP -> Skill
```

- Go 逐帧透传 `session/status/result/error/done`，不解析研究结论。
- Agent API 保存有界进程内会话。
- LangGraph 用固定节点和显式条件边控制工具调用与放行。
- 模型只生成结构化研究问题、证据分组、关联说明和下一步研究清单。

固定图：

```text
CLASSIFY
  -> PLAN_REGISTERED_TOOLS
  -> CALL_MCP
  -> VALIDATE_TOOL_ENVELOPES
  -> BUILD_RESEARCH_SYNTHESIS
  -> VALIDATE_RESPONSE
  -> RENDER_ANSWER
```

## 4. 组件职责

### 4.1 AKShare Skill

位置：`skills/akshare-fund-advisor/`

负责：

- 实体解析和 AKShare 接口调用；
- Schema、日期、唯一性和样本校验；
- 收益、波动、回撤、历史分位、ETF 溢价等确定性计算；
- `frame_sha256`、来源、字段和参数审计；
- 产生最具体的业务错误码。

不负责 MCP、HTTP、Agent 编排或网页展示。

### 4.2 Fund Advisor MCP

位置：`src/fund_advisor_mcp/fund/`

负责：

- 强类型输入 Schema 和十个工具注册；
- 超时、进程内 TTL 缓存和传输；
- 把 Skill 结果封装为 `ToolEnvelope`；
- 保留 `data`、`sources`、`data_audit`、warnings 和错误。

不得改写 Skill 的市场数值。

### 4.3 Data API

位置：`src/fund_advisor_data_api/`

负责为数据面板提供普通 REST 接口，调用同一审计数据核心并返回 `ToolEnvelope`。它不包含
模型、会话、LangGraph 或 MCP 协议，服务停止不影响 Agent 自身的 MCP 链路，反之亦然。

### 4.4 Web Research MCP

位置：`src/fund_advisor_mcp/web/`

负责网页搜索、抓取和文档读取。所有结果固定
`numeric_allowed=false`，不能确认实体或覆盖市场事实。安全细节见
[WEB_RESEARCH_MCP.md](WEB_RESEARCH_MCP.md)。

### 4.5 LangGraph Agent

位置：`src/fund_advisor_agent/`

负责问题分类、代码白名单工具计划、MCP 调用、FactRef 构造、结构化研究综合和响应门禁。

不得：

- 直接实例化 `FundAdvisor`；
- 使用开放式 ReAct 或动态工具规划；
- 让模型修改图状态、错误语义或工具权限；
- 让模型生成或修复金融数字。

### 4.6 Agent API

位置：`src/fund_advisor_app/`

只负责 HTTP/SSE、临时会话和兼容 CLI，不托管 React 静态文件。会话只保存最近消息、
上一轮实体和意图；服务重启后可清空，不是市场事实来源。

### 4.7 Go 网页后端

位置：`web-backend/`

负责调用 Data API、Dashboard 短生命周期聚合、静态托管和 Agent SSE 代理。Go 不直接
实现 AKShare 接口或任何金融计算。跨语言字段和透传规则见
[GO_PYTHON_CONTRACT.md](GO_PYTHON_CONTRACT.md)。

### 4.8 React Web

位置：`web/`

负责页面路由、交互和结构化数据渲染。不得实现业务计算、补齐图表数据或从模型文本提取
市场数值。

## 5. 事实、错误和输出门禁

市场事实优先级：

```text
审计通过的 Data API / Skill / Fund MCP
  > 用户给定的官方文档原文
  > Web MCP 非数值背景
  > 模型常识不得作为市场事实
```

统一语义必须区分：

```text
NOT_FOUND
AMBIGUOUS
UNSUPPORTED
UPSTREAM_ERROR
STALE_DATA
```

上游失败只能表达为“当前无法确认”。完整错误码与重试规则见
[ERROR_HANDLING.md](ERROR_HANDLING.md)。

Agent 最终放行至少满足：

- 每个市场数字对应有效 FactRef；
- FactRef 包含工具、字段路径、日期和审计引用；
- Web 数字没有进入市场事实；
- PE/PB 没有被合成综合分；
- 净值位置没有被表述为估值；
- 没有无证据因果和确定性交易指令。

## 6. 页面数据约束

- 每个数据块独立携带 `as_of`、`queried_at`、状态、warning 和审计引用。
- 指数详情展示 PE TTM、PB 历史双图。
- 个股详情分别展示前复权价格、PE TTM、PB。
- 图表只连接工具返回的真实 `chart_series`。
- PE/PB 单侧缺失时只展示可用侧，不使用零值。
- 列表排序只作用于同口径且状态可用的数据。
- “参考 Wind”只表示信息组织，不表示 Wind 数据源或品牌界面。
- ETF 详情提供右侧研究 Agent 抽屉；它只预填当前 ETF 问题并通过 Agent API 重新查询，
  不把页面展示值直接注入 Agent 市场事实。

## 7. 状态与存储

当前服务端只有两类进程内易失状态：

| 状态 | 所在服务 | 用途 |
| --- | --- | --- |
| `InMemorySessionStore` | Agent API | 最近消息、上一轮实体和意图 |
| `MemoryEnvelopeCache` | Data API / Fund MCP | 两个进程各自通过同一 Adapter 实现维护完整信封 TTL 缓存 |

当前不引入 PostgreSQL、Redis、消息队列、数据库 checkpoint 或跨会话长期记忆。

只有出现测量证据后才立项：

- PostgreSQL：全量目录、历史快照或横截面筛选无法按请求完成；
- Redis：多副本共享缓存、分布式锁或跨实例限流成为真实需求。

即使引入存储，市场事实仍必须先经过 Skill/MCP 审计。

## 8. 实现状态

| 能力 | 状态 |
| --- | --- |
| Skill、Data API、Fund/Web MCP、LangGraph、Agent API | 已实现 |
| React 数据面板/Agent 一级分类、指数工作台、ETF 五联图终端与 Agent 页 | 已实现 |
| Go BFF 指数、基金搜索和 ETF Dashboard API | 已实现 |
| 指数看板和 PE/PB 历史双图前端 | 已实现 |
| ETF 搜索、高密度详情终端和右侧 Agent 抽屉 | 已实现 |
| 主动基金产品档案和非 ETF 详情 | 当前下一批 |
| 股票详情、研究动态、完整总览 API | 待实现 |
| 通用 `PageContext` 契约 | 待实现；ETF 抽屉仅预填当前代码，不等同于该契约 |
| `fund_screen` / `stock_screen` | 接口审计完成，工具待实现 |

不在 HLD 维护逐项开发清单；交付状态在 `docs/tasks/` 的三个活跃 TASK 中更新。

## 9. 验证边界

每次架构或部署变更至少验证：

- Python Ruff 和全量 Pytest；
- Go `gofmt`、`go vet` 和单元测试；
- 五个 Compose 服务健康；
- Fund/Web MCP 工具发现；
- Go 到 Data API 的 Dashboard 取数；
- Go 到 Agent API 的 SSE 透传；
- 浏览器页面、移动视口和控制台错误。
