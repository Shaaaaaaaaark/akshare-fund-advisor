# 整体架构

本文是仓库架构、边界、协议和错误语义的唯一入口。实现进度见
[ROADMAP.md](ROADMAP.md)，数据接口和指标细节见
[`skills/akshare-fund-advisor/references/`](../skills/akshare-fund-advisor/references/)。

## 1. 目标

项目是一个可信投研数据工作台，也是受控 Agent 工程示例：

- 数据面板直接展示经过审计的基金、ETF、指数和 A 股数据；
- Agent 解释已验证事实，不决定金融数字、工具权限、图状态或最终放行；
- 不预测收益、不输出确定性交易指令、不自动交易。

市场事实只能来自经过 Schema、时效和 `frame_sha256` 审计的工具结果。模型、Java
BFF 和 React 不得生成、补齐、插值、修复或改写市场事实。

## 2. 系统拓扑

### 目标架构

```text
React Web
  -> Java BFF（对外唯一 HTTP 入口）
     |-- Dashboard REST
     |     -> Python Data API
     |        -> data_core / legacy Skill bridge
     |           -> providers(AKShare/...)
     |
     `-- Agent SSE proxy
           -> Python Agent API
              -> fixed LangGraph
                 |-- Fund MCP -> data_core / legacy Skill bridge
                 `-- Web MCP  -> 公网非数值背景
```

部分 legacy 数据调用仍在 Agent Skill 内部脚本中，按 Roadmap 逐步迁移到 `data_core`。
Skill 只作为 Agent 能力包装和内部调试边界，不是数据来源层。

原 Go BFF 已由 Java BFF 替换。主干只保留 Java Web 后端，不维护 Go/Java 双栈。

### 目标 Agent 架构

目标是在现有固定图外增加精简的 Pi-style Harness，不引入 Pi 的 Node runtime、TUI、
文件系统工具或开放式扩展机制。

```text
Java BFF
  -> Python Agent Service
     -> Financial Agent Harness
        |-- Run Controller
        |-- Session Context / Context Compressor
        |-- Fixed LangGraph Runtime
        |-- Model Gateway
        |-- Tool Registry / Tool Gate / Tool Executor
        |-- Evidence Ledger
        `-- Final Answer Gate
              -> AgentEvent stream
