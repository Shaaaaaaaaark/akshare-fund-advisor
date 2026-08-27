# Roadmap

本文只维护实现状态和后续顺序。架构和协议见
[ARCHITECTURE.md](ARCHITECTURE.md)。

## 当前状态

| 能力 | 状态 |
| --- | --- |
| Agent Skill 包装 | 已实现 |
| `data_core` | 已建立，`fund_search`、`fund_status` 已迁移 |
| Data API | 已实现 |
| Fund MCP / Web MCP | 已实现 |
| Fixed LangGraph Agent | 已实现 |
| FastAPI Agent API / SSE / 有界临时会话 | 已实现 |
| Java BFF | 已实现，替换原 Go BFF，保持外部 HTTP/SSE 契约 |
| React 总览、指数、ETF、主动基金、股票和 Agent 页 | MVP 已实现 |
| Pi-style Agent Harness | 设计完成，尚未实现 |
| `fund_screen` / `stock_screen` | 接口审计完成，工具未实现 |
| 研究动态 / 通用 `PageContext` | 未实现 |

## 当前优先级

### P0：稳定 Java BFF

`web-backend/` 已切换为 Java 21 + Spring Boot WebFlux，后续只保留该实现：

1. 保持 Dashboard、SSE、静态资源和错误契约与迁移前兼容；
2. 保持 Data API `WebClient`、完整 `ToolEnvelope` 原样透传和全局并发 Bulkhead；
3. 保持 Overview、Index、ETF、主动基金和股票接口稳定；
4. 保持 Agent SSE 流式代理、SPA fallback 和 `/health`；
5. 持续用 Maven `verify`、Compose 测试和 Web/API 黑盒闭环验证。

主干不保留 Go/Java 双栈，不改变前端 API 或 Python 服务契约。

### P1：保持 MVP 稳定

- 保持 Web、Java BFF、Data API、MCP、LangGraph 和 Ark 结构化调用回归稳定；
- 保持非法参数返回 4xx；
- 保持普通 Dashboard 请求 100 秒、聚合请求 200 秒的前后端预算关系；
- 保持 Dashboard 和 Agent 两条链路独立。

### P2：收敛数据核心

按页面价值和复用程度把 legacy Skill 数据逻辑迁移到 `data_core`：

1. `fund_analyze`
2. `fund_profile`
3. `fund_rating`
4. `index_valuation`
5. `etf_dashboard`
6. `stock_valuation`

每次迁移必须同步 Schema、Adapter、Data API/MCP、审计哈希和测试，不能改变现有接口。

### P3：候选筛选

1. 定义 `fund_screen`、`stock_screen` 输入输出 Schema；
2. 只使用已审计的财务、行业和基金质量接口；
3. 使用确定性规则生成候选，不让模型决定金融分数；
4. 工具稳定后接入 Fund MCP、Agent 和 Dashboard；
5. 未实现前继续返回 `not_implemented`，不返回空候选冒充成功。

### P4：精简 Agent Harness

参考 Pi 的分层思想，但继续使用 Python 和现有固定 LangGraph：

1. 完成 Run/Event/Tool 协议；
2. 实现 Tool Registry、`before_tool_call` 和 `after_tool_call`；
3. 实现 Evidence Ledger 和 Final Answer Gate；
4. 实现有界上下文压缩，不把摘要升级为市场事实；
5. 用 Fake Model 覆盖工具成功、歧义、过期和上游失败；
6. 用 Runtime Adapter 包装现有 Agent API，再考虑替换旧入口。

Redis、异步队列和 gRPC 不属于当前阶段。

### P5：产品增强

- 研究动态；
- 通用 `PageContext`；
- 主动基金页内 Agent 抽屉；
- ETF/基金净值和指数的更多交叉校验。

## 暂不立项

- 组合分析和回测；
- 自动交易和收益预测；
- PostgreSQL、Redis、Elasticsearch；
- RAG、向量库、多 Agent 和跨会话长期记忆；
- Kafka、NATS、RabbitMQ 等消息队列。

## 完成标准

任何新市场能力都必须满足：

1. 数据可追溯到明确接口、日期、字段和 `frame_sha256`；
2. `NOT_FOUND`、`AMBIGUOUS`、`UNSUPPORTED`、`UPSTREAM_ERROR`、
   `STALE_DATA` 语义稳定；
3. Java BFF 和 React 不重算、不补点、不改写数值；
4. Agent 最终结论只引用通过门禁的事实；
5. Docker 中 Ruff、Pytest 和 Maven `verify` 通过；
6. 涉及部署时完成五服务和 Web/API 黑盒闭环。
