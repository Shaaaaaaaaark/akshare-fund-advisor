# AKShare Financial Research Agent

面向中国基金、指数和 A 股研究的个人数据分析工具，也是用于面试展示可信 Agent
工程能力的项目。

项目当前优先做好两件事：

1. 用 AKShare 获取并审计基金、指数、ETF 和 A 股数据，进行确定性分析。
2. 用 LangGraph 固定状态图调用这些工具，关联已审计事实字段并解释其含义，但不生成
   市场事实、不预测涨跌、不替用户决策。

## 产品定位

它不是荐股机器人，也不是量化交易平台。目标是回答：

- 一只基金的产品类型、费用、评级、历史收益、波动和回撤如何？
- ETF 的场内价格、IOPV 和溢价风险如何？
- 指数或个股当前 PE/PB 位于历史什么位置，完整历史曲线如何变化？
- 多只基金是否同口径、能否直接比较？
- 基金产品、跟踪指数估值、历史风险和交易状态之间存在什么关联？

Agent 的职责是组织工具调用和说明关联，不能把相关性写成因果，也不能补齐工具没有
返回的数据。

## Agent 与模型定位

```text
数据工具：提供并校验金融事实
Agent：理解问题、组织研究流程、调用工具、处理失败和执行门禁
模型：整理研究问题、分组证据、解释事实与观点、生成下一步研究清单
```

当前 Agent 的固定编排和门禁已经实现；模型通过一次结构化调用生成研究问题、
支持/反对/未知证据分组、关联说明和下一步研究清单，并可选在规则未提取到实体时补充
意图。根据明确的用户期限、仓位和风险承受能力调整解释重点仍是后续增强。

模型不能生成市场数据、修改工具计划、改变错误状态或绕过输出校验。它的价值是把可信
数据转化为可理解的研究上下文，而不是扮演 AI 基金经理。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| AKShare Skill CLI | 已实现 | `search`、`status`、`analyze`、`profile`、`rating`、`valuation`、`compare`、`audit` |
| Fund Advisor MCP | 已实现 | 九个强类型市场事实工具，stdio 工具发现已验证 |
| Web Research MCP | 已实现 | 三个非数值背景工具，stdio 工具发现已验证 |
| LangGraph Agent | 已实现 | 固定状态图、FactRef、结构化研究综合、输出门禁和节点进度流 |
| Agent API | 已实现 | FastAPI、SSE 和有界临时会话（Python），供 Web 使用 |
| Web | 已实现基础入口 | React 对话页已实现，下一阶段升级为投研数据工作台 |
| Go 网页后端（BFF） | 已实现 M0 骨架 | Dashboard 取数聚合、指数看板 API、静态托管、Agent SSE 代理，不做金融计算 |
| CLI | 冻结维护 | 已有 `fund-advisor chat/ask` 保留兼容和调试，不继续扩展 |
| 组合分析 / 回测 / 自动提醒 | 后续扩展 | 等单标的数据分析稳定后再评估 |

> MCP、Agent API 和 Web 的包、依赖、配置、入口与测试接线已完成。Compose 包含 Go 网页
> 后端、Agent API、Fund MCP 和 Web MCP 四个运行服务；对外仅暴露 Go 网页后端，Agent API
> 与两个 MCP 仅在容器网络内可达。网页后端用 Go（BFF），Agent、MCP 和 Skill 保留 Python，
> 边界见 [Go/Python 透传契约](docs/GO_PYTHON_CONTRACT.md)。Go BFF 已实现指数看板取数
> （`GET /api/dashboard/indices` 及指数详情）和 Agent SSE 反向代理，数据工作台前端页面待建。
> A 股 `stock_valuation` 由 MCP 和 LangGraph Agent 暴露，Skill CLI 仍不增加重复子命令。

## 核心工程设计

```text
React Web
  -> Go 网页后端（BFF；对外唯一入口）
       - 静态托管 React 产物
       - 数据路径：作为 MCP Client 聚合指数看板，原样透传 ToolEnvelope
       - Agent 路径：SSE 反向代理，不做金融计算
  -> Agent API
       - SSE 节点进度
       - 有界临时会话
  -> LangGraph Agent
       - 固定 StateGraph
       - 规则优先识别问题
       - 代码白名单选择工具
       - 关联已审计工具结果
       - 校验事实、关联和限制
  -> MCP
       - 强类型参数
       - 超时、缓存和错误语义
       - 原样透传审计字段
  -> AKShare Skill
       - 实体解析
       - Schema / 时效校验
       - frame_sha256 审计
       - 确定性指标计算
```