```

Harness 是控制平面。模型和工具不能直接互调，所有工具调用都必须经过 Harness。

## 3. 依赖方向

允许：

```text
React -> Java BFF
Java BFF -> Data API / Agent API
Data API / Fund MCP -> data_core -> providers
Agent Harness -> fixed LangGraph
Agent Harness -> Model Gateway
Agent Harness -> Tool Gateway -> Fund/Web MCP
```

禁止：

1. React 直连 Python 服务。
2. Java BFF 调用 AKShare、计算或改写金融数值。
3. 模型直接调用 MCP、Data API、Redis、Skill 或 `data_core`。
4. 工具调用模型、修改会话状态或生成最终投资结论。
5. `data_core` 依赖 Agent、Web、Java BFF、Redis 或模型。
6. Skill 成为 Dashboard 数据来源层。
7. 对话历史、页面文本和 Web 内容升级为市场事实。

## 4. 组件职责

| 组件 | 负责 | 不负责 |
| --- | --- | --- |
| React Web | 展示数据、图表、状态和 Agent 事件 | 金融计算、补点、直连 Python |
| Java BFF | 静态托管、REST 聚合、有界并发、超时、SSE 代理 | 金融计算、审计改写、模型调用 |
| Data API | 面板专用 REST、参数校验、返回完整信封 | Agent、会话、MCP 协议 |
| `data_core` | Provider、实体解析、Schema、确定性指标、审计 | HTTP、MCP、Agent 编排 |
| Fund MCP | 市场事实工具、Schema、超时和信封 | 改写 `data_core` 数值 |
| Web MCP | 搜索、网页和文档的非数值背景 | 确认实体或市场数字 |
| Agent Skill | Agent 技能包装和内部脚本 | 数据来源层 |
| Fixed LangGraph | 固定研究流程、条件边、工具计划和错误分支 | 开放式 ReAct、动态工具规划 |
| Model Gateway | 模型适配、结构化调用、Fake Model 测试 | 数据访问、工具执行、事实裁决 |
| Agent Harness | Run、权限、上下文、工具门禁、证据和最终放行 | 金融数据计算 |

### Java BFF 技术方案

最终 `web-backend/` 使用：

| 领域 | 选型 |
| --- | --- |
| 运行时 | Java 21 LTS |
| 框架 | Spring Boot 3.5.x |
| HTTP | Spring WebFlux + Reactor Netty |
| 内部客户端 | `WebClient` |
| JSON | Jackson `JsonNode` + `@JsonRawValue` |
| 参数校验 | Jakarta Bean Validation |
| 并发门禁 | Resilience4j Reactor Bulkhead |
| 健康检查 | Spring Boot Actuator |
| 构建 | Maven Wrapper |
| 测试 | JUnit 5、WebTestClient、MockWebServer |

不引入 Spring Cloud Gateway、Feign、Lombok、数据库、Redis 或 MQ。BFF 只有固定路由和
聚合逻辑，直接使用 WebFlux 比引入完整网关平台更容易审计。Spring Boot 使用 3.5
版本线，实施时在 `pom.xml` 固定具体 patch，不使用动态版本。

关键实现规则：

1. Data API 响应先保留原始 JSON 字符串，再解析只读 `JsonNode` 提取
   `DatasetMeta`；只有解析成功后，外层响应才通过 `@JsonRawValue` 嵌入完整信封，
   避免改写数值精度、字段和错误。
2. Agent SSE 使用 `WebClient` 读取 `Flux<DataBuffer>` 并逐块写回下游，不聚合完整响应；
   客户端断开必须取消上游订阅。
3. 普通 Data API 调用预算保持 90 秒，Java Dashboard 普通接口保持 95 秒左右的服务端
   预算；Overview/产品聚合按调用批次计算预算，前端继续使用 100/200 秒上限。
4. 所有 Data API 调用共享一个全局 Bulkhead，默认并发 4；Controller 不得绕过该门禁。
5. 非法 `years`、`max_points`、`limit` 和路径参数在 Java HTTP 边界返回 400，不调用
   Python。
6. React 构建产物打入 Spring Boot 静态资源；非 API 路径支持 SPA fallback，缺失静态
   资源返回真实 404。

最终目录：

```text
web-backend/
  pom.xml
  mvnw
  .mvn/wrapper/
  src/main/java/com/fundadvisor/web/
    WebBackendApplication.java
    config/BffProperties.java
    facts/ToolEnvelope.java
    dataapi/DataApiClient.java
    dashboard/DashboardController.java
    dashboard/DashboardService.java
    dashboard/model/
    agent/AgentProxyHandler.java
    web/SpaFallbackHandler.java
  src/main/resources/
    application.yaml
    static/
  src/test/java/com/fundadvisor/web/
