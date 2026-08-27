# Repository Agent Guide

本文件适用于整个仓库。修改 Skill 时还必须遵守
`skills/akshare-fund-advisor/SKILL.md`。

## 项目方向

项目首先用于面试展示可信 Agent 工程，同时提供基金、指数、ETF 和 A 股数据分析供个人
研究参考。

当前优先级：

1. 稳定 Java 21 + Spring Boot WebFlux BFF，保持 HTTP/JSON/SSE 黑盒契约不变；
2. 保持投研数据工作台 MVP 稳定：指数、ETF、主动基金产品档案、股票单标价格/PE/PB
   和 Agent 均已可运行，细节增强按 `docs/ROADMAP.md` 排队；
3. 按已审计接口推进基金与股票候选筛选，并保持 Web、Agent API、MCP、LangGraph、
   金融门禁和 Ark 结构化模型回归稳定。

当前不优先：

- 组合分析和回测；
- PostgreSQL、Redis、Elasticsearch；
- 多 Agent、RAG、向量库和长期记忆；
- 自动交易和收益预测。

## 实现状态

- Agent Skill 包装和内部调试脚本已实现；目标架构中 Skill 只服务 Agent，不承担数据
  来源层定位。
- Fund MCP 和 Web MCP 的命名空间、入口、配置和测试接线已完成。
- 独立 Data API 已实现，数据面板不经过 Agent、LangGraph 或 MCP 协议取数。
- LangGraph Agent 固定图、MCP Client、FactRef、结构化研究综合和门禁已实现。
- FastAPI Agent API、SSE、有界临时会话和 React 对话页已实现。
- Compose 包含 Java 网页后端、Data API、Agent API 和两个 MCP 共五个服务；对外仅暴露
  Java 网页后端。
- Java BFF 已实现指数、基金搜索、ETF、主动基金四块聚合和股票单标取数、
  ToolEnvelope 原样透传、Agent SSE 反向代理、React 静态托管和 `/health`。
- 跨模块总览、指数看板、指数详情、PE/PB 历史双图、ETF 五联图终端、主动基金产品
  档案、股票单标价格/PE/PB、ETF Agent 抽屉和独立 Agent 页已实现；研究动态尚未实现。
- 产品方向已收敛为 Web；目标网页后端用 Java 21 + Spring Boot WebFlux，Data API、
  Agent、MCP 和 Agent Skill 保留 Python。
- Ark thinking 模型的 Pydantic 结构化关联输出和门禁闭环已验证。
- 基金和股票单标分析已接入研究/媒体文章与博主/社区公开链接的可选 Web 搜索。
- 财务、行业和基金质量候选接口审计已完成；`stock_screen`、`fund_screen` 尚未实现。

不得把后续组合能力写成“已实现”。

## 事实来源

优先级从高到低：

1. 通过 Schema、时效和 `frame_sha256` 审计的 Data API / Fund MCP；
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

目标依赖方向：

```text
React Web
  -> Java 网页后端（BFF）
     |-- 数据面板 -> Data API (Python) -> data_core -> providers(AKShare/...)
     `-- Agent SSE -> Agent API (Python) -> LangGraph
                                      |-> Fund MCP -> data_core
                                      `-> Web MCP -> 公网内容
```

- `src/fund_advisor_data_core/`：目标数据核心，负责数据源 provider、审计、Schema 和确定性指标。
- `skills/akshare-fund-advisor/scripts/fund_advisor.py`：Agent Skill 内部脚本；当前 legacy
  实现仍承载部分数据调用，后续应逐步迁移到 `data_core`。
- `src/fund_advisor_data_api/`：数据面板专用 REST API，不包含模型、会话或 MCP 协议。
- `src/fund_advisor_mcp/fund/`：市场事实 MCP，不改写 data_core 数值；必要时可包装
  Agent Skill 能力，但不把 Skill 定位为数据来源层。
- `src/fund_advisor_mcp/web/`：非数值背景 MCP，固定 `numeric_allowed=false`。
- `src/fund_advisor_agent/`：只做固定图编排、工具路由、关联说明和输出校验。
- `src/fund_advisor_app/`：Python Agent API、SSE 和临时会话。
- Java 网页后端：Dashboard BFF、静态托管、Agent SSE 代理，只取数聚合，不做任何
  金融计算或审计改写；边界见 `docs/ARCHITECTURE.md`。
- `web/`：React 界面，不实现业务计算或金融事实生成。

语言分工：Java 只做网页后端（调用 Data API、有界并发聚合、超时、静态托管、SSE
代理）；Python 保留 Data API、Agent、MCP、Agent Skill 和全部金融计算与审计。Java BFF
不得直接实现 AKShare 接口，不得重算、改写、四舍五入、插值或合成任何净值、价格、
PE、PB、收益率、回撤、分位、限额或交易状态，必须原样透传 `ToolEnvelope` 的
`data_audit`、`frame_sha256`、warnings 和错误码。

Java BFF 固定使用 Java 21、Spring Boot WebFlux、Maven、WebClient、Jackson、
Bean Validation、Actuator 和 JUnit 5。当前不引入 Spring Cloud Gateway、Feign、Lombok、
数据库、Redis 或 MQ。所有 Data API 调用共享全局并发门禁，Agent SSE 必须逐块转发，
不得缓冲完整响应。

源码层级顺依赖方向：仓库级 `src/` 存放 Data API、data_core、Agent 与 MCP，
`skills/akshare-fund-advisor/` 只保留 Agent Skill 包装、内部脚本与说明，可独立拷贝。

LangGraph 只使用 `StateGraph` 和显式条件边。不得恢复 LangChain Agent、开放式 ReAct、
动态工具规划、数据库 checkpoint、长期记忆或多 Agent。

Web 必须通过 Agent API 调用研究能力，不复制图编排或金融计算。会话只允许保存进程内
的最近消息、上一轮实体和意图；不得把对话历史升级为市场事实，不得引入数据库或跨会话
记忆。

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

Java BFF 迁移完成后须在容器内执行 Maven 验证：

```bash
docker run --rm -v "$PWD/web-backend":/workspace -w /workspace \
  eclipse-temurin:21-jdk ./mvnw verify
```

Docker 相关改动仍须重新运行 Compose 测试、五个服务健康检查、Data API 健康与
Fund/Web MCP 工具发现和 Web/API 闭环，并验证 Java→Data API 取数与 Java→Agent SSE
连通。

本地 `.venv-agent` 只是可选调试环境，未纳入版本控制，需先按 README 创建后才能使用：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
.venv-agent/bin/python -m ruff check --no-cache .
.venv-agent/bin/python -m pytest -q -p no:cacheprovider
AKSHARE_FUND_VENV="$PWD/.venv-agent" bash "$SKILL_DIR/scripts/run.sh" audit
```

## 文档同步

- 项目入口和运行方式：`README.md`
- 架构、契约、错误与安全边界：`docs/ARCHITECTURE.md`
- 实现状态和优先级：`docs/ROADMAP.md`
- Skill 接口和指标：Skill 目录及 `references/`
