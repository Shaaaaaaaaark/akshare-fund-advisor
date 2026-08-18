# Repository Agent Guide

本文件适用于整个仓库。修改 Skill 时还必须遵守
`skills/akshare-fund-advisor/SKILL.md`。

## 项目方向

项目首先用于面试展示可信 Agent 工程，同时提供基金、指数、ETF 和 A 股数据分析供个人
研究参考。

当前优先级：

1. 按 `TASK_research_dashboard.md` 推进投研数据工作台，指数看板前端和 PE/PB 历史双图
   已完成，ETF 搜索和五联图终端已接入，当前补基金产品档案与非 ETF 详情；
2. 按已审计接口推进基金与股票候选筛选，并在工具完成后接入工作台；
3. 保持 Web、Agent API、MCP、LangGraph、金融门禁和 Ark 结构化模型回归稳定。

当前不优先：

- 组合分析和回测；
- PostgreSQL、Redis、Elasticsearch；
- 多 Agent、RAG、向量库和长期记忆；
- 自动交易和收益预测。

## 实现状态

- Skill CLI 已实现，是当前稳定运行入口。
- Fund MCP 和 Web MCP 的命名空间、入口、配置和测试接线已完成。
- 独立 Data API 已实现，数据面板不经过 Agent、LangGraph 或 MCP 协议取数。
- LangGraph Agent 固定图、MCP Client、FactRef、结构化研究综合和门禁已实现。
- FastAPI Agent API、SSE、有界临时会话、React 对话页和共用 API 的兼容 CLI 已实现。
- Compose 包含 Go 网页后端、Data API、Agent API 和两个 MCP 共五个服务；对外仅暴露
  Go 网页后端。
- Go 网页后端（BFF）已实现指数看板、基金搜索和 ETF 详情取数、ToolEnvelope 原样透传、
  Agent SSE 反向代理、React 静态托管，作为对外唯一 HTTP 入口。
- 指数看板、指数详情、PE/PB 历史双图、ETF 五联图终端、ETF Agent 抽屉和独立 Agent
  页已实现；主动基金产品档案、股票详情和完整总览尚未实现。
- 产品方向已收敛为 Web；网页后端用 Go（BFF），Data API、Agent、MCP、Skill 保留
  Python。
- 已有 CLI 只保留兼容和调试，不继续增加产品功能。
- Ark thinking 模型的 Pydantic 结构化关联输出和门禁闭环已验证。
- 基金和股票单标分析已接入研究/媒体文章与博主/社区公开链接的可选 Web 搜索。
- 财务、行业和基金质量候选接口审计已完成；`stock_screen`、`fund_screen` 尚未实现。

不得把后续组合能力写成“已实现”。

## 事实来源

优先级从高到低：

1. 通过 Schema、时效和 `frame_sha256` 审计的 Data API / AKShare Skill / Fund MCP；
2. 用户给定的官方文档原文；
3. Web MCP 提供的非数值背景；
4. 模型常识不得作为市场事实。

以下内容只能来自审计工具：

- 净值、价格、指数点位；
- PE、PB、收益率、波动、回撤和历史分位；
- 申购、赎回、限额和交易状态；
- 实体是否存在及其规范代码。

模型不得生成、补齐、插值、前向填充、修复或改写上述内容。

## 错误语义

必须区分：

- `NOT_FOUND`；
- `AMBIGUOUS`；
- `UNSUPPORTED`；
- `UPSTREAM_ERROR`；
- `STALE_DATA`。

上游失败只能回答“当前无法确认”，不能回答“该标的不存在”。

## 架构边界

当前依赖方向：

```text
React Web
  -> Go 网页后端（BFF）
     |-- 数据面板 -> Data API (Python) -> AKShare Skill
     `-- Agent SSE -> Agent API (Python) -> LangGraph
                                      |-> Fund MCP -> AKShare Skill
                                      `-> Web MCP -> 公网内容
```

- `skills/akshare-fund-advisor/scripts/fund_advisor.py`：实体解析、AKShare 调用、确定性指标和审计。
- `src/fund_advisor_data_api/`：数据面板专用 REST API，不包含模型、会话或 MCP 协议。
- `src/fund_advisor_mcp/fund/`：市场事实 MCP，不改写 Skill 数值。
- `src/fund_advisor_mcp/web/`：非数值背景 MCP，固定 `numeric_allowed=false`。
- `src/fund_advisor_agent/`：只做固定图编排、工具路由、关联说明和输出校验。
- `src/fund_advisor_app/`：Python Agent API、SSE、临时会话和兼容 CLI。
- Go 网页后端：Dashboard BFF、静态托管、Agent SSE 代理，只取数聚合，不做任何金融
  计算或审计改写；边界见 `docs/GO_PYTHON_CONTRACT.md`。