```

## 5. 两条数据链路

### Dashboard

```text
React -> Java Dashboard API -> Data API -> data_core -> providers
```

- 不调用模型、LangGraph 或 MCP；
- Java BFF 可以聚合和选择展示字段，但不得重算、四舍五入、换算、插值或补点；
- 每个数据块保留完整 `ToolEnvelope`、独立状态、日期、warning 和审计引用；
- `fund_screening`、`stock_screening` 在工具完成前必须为 `not_implemented`。

主要 BFF 接口：

```text
GET /api/dashboard/overview
GET /api/dashboard/overview/{index|etf|fund|stock}
GET /api/dashboard/indices
GET /api/dashboard/indices/{index}
GET /api/dashboard/funds/search
GET /api/dashboard/funds/{fund}
GET /api/dashboard/funds/{fund}/product
GET /api/dashboard/stocks/{stock}
```

### Agent

```text
React -> Java SSE proxy -> Agent API -> fixed LangGraph -> Fund/Web MCP
```

- 图只使用 `StateGraph` 和显式条件边；
- 代码决定工具计划、错误分支和最终放行；
- 模型只做意图理解、结构化综合和已验证事实解释；
- Fund MCP 失败时，Web 内容不能替代市场事实。

## 6. 市场事实契约

Python `ToolEnvelope` 是跨边界事实信封：

```text
schema_version: "1.0"
request_id:     UUID
tool:           ToolName
ok:             bool
data:           object | null
sources:        array
data_audit:     array
data_warnings:  array
data_policy:    object
queried_at:     datetime
error:          {code, message, retryable, details} | null
```

规则：

1. `data_audit` 保留接口、参数、字段、行数和 `frame_sha256`。
2. `ok=false` 时保留已产生的来源、审计和 warning。
3. Java BFF 使用原始 JSON 透传金融事实，不改变精度、时区或错误码。
4. 图表只连接工具返回的真实 `chart_series`。
5. PE、PB、价格、净值、收益、回撤、分位、限额、交易状态和实体存在性只能来自信封。

Java BFF 可在信封外增加展示元数据：

```text
DatasetMeta
  as_of          # 来自工具事实日期，不是服务器当前时间
  queried_at
  status         # available | partial | stale | unavailable | not_implemented
  source_tools
  audit_refs
  warnings
  error
```

## 7. Agent Harness

### 核心组件

| 组件 | 职责 |
| --- | --- |
| Protocol | 版本化 Run、Event 和 Tool 调用模型 |
| Run Controller | `request_id/run_id/trace_id`、超时、取消、事件顺序 |
| Session Context | 有界最近消息、上一轮实体和意图、页面上下文 |
| Context Compressor | 把内部记录压缩为模型可见上下文 |
| Fixed Graph Adapter | 包装现有 `fund_advisor_agent` 固定图 |
| Model Gateway | Ark/OpenAI-compatible/Fake Model 的统一小接口 |
| Tool Registry | 静态白名单、输入输出 Schema 和能力标签 |
| Tool Gate | 调用前权限校验和调用后信封审计 |
| Evidence Ledger | 已验收事实、字段、日期、来源和哈希 |
| Final Answer Gate | 引用、时效、限制和投资建议边界 |

当前没有独立 Agent Service 代码；Harness 是后续实现目标，现有生产入口仍是
`src/fund_advisor_app/` 的 Agent API。

### 权限门禁

```text
Java identity/rate-limit gate
  -> Agent run/mode gate
  -> Tool Registry allowlist
  -> before_tool_call
  -> Data API / MCP validation
  -> after_tool_call
  -> Final Answer Gate
```

- `before_tool_call`：校验工具注册、参数 Schema、实体歧义、权限、数值策略、超时和并发；
- `after_tool_call`：校验完整 `ToolEnvelope`、工具名、数据结构、审计哈希、warning 和时效；
- 未通过的结果进入错误或限制分支，不能进入 Evidence Ledger；
- `user_context` 和 `security_context` 由 Java BFF 生成并作为内部可信上下文传递。

### 模型与工具隔离

模型可以：

- 解析用户意图；
- 生成受 Schema 约束的结构化输出；
- 解释 Evidence Ledger 中的事实。

模型不可以：

- 选择未注册工具或修改图状态；
- 生成缺失数字、日期、状态或实体代码；
- 覆盖工具错误、warning 或时效结论。

工具可以调用受控数据能力并返回完整信封，但不能读取任意模型历史、调用模型或生成最终
研究结论。

### 上下文压缩

内部记录与模型上下文分离：

```text
内部事件/消息/工具信封
  -> 保留当前请求和 PageContext
  -> 压缩用户意图与非市场偏好
  -> 仅附加已验收 Evidence 引用
  -> 附加未解决问题和错误
  -> 模型可见上下文
