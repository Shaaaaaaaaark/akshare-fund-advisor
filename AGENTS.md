# Repository Agent Guide

本文件适用于整个仓库。修改 Skill 时还必须遵守
`skills/akshare-fund-advisor/SKILL.md`。

## 项目方向

项目首先用于面试展示可信 Agent 工程，同时提供基金、指数、ETF 和 A 股数据分析供个人
研究参考。

当前优先级：

1. 按已审计接口推进基金与股票候选筛选；
2. 完善基金、指数和个股数据分析；
3. 保持 MCP、LangGraph、金融门禁和 Ark 结构化模型回归稳定。

当前不优先：

- 组合分析和回测；
- FastAPI/Web UI；
- PostgreSQL、Redis、Elasticsearch；
- 多 Agent、RAG、向量库和长期记忆；
- 自动交易和收益预测。

## 实现状态

- Skill CLI 已实现，是当前稳定运行入口。
- Fund MCP 和 Web MCP 的命名空间、入口、配置和测试接线已完成。
- LangGraph Agent 固定图、MCP Client、FactRef、关联说明、门禁和 CLI 已实现。
- Compose 已收敛为两个 MCP 服务；镜像、容器测试、健康检查、HTTP 工具发现和 Agent
  容器闭环已验证。
- Ark thinking 模型的 Pydantic 结构化关联输出和门禁闭环已验证。
- 基金和股票单标分析已接入研究/媒体文章与博主/社区公开链接的可选 Web 搜索。
- 财务、行业和基金质量候选接口审计已完成；`stock_screen`、`fund_screen` 尚未实现。

不得把后续组合能力写成“已实现”。

## 事实来源

优先级从高到低：

1. 通过 Schema、时效和 `frame_sha256` 审计的 AKShare Skill / Fund MCP；
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
LangGraph Agent
  -> MCP
     -> AKShare Skill
```

- `skills/akshare-fund-advisor/scripts/fund_advisor.py`：实体解析、AKShare 调用、确定性指标和审计。
- `src/fund_advisor_mcp/fund/`：市场事实 MCP，不改写 Skill 数值。
- `src/fund_advisor_mcp/web/`：非数值背景 MCP，固定 `numeric_allowed=false`。
- `src/fund_advisor_agent/`：只做固定图编排、工具路由、关联说明和输出校验。

源码层级顺依赖方向：仓库级 `src/` 存放 Agent 与 MCP，`skills/akshare-fund-advisor/`
回归纯数据层（SKILL.md + scripts + references），可独立拷贝。

LangGraph 只使用 `StateGraph` 和显式条件边。不得恢复 LangChain Agent、开放式 ReAct、
动态工具规划、数据库 checkpoint、长期记忆或多 Agent。

## Agent 关联说明

Agent 可以解释多个工具事实如何共同影响研究理解，但必须：

- 每条关联引用具体工具和字段；
- 区分事实、关联和限制；
- 明确相关性不等于因果；
- 不从历史统计预测未来收益；
- 不把净值位置写成估值；
- 不把 PE/PB 合成综合分；
- 不输出确定性交易指令。

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

当前稳定验证入口：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
.venv-agent/bin/python -m ruff check --no-cache .
.venv-agent/bin/python -m pytest -q -p no:cacheprovider
AKSHARE_FUND_VENV="$PWD/.venv-agent" bash "$SKILL_DIR/scripts/run.sh" audit
```

Docker 相关改动仍须重新运行 Compose 测试、两个 MCP 服务健康检查和 HTTP 工具发现。

## 文档同步

- 产品方向或架构：`README.md`、`docs/HLD.md`、`docs/LLD.md`
- 错误语义：`docs/ERROR_HANDLING.md`
- Web MCP：`docs/WEB_RESEARCH_MCP.md`
- Skill 接口和指标：Skill 目录及 `references/`
- 实施优先级：`docs/tasks/`