市场事实只能来自通过审计的 Skill/MCP 结果。Go 网页后端只做取数聚合、静态托管和 SSE
代理，不重算或改写任何市场数值。Web 内容固定
`numeric_allowed=false`，不能覆盖净值、价格、PE、PB、收益率、回撤、交易状态或
实体存在性。

## 已实现的数据分析

- 基金：历史收益、年化波动、下行波动、最大回撤、修复日期、最长水下期、月度收益统计。
- 产品：基金类型、经理、费用、规模、资产配置、评级、可用时的持仓集中度。
- ETF/LOF：历史价格或净值、实时价格、IOPV、统一方向的溢价率。
- 指数：PE TTM、PB、历史分位和专业终端式历史双图数据，信息组织参考 Wind 深度资料。
- A 股：PE TTM、PB 与前复权价格历史曲线，三者独立展示。
- 比较：两到五只基金的同口径比较和不可比提示。
- Web 背景：单标分析同步检索公开研究文章、财经媒体和博主/社区链接，来源分类不作身份认证。
- 审计：接口、参数、字段、行数、数据日期、内容指纹和失败语义。

## LangGraph Agent 的关联说明

LangGraph Agent 只在已审计结果之间做可验证的关联说明，例如：

- 基金历史回撤较大，同时股票仓位较高：说明两项事实同时存在，不宣称后者必然导致前者。
- ETF 价格上涨且溢价扩大：提示场内追价风险，不等于基金本身高估。
- 指数 PE 分位较高但 PB 分位中性：分别解释盈利估值与净资产估值，禁止合成总分。
- 个股价格接近区间高位且 PE 分位较高：描述历史位置，不预测后续涨跌。
- 两只基金收益差异明显但产品类型或基准不同：先提示不可直接归因于管理能力。

每条说明必须绑定输入工具、字段、数据日期和限制条件。

启用 Web Research 后，基金和股票单标分析会在市场工具之外追加两次可选搜索，分别覆盖
研究/媒体文章和博主/社区观点。搜索结果只展示标题、链接、域名和来源类别；网页摘要中的
数字不能成为市场事实，Web 失败也不能改变 Fund MCP 的错误语义。

## 稳定运行入口

项目以 Docker 为准运行。完整容器编排一键拉起 Go 网页后端、Agent API、Fund MCP 和
Web MCP：

```bash
docker compose -f deploy/compose/compose.yaml up --build -d
```

对外只暴露 Go 网页后端，默认地址 `http://127.0.0.1:8080`；Agent API 与两个 MCP 仅在
容器网络内可达。Go 网页后端提供指数看板取数（`GET /api/dashboard/indices`）并把
`/api/chat/stream` 等 Agent 请求反向代理到 Python Agent API。Web 会话只保存在 Agent API
进程内，不写数据库；页面刷新、会话过期或服务重启后可以清空。
若宿主机 `8080` 已占用，可用
`FUND_ADVISOR_PORT=8090 docker compose -f deploy/compose/compose.yaml up -d` 覆盖映射端口。

验证在容器内执行 Ruff 和全量 Pytest（Python），以及 `go vet` 和 Go 单元测试：

```bash
# Python：Skill、MCP、Agent、App 回归
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test

# Go：网页后端（BFF）单元测试与静态检查
docker run --rm -v "$PWD/web-backend":/src -w /src golang:1.22-alpine \
  sh -c "go vet ./... && go test ./..."
```

### 可选：本地调试环境

以下入口仅用于本地调试，不是产品运行形态。Skill 数据层可独立运行：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
bash "$SKILL_DIR/scripts/setup.sh"

