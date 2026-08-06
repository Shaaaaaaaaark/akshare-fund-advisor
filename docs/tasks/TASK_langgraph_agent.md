# TASK：最小 LangGraph 金融数据分析 Agent

> 状态：`已完成：核心实现、测试、Docker 闭环与真实结构化模型验证均通过`
>
> 前置 1：已完成 [基金与个股数据分析任务](TASK_fund_stock_data_analysis.md) 的阶段 0。
>
> 前置 2：单标数据增强已完成，MCP/`ToolEnvelope` 契约已冻结。

## 1. 目标

实现一个面向单轮研究问题的受控 LangGraph Agent：

- 识别基金、指数、ETF、A 股和外部背景问题；
- 只规划已注册的 MCP 工具；
- 校验工具结果、审计、时效、数据策略和错误语义；
- 对多个已审计事实生成带引用的非因果关联说明；
- 确定性渲染事实、关联、限制和条件式参考；
- 阻止无来源数字、Web 市场数字、无证据因果和确定性交易指令。

目标是展示 LangGraph、MCP、结构化输出和代码门禁的工程闭环，不追求自治程度。

## 2. 非目标

- 不使用 LangChain AgentExecutor、ReAct 或动态工具规划；
- 不使用 LangChain Memory、数据库 checkpoint 或跨会话记忆；
- 不使用多 Agent、SubAgent 或自治反思循环；
- 不引入 RAG、向量库或固定文档知识库；
- 不实现 FastAPI、Web UI、任务队列或长期任务；
- 不实现组合分析、回测、收益预测或自动交易。

## 3. 固定状态图

```text
START
  -> CLASSIFY
  -> PLAN_REGISTERED_TOOLS
  -> CALL_MCP
  -> VALIDATE_TOOL_ENVELOPES
  -> BUILD_ASSOCIATIONS
  -> VALIDATE_RESPONSE
  -> RENDER_ANSWER
  -> END
```

终止分支：

```text
AMBIGUOUS       -> need_clarification
NOT_FOUND       -> not_found
UNSUPPORTED     -> unsupported
UPSTREAM_ERROR  -> cannot_confirm
STALE_DATA      -> stale_data
VALIDATION_FAIL -> failed
```

图保持无环。模型不能增加节点、边、工具或重试次数。

## 4. 阶段 A：依赖与包结构

- [x] 删除旧架构遗留的宽松 `langgraph>=0.2.0` 声明。
- [x] 选择并锁定验证过的 LangGraph 1.x 版本。
- [x] 不安装 `langchain` 聚合包。
- [x] 仅在 LangGraph 或消息接口确有需要时保留 `langchain-core`。
- [x] 选择并锁定一个 OpenAI-compatible 模型 SDK；首版不引入 LiteLLM。
- [x] 新增命令入口 `fund-advisor-agent`，但不恢复旧 `financial-agent` API 入口。
- [x] 新增包：

```text
src/fund_advisor_agent/
├── __init__.py
├── state.py
├── graph.py
├── nodes.py
├── policies.py
├── associations.py
├── validator.py
├── renderer.py
├── model_client.py
├── prompts.py
└── cli.py
```

## 5. 阶段 B：核心 Schema

- [x] 定义 `Intent`：
  - `FUND_SEARCH`
  - `FUND_ANALYSIS`
  - `FUND_STATUS`
  - `FUND_COMPARE`
  - `INDEX_VALUATION`
  - `STOCK_VALUATION`
  - `WEB_RESEARCH`
  - `DOCUMENT_READ`
  - `UNSUPPORTED`
- [x] 定义 `AgentStatus`：
  - `running`
  - `need_clarification`
  - `not_found`
  - `unsupported`
  - `cannot_confirm`
  - `stale_data`
  - `partial_result`
  - `completed`
  - `failed`
- [x] 定义 `ToolCallSpec`，工具名必须是枚举，不接受任意字符串。
- [x] 定义 `FactRef`：
  - `fact_id`
  - `tool`
  - `field_path`
  - `value`
  - `unit`
  - `as_of`
  - `audit_ref`
- [x] 定义 `AssociationDraft`：
  - `evidence_refs`，至少两个 `fact_id`
  - `relationship`
  - `explanation`
  - `causal_claim: Literal[False]`
  - `confidence`
- [x] 定义 Pydantic `AgentState` 和最终 `AgentResponse`。
- [x] 所有 Schema 使用 `extra="forbid"`。

## 6. 阶段 C：MCP Client 边界

- [x] 定义 transport-neutral `McpToolClient` Protocol。
- [x] 复用 Web MCP Client，并实现同契约的 Fund MCP Client。
- [x] 本地 CLI 默认使用 stdio；HTTP 作为后续 Docker 传输。
- [x] Agent 不得直接 import 或实例化 `FundAdvisor`。
- [x] `CALL_MCP` 只保存完整 `ToolEnvelope`，不只保存 `data`。
- [x] 测试使用 Fake MCP Client，不访问 AKShare 或公网。
- [x] MCP Client 保留：
  - `request_id`
  - `sources`
  - `data_audit`
  - `data_warnings`
  - `data_policy`
  - `queried_at`
  - `error`

## 7. 阶段 D：节点和条件边

### `CLASSIFY`

- [x] 规则优先识别意图和显式代码。
- [x] 低置信度时才允许模型返回结构化候选。
- [x] 模型候选不能确认实体存在。

### `PLAN_REGISTERED_TOOLS`

