# AKShare Financial Research Agent

面向中国基金、ETF、指数和 A 股研究的可信投研数据工作台，也是用于展示受控 Agent
工程能力的项目。

项目不预测涨跌、不荐股、不执行交易。金融数值只能来自经过 Schema、时效和
`frame_sha256` 审计的 AKShare 数据；模型只解释已验证事实。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| AKShare Skill | 已实现 | 实体解析、接口调用、确定性指标和审计 |
| Fund Advisor MCP | 已实现 | 九个市场事实工具 |
| Web Research MCP | 已实现 | 三个非数值背景工具 |
| LangGraph Agent | 已实现 | 固定图、工具白名单、FactRef、结构化研究综合和门禁 |
| Agent API | 已实现 | FastAPI、SSE 和有界进程内会话 |
| React Web | 基础入口已实现 | 当前是对话页，数据工作台页面待开发 |
| Go 网页后端 | M0 已实现 | 对外入口、指数 API、静态托管和 Agent SSE 代理 |
| CLI | 冻结维护 | 只保留兼容和调试，不再增加产品功能 |

当前开发重点是完成指数估值看板前端，再推进基金、股票、研究动态和页面上下文 Agent。
具体进度以 [投研数据工作台任务](docs/tasks/TASK_research_dashboard.md) 为准。

## 架构

```text
React Web
  -> Go 网页后端（对外唯一 HTTP 入口）
     |-- Dashboard 数据请求 -> Fund MCP (Python) -> AKShare Skill
     `-- Agent SSE 代理 -> Agent API (Python) -> LangGraph -> MCP -> Skill
```

职责边界：

- **Skill**：获取 AKShare 数据，执行确定性金融计算和审计。
- **Fund MCP**：提供强类型工具、超时、缓存和 `ToolEnvelope`，不改写 Skill 数值。
- **Web MCP**：提供非数值背景，固定 `numeric_allowed=false`。
- **Agent**：执行固定研究流程、错误分支和输出门禁。
- **Go 网页后端**：取数聚合、静态托管和 SSE 代理，不做金融计算。
- **React**：渲染结构化数据和 Agent 结果，不生成市场事实。

详细边界见 [HLD](docs/HLD.md) 和
[Go/Python 透传契约](docs/GO_PYTHON_CONTRACT.md)。

## 已实现能力

- 基金搜索、产品档案、评级、申赎状态、历史收益、波动和回撤。
- ETF/LOF 历史价格或净值、实时价格、IOPV 和统一方向的溢价率。
- 指数 PE TTM、PB、历史分位和历史曲线数据。
- A 股 PE TTM、PB 和前复权价格历史曲线。
- 两到五只基金的同口径比较和不可比提示。
- 公开研究文章、财经媒体和社区链接的非数值背景搜索。
- 固定 LangGraph 研究流程、事实引用、关联说明和响应门禁。
- Go Dashboard 指数列表与详情 API：
  - `GET /api/dashboard/indices`
  - `GET /api/dashboard/indices/{index}`

数据 API 已可用，但指数看板和 PE/PB 历史双图前端尚未实现。

## Docker 运行

项目以 Docker 为准运行：

```bash
docker compose -f deploy/compose/compose.yaml up --build -d
```

默认入口：

```text
http://127.0.0.1:8080
```

若端口被占用：

```bash
FUND_ADVISOR_PORT=8090 \
  docker compose -f deploy/compose/compose.yaml up --build -d
```

Compose 包含四个服务：

```text
web-backend       # Go，对外暴露
agent-api         # Python，仅容器网络
fund-advisor-mcp  # Python，仅容器网络
web-research-mcp  # Python，仅容器网络
```

## 验证

Python 全量检查：

```bash
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test
```

Go 检查：

```bash
docker run --rm -v "$PWD/web-backend":/src -w /src golang:1.22-alpine \
  sh -c "gofmt -l . && go vet ./... && go test ./..."
```

Docker 相关变更还需验证四个服务健康、MCP 工具发现、Dashboard 取数和 Agent SSE 闭环。

## 当前任务

1. [投研数据工作台](docs/tasks/TASK_research_dashboard.md)：当前主任务，下一批交付指数
   看板和 PE/PB 历史双图。
2. [数据源交叉校验审计](docs/tasks/TASK_data_source_cross_validation.md)：审计
   Baostock、efinance 等免费源是否适合作为 AKShare 主源的校验源。
3. [基金与股票候选筛选](docs/tasks/TASK_asset_screening.md)：接口审计已完成，待工作台
   基础页面稳定后实现 `fund_screen` 和 `stock_screen`。

组合分析、回测、数据库、Redis、RAG、多 Agent 和自动交易当前不立项。

## 文档

- [产品范围](docs/PRODUCT.md)
- [系统架构](docs/HLD.md)
- [Go/Python 透传契约](docs/GO_PYTHON_CONTRACT.md)
- [错误语义](docs/ERROR_HANDLING.md)
- [Web Research MCP](docs/WEB_RESEARCH_MCP.md)
- [文档索引](docs/README.md)
- [Skill 使用与数据口径](skills/akshare-fund-advisor/README.md)

## 免责声明

本项目仅用于金融信息分析和个人研究参考，不构成投资建议。历史统计和关联说明不代表
因果关系，也不代表未来表现。
