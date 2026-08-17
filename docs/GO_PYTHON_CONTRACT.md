# Go 网页后端与 Python Agent 透传契约

> 状态：`M0 骨架已实现，契约持续适用`
>
> 适用范围：Go Web 后端（Dashboard BFF + 静态托管 + Agent SSE 代理）与 Python
> Agent API / MCP / Skill 之间的边界。
>
> 实现位置：`web-backend/`（`internal/mcp` 透传 Client、`internal/dashboard` 取数与
> 状态映射、`internal/proxy` SSE 代理、`internal/static` 静态托管）。
>
> 上位约束：[AGENTS.md](../AGENTS.md)、[HLD.md](HLD.md)、[ERROR_HANDLING.md](ERROR_HANDLING.md)。

## 1. 语言分工

```text
React 前端
  -> Go 网页后端（BFF）
       - 静态资源托管、路由、TLS
       - Dashboard 取数：并发聚合、缓存、限流
       - Agent SSE 反向代理
       |
       +-- 数据路径：Go 作为 MCP Client -> Python Fund MCP -> AKShare Skill
       `-- Agent 路径：透传 -> Python Agent API -> LangGraph -> MCP -> Skill
```

Go 负责：编排取数、聚合、缓存、限流、静态托管、SSE 代理。
Python 负责：AKShare Skill、Fund/Web MCP、LangGraph Agent、结构化研究综合、所有金融
计算与门禁。

## 2. 不可移植清单（必须留在 Python）

以下能力是市场事实与安全边界，Go 一律不得重写、复算或改写：

- AKShare Skill 的实体解析、确定性指标（收益、波动、回撤、历史分位、PE/PB 分位、
  ETF 溢价）和 `frame_sha256` 审计。
- Fund MCP / Web MCP 的参数契约、缓存、超时和 `ToolEnvelope` 生成。
- LangGraph 固定图、研究综合和响应门禁。

Go 中不得出现任何净值、价格、PE、PB、收益率、回撤、分位、限额或交易状态的重新计算、
四舍五入、单位换算、插值、补点或综合评分。

## 3. Go 允许做的事

- 作为 MCP Client 调用已注册工具，按页面需要并发聚合多个 `ToolEnvelope`。
- 施加有界并发、请求去重、短 TTL 缓存、超时和限流。
- 组织 Dashboard 响应结构（分组、排序视图、字段选择）。
- 托管 React 构建产物；把 `/api/chat/stream` 等 Agent 请求反向代理到 Python Agent API。

Go 的排序和分组只能作用于同口径、状态可用的数据；缺失和过期数据不得参与排序，也不得
用零值占位。

## 4. 透传契约：`ToolEnvelope`

Python `ToolEnvelope`（`src/fund_advisor_mcp/fund/schemas.py`）当前字段：

```text
schema_version: "1.0"
request_id:     UUID
tool:           ToolName
ok:             bool
data:           object | null
sources:        array
data_audit:     array           # 每次真实接口调用的参数、字段、行数、frame_sha256
data_warnings:  array           # 字符串或对象
data_policy:    object          # 含 ai_may_generate_market_data 等
queried_at:     datetime(RFC3339)
error:          { code, message, retryable, details } | null
```

Go 侧规则：

- 用 `json.RawMessage` 承载 `data`、`sources`、`data_audit`、`data_warnings`、
  `data_policy`，**原样透传**，不重排字段、不改数值精度、不丢字段。
- `queried_at` 按字符串透传，不做时区改写。
- `ok=false` 时必须把 `error.code` 原样返回给前端，Go 不重写错误码。
- 不得剥离 `data_audit` 或 `frame_sha256`；这是前端可反查审计的依据。
- Go 不解析 `data` 内部业务数字用于再计算；只在需要选字段时做只读读取。

## 5. Dashboard 响应包装

Go 在 envelope 之上添加展示层元数据，但不改原始事实：

```text
DatasetMeta
  as_of          # 取自工具事实字段的数据日期，不是 Go 生成的当前时间
  queried_at     # 透传自 ToolEnvelope.queried_at
  status         # available | partial | stale | unavailable | not_implemented
  source_tools   # 参与本数据块的工具名
  audit_refs     # 对应 data_audit 中的 frame_sha256
  warnings       # 透传 data_warnings
  error          # 透传 ToolError（如有）
```

状态映射（与 [ERROR_HANDLING.md](ERROR_HANDLING.md) 一致，Go 不新增语义）：

```text
工具 ok 且新鲜        -> available
可选工具失败/部分成功 -> partial
STALE_DATA           -> stale
NOT_FOUND/UNSUPPORTED/UPSTREAM_ERROR/AMBIGUOUS -> unavailable（保留原始 error.code）
fund_screen/stock_screen 未实现 -> not_implemented
```

- `as_of` 必须来自工具返回的数据日期字段，Go 不得用服务器当前时间冒充数据时效。
- 上游失败一律 `unavailable` 并保留原始错误码，不得回退成空列表或“不存在”。

## 6. Agent SSE 代理契约

- Go 对 `POST /api/chat/stream` 只做反向代理，逐帧透传
  `session / status / result / error / done` 事件，不缓冲整流、不改写事件顺序。
- Go 不解析研究结论、不注入市场数字、不改写门禁结果。
- 代理需正确处理 `text/event-stream`、禁用响应缓冲、传播客户端断开。
- 临时会话状态仍由 Python Agent API 进程内持有；Go 不落库、不持久化会话。
- 当前部署中前端必须经 Go 代理访问 Python Agent API；Python 服务不暴露宿主端口。
  本地调试可以直连，但不得成为产品部署路径。

## 7. Schema 同步规则

- Python Pydantic Schema 是 `ToolEnvelope`、`ToolError` 和 `FactRef` 的事实源。
- Go `internal/dashboard` 类型是 `DatasetMeta` 和 Dashboard HTTP 包装的事实源。
- 任一跨语言字段变更，必须同步更新双方类型、测试与本契约文档。
- Go 结构体对未知字段保持宽容透传（`json.RawMessage` 或保留原始 JSON），避免字段漂移
  导致审计字段丢失。
- 强类型只用于 Go 需要读取的少数展示字段（名称、代码、状态、`as_of`）。
- 契约版本以 `schema_version` 为准；不兼容变更必须升版本并在两侧同步。

## 8. 部署形态

```text
React 静态产物  ->  Go Web 后端容器（对外唯一 HTTP 入口）
                      ├─ MCP Client -> fund-advisor-mcp（容器网络内）
                      ├─ MCP Client -> web-research-mcp（容器网络内，可选）
                      └─ SSE 代理   -> agent-api（Python，容器网络内）
```

- Go 服务对外暴露端口；Python Agent API 与两个 MCP 仅在容器网络内可达。
- `config/config.local.yaml` 仍只读挂载给 Python 服务，密钥不进入镜像、不下发给前端。
- 具体 Dockerfile 阶段与 compose 服务接线在实现阶段落地，本文件只定义边界与契约。

## 9. 验收要点

- Go 返回的任一市场数值都能反查到对应 `ToolEnvelope` 字段与 `frame_sha256`。
- Go 侧无任何金融计算、综合评分或补点逻辑。
- 上游失败、过期、未实现在 Go 响应中分别为 `unavailable`/`stale`/`not_implemented`，
  错误码与 Python 一致。
- SSE 事件顺序、门禁结论与直连 Python Agent API 完全一致。
- Python 契约变更后，Go 结构体与本文档同步更新，审计字段无丢失。