- [x] 建立 `Intent -> ToolName[]` 代码白名单。
- [x] 校验参数范围和工具调用数量。
- [x] 拒绝模型产生的未知工具名。

### `CALL_MCP`

- [x] 按计划调用 Fund/Web MCP Client。
- [x] 保持调用幂等并记录调用顺序。
- [x] 不在节点内重算或修改金融值。

### `VALIDATE_TOOL_ENVELOPES`

- [x] 校验 `ok`、`error`、审计、时效、warning 和数据策略。
- [x] 将具体错误码映射为统一错误语义和 `AgentStatus`。
- [x] 只从成功且允许使用的字段构造 `FactRef`。
- [x] Web 结果固定不能构造市场数值 `FactRef`。

### `BUILD_ASSOCIATIONS`

- [x] 只接收问题、允许的 `FactRef` 和必要的非数值元数据。
- [x] 只输出 `AssociationDraft`。
- [x] 模型失败时返回空关联列表，不影响事实报告。

### `VALIDATE_RESPONSE`

- [x] 验证所有 `evidence_refs` 存在且可用。
- [x] 验证至少引用两个事实字段。
- [x] 拦截未授权数字、确定性因果词和交易指令。
- [x] 拦截 PE/PB 综合分、净值低位等于低估等概念错误。

### `RENDER_ANSWER`

- [x] 从 `FactRef` 确定性注入数值、单位和日期。
- [x] 固定输出：事实、关联说明、限制、条件式参考。
- [x] 错误终止状态使用固定模板，不调用模型润色。

## 8. 阶段 E：模型协议与 Prompt

- [x] 定义 `AssociationModel` Protocol：

```text
build_associations(facts, question) -> list[AssociationDraft]
```

- [x] 生产实现只接一个 OpenAI-compatible 模型。
- [x] 模型请求设置超时和最大输出长度。
- [x] 使用 Pydantic 结构化输出，不解析自由文本 JSON。
- [x] 在 `prompts.py` 定义 `ASSOCIATION_PROMPT_VERSION`。
- [x] Prompt 只负责语言和结构，不负责真实性、时效或数值校验。
- [x] 模型输入不包含 API Key、完整配置或无关工具原始响应。
- [x] 模型输出失败时回退为确定性事实报告。

## 9. 阶段 F：CLI

- [x] 实现：

```bash
fund-advisor-agent ask --question "分析 510300 的风险和估值"
```

- [x] 支持 `--output text|json`。
- [x] JSON 输出包含：
  - `status`
  - `facts`
  - `associations`
  - `limitations`
  - `warnings`
  - `answer`
- [x] CLI 只执行单轮 `graph.ainvoke()`。
- [x] 不增加会话数据库、后台任务或 HTTP API。

## 10. 阶段 G：测试

### Schema 和节点

- [x] `AgentState`、`ToolCallSpec`、`FactRef`、`AssociationDraft` 边界测试。
- [x] 每个节点使用固定输入独立测试。
- [x] 节点只能返回声明过的状态字段。

### 条件边

- [x] `AMBIGUOUS -> need_clarification`。
- [x] `NOT_FOUND -> not_found`。
- [x] `UNSUPPORTED -> unsupported`。
- [x] `UPSTREAM_ERROR -> cannot_confirm`。
- [x] `STALE_DATA -> stale_data`。
- [x] 非关键 warning -> `partial_result`。

### 工具和金融门禁

- [x] 意图到工具白名单。
- [x] 未注册工具名被拒绝。
- [x] 市场数字逐项来自 `FactRef`。
- [x] Web 数字不能进入市场事实。
- [x] PE/PB 单侧失败不互相替代。
- [x] 基金净值位置不被写成估值。
- [x] 工具失败不被写成实体不存在。

### 关联和输出

- [x] 关联至少引用两个事实。
- [x] 不存在的 `fact_id` 被拒绝。
- [x] `causal_claim=true` 被 Schema 拒绝。
- [x] 无证据因果表达被阻断。
- [x] 确定性买卖指令被阻断。
- [x] 模型超时、非法结构和空结果都回退事实报告。
- [x] Fake Model + Fake MCP 完整图快照。
- [x] 图无环，所有路径在有限步骤内结束。

## 11. 验收标准

- [x] `fund-advisor-agent ask` 可处理基金、指数、个股和比较问题。
- [x] 至少覆盖一条成功、一条部分成功和五类错误语义路径。
- [x] 回答中的每个市场数字都能反查 `tool + field_path + audit_ref`。
- [x] Web 内容不能覆盖市场事实。
- [x] 模型不可创建工具、修改状态或绕过门禁。
- [x] 关联说明不生成因果、未来收益概率或确定性交易指令。
- [x] Agent 单元测试和图级测试全绿。
- [x] Fund/Web MCP 契约测试保持全绿。
- [x] README、HLD、LLD、ERROR_HANDLING 和 SECURITY 与实现一致。

环境验证：

- [x] Docker 镜像构建、容器内测试、两个 MCP 服务健康检查和 HTTP 工具发现。
- [x] 使用真实 OpenAI-compatible Ark 配置验证 Pydantic 结构化关联输出。

## 12. 后续触发条件

只有出现以下需求时才扩展 LangGraph：

- 需要跨请求恢复时，再评估 checkpointer；
- 需要多用户会话时，再评估数据库；
- 单次任务持续时间明显增长时，再评估任务队列；
- 同时接入两个以上模型供应商时，再评估 LiteLLM；
- 出现真正独立且可并行的专业任务时，再评估 SubAgent。