bash "$SKILL_DIR/scripts/run.sh" search --query "沪深300"
bash "$SKILL_DIR/scripts/run.sh" analyze --fund "510300" --years 3
bash "$SKILL_DIR/scripts/run.sh" valuation --index "沪深300" --years 10
bash "$SKILL_DIR/scripts/run.sh" compare --funds "000001" "110022" --years 3
bash "$SKILL_DIR/scripts/run.sh" audit
```

完整命令见 [Skill 使用说明](skills/akshare-fund-advisor/USAGE.md)。

LangGraph Agent 和 Agent API 的本地调试需先创建 `.venv-agent`（未纳入版本控制）：

```bash
python3.11 -m venv .venv-agent
.venv-agent/bin/python -m pip install -r requirements.txt
.venv-agent/bin/python -m pip install --no-deps -e .

# 单轮调试
.venv-agent/bin/fund-advisor-agent ask \
  --question "沪深300指数估值" \
  --output text

# Agent API 同源托管已构建的 React 页面
.venv-agent/bin/fund-advisor-api
```

前端开发：

```bash
cd web
npm install
npm run dev
```

## 目录结构

```text
.
├── docs/                              # 架构、错误语义和任务文档
├── src/                               # 仓库级源码根（顺依赖方向）
│   ├── fund_advisor_agent/            # LangGraph 固定状态图与响应门禁
│   ├── fund_advisor_app/              # Agent API、临时会话与兼容 CLI
│   └── fund_advisor_mcp/
│       ├── fund/                      # 市场事实 MCP
│       └── web/                       # 外部背景 MCP
├── web/                               # React 对话页
├── web-backend/                       # Go 网页后端（BFF）：取数聚合、静态托管、SSE 代理
│   ├── cmd/server/                    # HTTP 入口与路由
│   └── internal/                      # mcp / dashboard / proxy / static
├── skills/akshare-fund-advisor/       # 纯数据层：可独立拷贝
│   ├── scripts/fund_advisor.py        # 数据访问、校验、指标和规则
│   ├── references/                    # 接口和指标口径
│   └── tests/                         # Skill 回归测试
├── tests/                             # App、MCP、Web 与 LangGraph 图级测试
└── deploy/                            # Go 网页后端、Agent API 与两个 MCP 的 Docker Compose
```

## 当前优先任务

1. [投研数据工作台](docs/tasks/TASK_research_dashboard.md) 是下一阶段主任务，先实现 Dashboard
   契约和指数估值看板，再推进标的详情、总览和页面上下文 Agent。
2. [基金与股票候选筛选](docs/tasks/TASK_asset_screening.md) 已完成 AKShare 接口审计；
   `fund_screen`、`stock_screen` 完成后再接入工作台候选模块。
3. [基金与个股数据分析处理](docs/tasks/TASK_fund_stock_data_analysis.md) 已完成当前任务清单。
4. [LangGraph Agent](docs/tasks/TASK_langgraph_agent.md) 已完成核心实现与 Docker 验证。
5. [Web 与 CLI 历史任务](docs/tasks/TASK_web_cli_product.md) 已完成；CLI 后续冻结维护，
   产品能力只在 Web 推进。
6. 保持 Ark 结构化模型和金融门禁回归稳定。
7. [组合分析](docs/tasks/TASK_portfolio_analysis.md) 保留为后续扩展。

## 文档

- [产品简述（与 AI 讨论产品时先看）](docs/PRODUCT.md)
- [文档索引](docs/README.md)
- [高层设计](docs/HLD.md)
- [低层设计](docs/LLD.md)
- [Go/Python 透传契约](docs/GO_PYTHON_CONTRACT.md)
- [错误处理](docs/ERROR_HANDLING.md)
- [Web Research MCP](docs/WEB_RESEARCH_MCP.md)
- [投研数据工作台任务](docs/tasks/TASK_research_dashboard.md)
- [候选筛选任务](docs/tasks/TASK_asset_screening.md)
- [LangGraph Agent 任务](docs/tasks/TASK_langgraph_agent.md)
- [Web 与 CLI 历史任务](docs/tasks/TASK_web_cli_product.md)
- [Skill 入口](skills/akshare-fund-advisor/SKILL.md)
- [Skill 内部设计](skills/akshare-fund-advisor/DESIGN.md)

## 边界

本项目仅用于金融信息分析和个人研究参考，不构成投资建议，不执行交易，不承诺收益。
历史统计和关联说明不代表因果关系，也不代表未来表现。