```

压缩摘要不是市场事实来源。它不能保留：

- 未验收工具结果；
- Web 数值；
- 过期且未通过策略的数据；
- 模型先前生成但没有 Evidence 引用的市场事实；
- 任意页面文本中的市场数字。

MVP 只需要短期原始事件窗口和会话级语义摘要，不做跨会话长期记忆。最终答案引用
Evidence，而不是引用摘要文本。

### 事件协议

当前 SSE 使用既有 `session/status/result/error/done`。目标 Harness 使用版本化事件：

```text
run.created / run.started
message.delta / message.completed
tool.started / tool.completed / tool.failed
artifact.created
run.completed / run.failed / run.cancelled
```

后续可以增加 `turn.*`、`evidence.*` 和 `gate.failed`，但 HTTP NDJSON、SSE 或未来 gRPC
只改变传输，不改变事件语义。

## 8. 错误和降级

必须保留五类语义：

| 语义 | 含义 | 用户表达 |
| --- | --- | --- |
| `NOT_FOUND` | 目录成功但无匹配 | 未找到该标的 |
| `AMBIGUOUS` | 多个候选 | 展示候选并追问 |
| `UNSUPPORTED` | 实体可能存在，但当前接口不支持 | 当前能力不支持 |
| `UPSTREAM_ERROR` | 上游或网络失败 | 当前无法确认 |
| `STALE_DATA` | 数据存在但过期 | 数据过期，不用于当前结论 |

规则：

1. 上游失败不得映射成不存在。
2. 必需接口失败时工具失败，不生成对应结论。
3. 可选接口失败时可保留主要结果，但必须进入 `data_warnings`。
4. PE/PB 单侧失败不能互相替代。
5. 失败信封不缓存；当前 Agent 不做通用自动重试。
6. HTTP 参数错误直接返回 4xx，不伪装成市场事实错误。

Java BFF 展示状态映射：

```text
ok=true                       -> available
STALE_DATA                    -> stale
部分数据块成功                -> partial
NOT_FOUND/AMBIGUOUS/
UNSUPPORTED/UPSTREAM_ERROR    -> unavailable，保留原始 code
尚未实现                      -> not_implemented
```

## 9. Web Research 安全

Web MCP 只有三个工具：`web_search`、`web_fetch`、`document_read`。其固定策略为：

```json
{
  "purpose": "background_only",
  "numeric_allowed": false,
  "ai_may_generate_market_data": false,
  "may_override_market_tools": false
}
```

网页文本是不可信输入，不是 Agent 指令。抓取必须限制公网 HTTP/HTTPS URL，拒绝私网和
保留地址，每次重定向重新校验 DNS，并限制重定向、字节数、正文长度和内容类型。

## 10. 状态与存储

当前实现：

- Agent 会话只在进程内保存最近消息、上一轮实体和意图；
- Data API 与 MCP 使用进程内完整信封 TTL 缓存；
- 不启用 PostgreSQL、Redis、MQ、数据库 checkpoint 或长期记忆。

目标扩展仅在有测量证据时启用：

- Redis：网关限流、Run 状态、取消信号、短事件缓冲；
- Redis 缓存只能保存完整 `ToolEnvelope`，不能保存裸市场字段；
- Redis Stream/MQ：只在长任务需要排队、恢复、重试或多 worker 时引入。

## 11. 部署与验证

Compose 包含五个运行服务：

```text
web-backend       # Java Spring Boot，对外暴露
data-api          # Python，仅容器网络
agent-api         # Python，仅容器网络
fund-advisor-mcp  # Python，仅容器网络
web-research-mcp  # Python，仅容器网络
```

Python 全量检查：

```bash
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test
```

Java BFF 检查：

```bash
docker run --rm -v "$PWD/web-backend":/workspace -w /workspace \
  eclipse-temurin:21-jdk ./mvnw verify
```

Docker 相关改动还需验证五服务健康、Data API、MCP 工具发现、Java 到 Data API 取数和
Java 到 Agent SSE 闭环。
