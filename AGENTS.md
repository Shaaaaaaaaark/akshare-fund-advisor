# Repository Agent Guide

本文件适用于整个仓库，供代码助手、自动化 Agent 和贡献者在修改项目时遵循。
`skills/akshare-fund-advisor/SKILL.md` 对 Skill 内金融数据处理有更严格的要求；
修改 Skill 时必须同时遵守两份文件。

## 项目目标

本项目是面向中国基金、指数和 A 股研究的专业 Agent，产品形态参考 Wind、
同花顺等金融终端的对话研究能力，但不复制其品牌或商业数据。

核心目标：

- 市场事实可验证、可追溯。
- 不存在、歧义、过期和上游失败必须明确区分。
- 大模型只参与受限语言任务，不成为金融事实源。
- 同一对话可承接上下文，不做跨对话全局记忆。
- 面向个人 Docker Compose 部署，同时保持可扩展的工程边界。

## 事实来源优先级

从高到低：

1. 通过 Schema、时效和 `frame_sha256` 审计的 AKShare MCP 工具结果。
2. 带来源、版本和页码的官方文档 Evidence。
3. Web 通道提供的非数值背景信息。
4. 模型常识不得作为基金、股票、指数或市场数值的事实来源。

以下内容只能来自通过审计的工具结果：

- 基金净值、ETF/股票价格、指数点位。
- PE、PB、收益率、波动率、回撤和历史分位。
- 申购、赎回、限额、交易状态和数据日期。
- 基金、股票和指数是否存在以及规范代码。

模型不得生成、补齐、插值、前向填充、修复或改写上述内容。

## 实体与错误语义

实体候选不等于实体已确认。基金、股票和指数必须由 Skill 或工具目录解析。

必须区分：

- `NOT_FOUND`：目录查询成功，但没有该实体。
- `AMBIGUOUS`：存在多个候选，需要用户确认。
- `UNSUPPORTED`：实体可能存在，但当前市场或数据接口不支持。
- `UPSTREAM_ERROR`：数据源失败，无法判断实体是否存在。
- `STALE_DATA`：数据存在但时效不满足使用要求。

上游失败时只能回答“当前无法确认”，不得回答“该标的不存在”。无有效 Evidence
时不得生成事实、图表或投资结论。

## 架构边界

- `orchestration/`：意图、状态机和工具白名单，不直接查询行情。
- `mcp_server/`：参数校验、超时、缓存和 `ToolEnvelope`，不改写金融数值。
- `skills/akshare-fund-advisor/`：AKShare 调用、实体解析、确定性计算和数据审计。
- `evidence/`：Evidence、Claim、门禁、确定性渲染和最终响应校验。
- `rag/`：官方文档、指定文档和 Web 背景检索，不覆盖市场事实。
- `portfolio/`：使用 `Decimal` 计算组合指标，并在外发模型前脱敏。
- `web/`：只消费 API 返回的数据，不从模型文本解析图表数值。

依赖方向应保持：

```text
API/Web -> Orchestration -> MCP -> Skill
                    |
                    +-> RAG -> Evidence -> Claim -> Renderer
```

## Prompt 规则

生产 Prompt 统一定义在 `src/financial_agent/prompts/`，业务节点不得新增内联
system prompt。

修改 Prompt 时必须：

1. 更新对应 `*_PROMPT_VERSION`。
2. 保持结构化输出字段与 Pydantic Schema 一致。
3. 不把代码门禁迁移成纯文本约束。
4. 增加或更新 Prompt 契约测试。
5. 在 `docs/PROMPT_DESIGN.md` 记录职责或安全边界变化。

Prompt 可以限制模型行为，但不能负责数据真实性、时效、权限和数值一致性。

## 配置与密钥

- 所有自定义配置进入 `config/config.example.yaml` 和 Pydantic 配置模型。
- 真实密钥只能写入被忽略的 `config/config.local.yaml` 或环境变量。
- 不提交 API Key、Token、个人持仓、原始私有文档和生产数据库快照。
- 日志默认不记录 Prompt、模型响应、完整持仓或密钥。

## 代码修改原则

- 优先复用现有模块、Schema 和错误模型。
- 金融计算使用确定性函数；金额和仓位计算使用 `Decimal`。
- 新增工具必须同时更新 MCP Schema、Adapter、Server、工具发现数量和测试。
- 新增市场数值必须提供来源接口、字段口径、时效规则和审计记录。
- 不在前端、Prompt 或报告文本中复制一套金融计算。
- 不顺手重构无关模块，不覆盖用户未提交的修改。

## 验证要求

默认在 Docker 中验证：

```bash
docker compose -f deploy/compose/compose.yaml \
  --profile test run --rm --build test
```

涉及运行链路时还要检查：

```bash
docker compose -f deploy/compose/compose.yaml up -d --build
curl -fsS http://127.0.0.1:8000/health/ready
```

按改动风险补充验证：

- 意图或规划：工具路由评测。
- MCP 或 Skill：真实 AKShare 冒烟测试和 `data_audit`。
- Evidence 或报告：数值忠实度、D/E 级无事实测试。
- 会话：同对话承接和新对话隔离。
- 前端：固定图表、空状态、PE/PB 切换和浏览器控制台。

## 文档同步

文档入口见 `docs/README.md`。出现以下变更时必须同步文档：

- 架构和职责变化：`docs/HLD.md`、`docs/LLD.md`。
- Prompt 变化：`docs/PROMPT_DESIGN.md`。
- 错误码或降级变化：`docs/ERROR_HANDLING.md`。
- 配置、启动命令或目录变化：`README.md`。
- Skill 接口和指标变化：Skill 目录下的 `references/`。