- `web/`：React 界面，不实现业务计算或金融事实生成。

语言分工：Go 只做网页后端（调用 Data API、有界并发聚合、超时、静态托管、SSE
代理）；Python 保留 Data API、Agent、MCP、Skill 和全部金融计算与审计。当前 Go BFF
未实现结果缓存、请求去重或业务限流。Go 不得直接实现 AKShare 接口，不得重算、改写、
四舍五入、插值或合成任何净值、价格、PE、PB、收益率、回撤、分位、限额或交易状态，
必须原样透传 `ToolEnvelope` 的 `data_audit`、`frame_sha256`、warnings 和错误码。

源码层级顺依赖方向：仓库级 `src/` 存放 Data API、Agent 与 MCP，
`skills/akshare-fund-advisor/` 回归纯数据层（SKILL.md + scripts + references），可独立
拷贝。

LangGraph 只使用 `StateGraph` 和显式条件边。不得恢复 LangChain Agent、开放式 ReAct、
动态工具规划、数据库 checkpoint、长期记忆或多 Agent。

Web 必须通过 Agent API 调用研究能力，不复制图编排或金融计算。已有 CLI 仍共用 Agent
API，但不得继续扩展产品能力。会话只允许保存进程内的最近消息、上一轮实体和意图；
不得把对话历史升级为市场事实，不得引入数据库或跨会话记忆。

## Agent 关联说明

职责分工：

- 数据工具提供并校验金融事实；
- Agent 控制固定研究流程、工具调用、错误分支和输出门禁；
- 模型理解自然语言并解释已验证事实，不决定金融数字、工具权限、图状态或最终放行。

当前模型通过一次结构化调用生成研究问题、支持/反对/未知证据分组、关联说明和下一步
研究清单。用户期限、仓位和风险承受能力尚未形成独立输入契约，不得写成已实现，也不得
借模型增强恢复开放式动态规划。

Agent 可以解释多个工具事实如何共同影响研究理解，但必须：

- 每条关联引用具体工具和字段；
- 区分事实、关联和限制；
- 明确相关性不等于因果；
- 不从历史统计预测未来收益；
- 不把净值位置写成估值；
- 不把 PE/PB 合成综合分；
- 不输出确定性交易指令。

Web 中 PE/PB 不得只展示当前值：

- 总览和列表可以展示当前值、历史分位和日期；
- 指数详情必须展示 PE TTM、PB 历史双图；
- 个股详情必须分别展示前复权价格、PE TTM、PB 历史曲线；
- 图表只能连接工具返回的真实 `chart_series`，不得由前端或模型补点；
- 信息组织可以参考 Wind 深度资料，但不得声称使用 Wind 数据或复制其品牌界面。

LangGraph 节点必须保持单一职责，节点间只通过 `AgentState` 传递结构化数据。工具计划、
错误分支和最终放行条件由代码决定，模型不得直接修改图状态或选择未注册工具。

## 修改原则

- 优先复用现有 Schema、错误模型和指标函数。
- 金融计算只能使用确定性函数。
- 新增工具必须同步 Schema、Adapter、Server、工具数量和测试。
- 新增市场数值必须同步接口来源、字段口径、时效和审计记录。
- 不在 Agent 文本中复制计算逻辑。
- 不改写用户未提交的无关修改。

## 验证

项目始终在 Docker 运行，稳定验证入口是 Compose test 镜像，在容器内执行 Ruff 和全量
Pytest：

```bash
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test
```

Go 网页后端改动须在容器内执行 `go vet` 和 Go 单元测试：

```bash
docker run --rm -v "$PWD/web-backend":/src -w /src golang:1.22-alpine \
  sh -c "gofmt -l . && go vet ./... && go test ./..."
```

Docker 相关改动仍须重新运行 Compose 测试、五个服务健康检查、Data API 健康与
Fund/Web MCP 工具发现和 Web/API 闭环，并验证 Go→Data API 取数与 Go→Agent SSE 连通。

本地 `.venv-agent` 只是可选调试环境，未纳入版本控制，需先按 README 创建后才能使用：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
.venv-agent/bin/python -m ruff check --no-cache .
.venv-agent/bin/python -m pytest -q -p no:cacheprovider
AKSHARE_FUND_VENV="$PWD/.venv-agent" bash "$SKILL_DIR/scripts/run.sh" audit
```

## 文档同步

- 产品方向：`docs/PRODUCT.md`
- 架构与组件边界：`README.md`、`docs/HLD.md`
- Go/Python 边界与透传契约：`docs/GO_PYTHON_CONTRACT.md`
- 错误语义：`docs/ERROR_HANDLING.md`
- Web MCP：`docs/WEB_RESEARCH_MCP.md`
- Skill 接口和指标：Skill 目录及 `references/`
- 实施优先级：`docs/tasks/`
