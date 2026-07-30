# 金融投资研究 Agent 低层设计

> 对应高层设计：[HLD.md](HLD.md)
>
> 项目定位：个人自用、GitHub 开源、用于展示 Agent 工程能力的金融研究系统。

## 1. 文档目的

本文把 HLD 中的架构决策细化为可编码、可测试、可审计的模块设计，重点回答四类问题：

1. 每个模块负责什么，不负责什么。
2. 为什么选择当前设计，而不是更复杂或更自由的方案。
3. 使用 FastAPI、LangGraph、MCP、LiteLLM、PostgreSQL、Redis 和 Elasticsearch 时具体怎么落地。
4. 如何通过接口、Schema、失败处理和测试证明金融数据没有被模型编造。

本文既是实现蓝图，也是面试讲解材料。所有章节都会区分“已经实现”和“目标设计”，避免把规划中的能力描述成已完成。

产品形态收敛为 **Agent(LangGraph) + 两个 MCP + Skill**：

- `fund-advisor-mcp`：九个强类型市场事实工具。
- `web-research-mcp`：`web_search` / `web_fetch` / `document_read` 三个工具，提供非数值背景。
- `akshare-fund-advisor` Skill：AKShare 调用、实体解析和确定性计算。

系统不含知识库、向量检索和文档摄取管线；外部文档按需实时读取，不做离线索引。

## 2. 实现状态与阅读约定

### 2.1 状态标记

| 标记 | 含义 |
| --- | --- |
| `已实现` | 仓库中已有可运行代码 |
| `待实现` | 已完成接口和行为设计，但尚无业务实现 |
| `阶段二` | 不阻塞首个可信工具闭环，属于后续增强阶段 |
| `可选` | 只有规模或业务复杂度达到条件后才引入 |

### 2.2 当前实现基线

| 模块 | 状态 | 当前路径 |
| --- | --- | --- |
| AKShare Skill | `已实现` | `skills/akshare-fund-advisor/` |
| 配置加载与 Pydantic 校验 | `已实现` | `src/financial_agent/config/` |
| LiteLLM + DeepSeek API | `已实现` | `src/financial_agent/models/` |
| 模型连通性检查 | `已实现` | `scripts/check_llm.py` |
| Fund Advisor MCP | `已实现` | `src/financial_agent/mcp_server/` |
| Web Research MCP | `已实现，需配置 Key` | `src/financial_agent/web_research/` |
| LangGraph 编排 | `已实现` | `src/financial_agent/orchestration/` |
| Evidence / Claim 门禁 | `已实现` | `src/financial_agent/evidence/` |
| FastAPI | `已实现` | `src/financial_agent/api/` |
| 用户画像与组合 | `已实现` | `src/financial_agent/portfolio/` |
| PostgreSQL / Redis / ES | `已实现，Compose 可启动` | `deploy/compose/` |
| 评测和端到端测试 | `已实现` | `evals/`、`tests/` |

### 2.3 存储职责统一

三类存储职责互不重叠，PostgreSQL 是事实主库：

```text
PostgreSQL
  - 事务主数据（会话、任务、工具调用）
  - Evidence / Claim / 报告
  - 用户风险画像与持仓

Elasticsearch
  - 审计投影（task 状态与可搜索摘要）
  - 报告全文检索
  - 日志与 Trace 关联字段

Redis
  - 短期缓存、限流、任务锁
```

系统不再使用 `pgvector`，也不在任何存储中保存语义向量或文档分块。Elasticsearch 只承担
审计投影和报告检索，不是文档检索集群；其中的数据都能从 PostgreSQL 主库和日志源重建。
Redis 只做缓存与限流，不作为事实唯一存储。

## 3. HLD 到 LLD 的映射

| HLD 章节 | LLD 落地章节 |
| --- | --- |
| 总体架构 | 4、5 |
| Agent 编排 | 8、9、10 |
| MCP 工具 | 7 |
| 证据与反幻觉 | 11、12、13 |
| 外部背景通道 | 14 |
| 用户画像与组合 | 16 |
| 数据存储 | 15、17 |
| 缓存与时效 | 17 |
| 模型层 | 6 |
| API | 5 |
| 安全与合规 | 19 |
| 可观测性与审计 | 18 |
| 可靠性与降级 | 20 |
| 测试与评测 | 21 |
| 分阶段实施 | 23 |

## 4. 代码结构与依赖方向

### 4.1 目标目录

```text
src/financial_agent/
├── api/
│   ├── app.py
│   ├── dependencies.py
│   ├── routes/
│   │   ├── conversations.py
│   │   ├── reports.py
│   │   └── users.py
│   └── schemas.py
├── config/
│   ├── loader.py
│   └── schemas.py
├── models/
│   ├── client.py
│   ├── messages.py
│   └── narrator.py
├── prompts/
│   ├── __init__.py
│   └── catalog.py
├── orchestration/
│   ├── graph.py
│   ├── state.py
│   ├── intent.py
│   └── planner.py
├── evidence/
│   ├── models.py
│   ├── adapters.py
│   ├── gate.py
│   ├── renderer.py
│   └── response_validator.py
├── mcp_client/
│   ├── client.py
│   └── schemas.py
├── web_research/
│   ├── schemas.py
│   ├── service.py
│   ├── client.py
│   └── server.py
├── portfolio/
│   ├── models.py
│   ├── repository.py
│   └── calculator.py
├── policies/
│   ├── suitability.py
│   └── privacy.py
├── repositories/
│   ├── task.py
│   ├── evidence.py
│   └── report.py
└── observability/
    ├── logging.py
    ├── tracing.py
    └── metrics.py
```

MCP 进程单独放置：

```text
mcp_servers/fund_advisor/
├── server.py
├── adapter.py
├── schemas.py
└── errors.py
```

### 4.2 依赖规则

```text
API -> Orchestration -> Domain services -> Repositories
                         |       |
                         |       +-> Web Research MCP client
                         +-> Fund Advisor MCP client

Evidence / Policy 可以被编排和服务调用
Repositories 不能反向依赖 API 或 LangGraph
Skill 不能依赖 Agent 或用户画像
```

**为什么这样设计**

- LangGraph 是编排基础设施，不应侵入金融计算和证据规则。
- Evidence Gate 需要能脱离模型和状态图做单元测试。
- Repository 隔离数据库细节，避免业务节点里散落 SQL。
- Skill 保持可独立打包，仍能作为独立 Agent Skill 使用。

**怎么做**

- 节点只接收 `AgentState` 和显式依赖，返回状态增量。
- 金融计算放在 Skill 或 `portfolio/calculator.py` 的纯函数中。
- 数据访问通过 `Protocol` 或抽象接口注入，测试时替换为内存实现。
- 禁止节点直接读取全局数据库连接、任意环境变量或执行 Shell。

**面试怎么讲**

这不是为了把个人项目拆成微服务，而是使用模块边界控制依赖。部署仍是模块化单体，只有容易被 AKShare 上游阻塞的 MCP 进程单独隔离。

## 5. FastAPI 接口层

状态：`已实现`

### 5.1 职责

- 校验 HTTP 请求和输出 Schema。
- 创建 `conversation_id`、`task_id`、`trace_id`。
- 调用 LangGraph，不参与工具规划和金融计算。
- 对外暴露任务状态、报告和 Evidence。
- 将领域错误映射成稳定 HTTP 错误。

### 5.2 为什么使用 FastAPI

- Pydantic v2 可复用到 API、配置和领域 Schema。
- 原生生成 OpenAPI，便于展示和后续作为外部 Tool 接入。
- 对个人 Python 项目部署成本低。
- 支持异步 I/O 和 `StreamingResponse`，后续可以增量返回状态。

FastAPI 只解决传输层问题，不把业务逻辑写进路由函数，否则 LangGraph 路径很难独立测试。

### 5.3 请求与响应

首个 MVP 使用同步提交、任务式查询：

```python
class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None


class MessageAccepted(BaseModel):
    conversation_id: UUID
    task_id: UUID
    status: Literal["running", "need_clarification", "completed", "failed"]
    clarification: str | None = None
    report_id: UUID | None = None
```

接口：

```text
POST /v1/conversations
POST /v1/conversations/{conversation_id}/messages
GET  /v1/tasks/{task_id}
GET  /v1/reports/{report_id}
GET  /v1/reports/{report_id}/evidence
PUT  /v1/users/me/risk-profile
PUT  /v1/users/me/portfolio
GET  /health/live
GET  /health/ready
```

`POST /messages` 不直接返回不受约束的模型文本。它只返回任务状态或已经通过 `VALIDATE_RESPONSE` 的报告。

### 5.4 组件怎么用

```python
app = FastAPI(title="Financial Research Agent", version="0.1.0")


@router.post("/v1/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: UUID,
    body: MessageRequest,
    graph: CompiledStateGraph = Depends(get_agent_graph),
) -> MessageAccepted:
    config = {"configurable": {"thread_id": str(conversation_id)}}
    result = await graph.ainvoke(
        initial_state(body, conversation_id),
        config=config,
    )
    return to_api_response(result)
```

- `Depends` 注入编译后的 Graph、Repository 和配置。
- `thread_id` 作为 LangGraph checkpoint 的会话键。
- 个人 MVP 可先同步 `ainvoke`；需要流式展示时改用 `astream_events`。
- `/health/live` 只判断进程存活；`/health/ready` 检查 PostgreSQL、Redis 和 MCP。

### 5.5 错误映射

| 领域错误 | HTTP | 对外语义 |
| --- | --- | --- |
| 请求 Schema 错误 | `422` | 参数不合法 |
| 实体歧义 | `409` | 需要用户确认具体产品 |
| Evidence 不足 | `200` | 返回 `cannot_confirm`，不是服务故障 |
| 上游超时 | `200/503` | 有部分证据则 `partial_result`，完全不可用则 `503` |
| 策略拒绝 | `200` | 返回 `policy_blocked` 和原因 |
| 内部异常 | `500` | 只返回 `trace_id`，不泄露堆栈 |

“无法确认”是合法业务结果，不应该统一包装成 `500`。

### 5.6 测试

- 使用 `TestClient` 验证 OpenAPI、请求校验和错误映射。
- 注入 Fake Graph，确保路由不依赖真实模型和 AKShare。
- 验证未通过响应门禁的报告不能从 API 返回。
- 验证日志不包含 API Key、完整持仓和成本金额。

### 5.7 面试怎么讲

重点说明 API 层和 Agent 层分离：FastAPI 管协议，LangGraph 管流程，Evidence Gate 管金融事实。三者各自可测试，不用启动整套服务才能验证规则。

## 6. 配置与 LiteLLM 模型层

状态：配置、`LLMClient` 和受限报告叙述器 `已实现`；多模型灾备待增强

### 6.1 配置加载

当前优先级：

```text
config/config.example.yaml
  -> config/config.local.yaml
  -> FINAGENT__... 环境变量
```

例如：

```bash
FINAGENT__MODELS__DEFAULT=deepseek-flash
FINAGENT__MODELS__PROVIDERS__DEEPSEEK__API_KEY=...
```

**为什么这样设计**

- `config.example.yaml` 提供可提交的完整配置说明。
- `config.local.yaml` 方便个人本地开发，但被 Git 忽略。
- 环境变量适合 CI 和容器部署。
- Pydantic 在进程启动时失败，优于运行到模型调用时才发现配置缺失。

**怎么用**

业务代码只调用：

```python
config = get_config()
client = get_llm_client()
```

禁止在业务模块中直接使用 `os.getenv()`。所有自定义配置先进入 `AppConfig`，确保默认值、类型和文档统一。

### 6.2 模型职责

允许模型执行：

- 意图分类。
- 实体候选提取。
- 基于 Claim 的自然语言组织。

禁止模型执行：

- 生成或修复市场数值。
- 计算收益、回撤、分位和组合权重。
- 判断工具数据是否过期。
- 确认基金、股票或指数是否真实存在。
- 绕过 Evidence Gate。

### 6.3 Prompt 目录与版本

生产 Prompt 统一放在：

```text
src/financial_agent/prompts/catalog.py
```

当前包含：

- `INTENT_CLASSIFIER_SYSTEM_PROMPT`
- `REPORT_NARRATOR_SYSTEM_PROMPT`
- `PROMPT_POLICY_VERSION`
- 每个 Prompt 独立的版本常量

业务节点只导入 Prompt，不允许新增内联 system prompt。Prompt 修改必须升级版本并通过
`tests/test_prompts.py`。完整规则见
[Prompt 设计与治理](PROMPT_DESIGN.md)。

Prompt 只约束模型语言行为；实体解析、数据时效、Evidence 授权和最终数字校验仍由代码
执行。

### 6.4 LiteLLM 怎么用

现有接口：

```python
text = client.complete(messages, model="deepseek-flash")
obj = client.complete_json(messages, model="deepseek-flash")
```

底层统一调用：

```python
response = litellm.completion(
    model=entry.litellm_model,
    api_base=provider.api_base,
    api_key=provider.api_key,
    messages=messages,
    temperature=entry.temperature,
    max_tokens=entry.max_tokens,
    timeout=entry.timeout_seconds,
    num_retries=config.models.litellm.num_retries,
)
```

后续为不同任务增加模型别名，而不是在节点中硬编码供应商模型名：

```yaml
models:
  default: deepseek-flash
  intent: deepseek-flash
  report: deepseek-flash
```

### 6.5 结构化输出

每个模型节点都定义 Pydantic 输出，而不是只要求“返回 JSON”：

```python
class IntentDecision(BaseModel):
    intent: Intent
    entities: list[EntityCandidate]
    needs_clarification: bool
    clarification_question: str | None = None
```

处理流程：

```text
模型 JSON
  -> json.loads
  -> Pydantic.model_validate
  -> 业务枚举和长度校验
  -> 写入 AgentState
```

JSON 解析失败最多进行一次“仅修复格式”重试。第二次失败后进入规则兜底或 `CANNOT_CONFIRM`，不能让模型无限自修复。

### 6.6 隐私处理

当前报告 Narrator 只接收公开且已授权的 Fact，不接收原始持仓。组合模块已提供
`qualitative_portfolio_context()`，用于未来需要向模型提供组合背景时生成脱敏上下文：

```text
持仓金额 -> 删除或区间化
平均成本 -> 删除
基金份额 -> 删除
用户姓名/账号 -> 替换为占位符
工具公开数据 -> 可保留
Evidence ID -> 可保留
```

本地组合服务先算出“仓位偏高”“超过目标上限”等确定性结果，模型只看到定性标签。
任何新增模型节点只要需要用户持仓，就必须显式调用该 helper 并增加外发参数测试；
不得直接把 Repository 返回的原始 Portfolio 放入 Prompt。

### 6.7 失败处理和测试

- 超时：分类节点可规则兜底，报告节点返回结构化简版报告。
- 限流：遵守 `Retry-After`，只对幂等调用重试并加入抖动。
- 供应商失败：切换备用别名，但使用同一输入 Claim。
- JSON 非法：一次格式重试后失败。
- 单元测试 mock `litellm.completion`。
- 契约测试验证模型切换后 Pydantic Schema 不变。
- 隐私测试扫描发送参数中是否出现持仓金额。

### 6.8 面试怎么讲

LiteLLM 解决供应商适配，不解决事实可信。反幻觉来自“模型职责限制 + 结构化输出 + Evidence Gate + 响应验证”，不能把“接了模型网关”当作安全机制。

## 7. Fund Advisor MCP Server

状态：`已实现`

### 7.1 职责与边界

MCP Server 把基金、指数和个股能力暴露为九个强类型工具：

| Tool | Skill 方法 |
| --- | --- |
| `fund_search` | `search` |
| `fund_status` | `status` |
| `fund_analyze` | `analyze` |
| `fund_profile` | `profile` |
| `fund_rating` | `rating` |
| `index_valuation` | `valuation` |
| `stock_valuation` | `stock_valuation` |
| `fund_compare` | `compare` |
| `interface_audit` | `audit` |

`fund_profile` 聚合基本信息、费率规则和资产配置（雪球系稳定接口），`fund_rating`
按代码精确匹配多家机构评级；两者把产品事实从固定文档收敛为实时可审计工具。

MCP 负责参数校验、超时、并发、缓存、日志和统一信封；不允许重算或改写 Skill 的金融值。

### 7.2 为什么要保留 MCP

直接在 LangGraph 节点里 import Skill 更简单，但 MCP 提供了：

- 标准化工具发现和参数 Schema。
- Agent 与数据工具的进程隔离。
- 后续可被其他 Agent 客户端复用。
- 工具权限边界和独立审计。
- 面试中可展示 Tool-using Agent 的协议化设计。

个人 MVP 不需要把 MCP 部署到远端，使用本机 `stdio` 即可。需要并发和常驻服务时再切换支持的流式 HTTP transport。

### 7.3 Skill 可导入化

当前核心代码位于带连字符的目录和单个脚本中，不适合作为 Python 包直接 import。目标结构：

```text
skills/akshare-fund-advisor/
├── src/akshare_fund_advisor/
│   ├── __init__.py
│   ├── advisor.py
│   └── schemas.py
└── scripts/fund_advisor.py
```

`scripts/fund_advisor.py` 只保留 argparse 和 JSON 输出，MCP 直接调用：

```python
from akshare_fund_advisor import FundAdvisor
```

这样 CLI 和 MCP 共用同一个实现，避免子进程 JSON 解析和重复逻辑。CLI 仍用于人工诊断。

### 7.4 Tool Schema

```python
class AnalyzeInput(BaseModel):
    fund: str = Field(min_length=1, max_length=100)
    years: int = Field(default=3, ge=1, le=10)


class ToolEnvelope(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    request_id: UUID
    tool: ToolName
    ok: bool
    data: dict[str, Any] | None
    sources: list[dict[str, Any]]
    data_audit: list[dict[str, Any]]
    data_warnings: list[str]
    data_policy: dict[str, Any]
    queried_at: datetime
    error: ToolError | None
```

`ToolError`：

```python
class ToolError(BaseModel):
    code: Literal[
        "INVALID_ARGUMENT",
        "ENTITY_NOT_FOUND",
        "ENTITY_AMBIGUOUS",
        "UPSTREAM_TIMEOUT",
        "UPSTREAM_SCHEMA_CHANGED",
        "STALE_DATA",
        "RATE_LIMITED",
        "INTERNAL_ERROR",
    ]
    message: str
    retryable: bool
```

### 7.5 Python MCP SDK 怎么用

锁定 Python MCP SDK 版本后，优先使用 SDK 提供的高层 Server API 注册工具。示意：

```python
mcp = FastMCP("fund-advisor")


@mcp.tool()
def fund_analyze(fund: str, years: int = 3) -> dict:
    request = AnalyzeInput(fund=fund, years=years)
    return adapter.execute(
        "fund_analyze",
        lambda advisor: advisor.analyze(request.fund, request.years),
    ).model_dump(mode="json")
```

`adapter.execute` 统一完成：

```text
生成 request_id
  -> 规范化参数
  -> 查询 Redis 缓存
  -> 获取并发信号量
  -> 调用 FundAdvisor
  -> 验证审计字段
  -> 包装 ToolEnvelope
  -> 写缓存和审计日志
```

SDK API 可能随锁定版本变化，实现时以对应版本文档为准，但工具 Schema 和 `ToolEnvelope` 契约不随 SDK 变化。

### 7.6 超时、并发和缓存

- 单进程并发上限建议 `2-4`，避免同时压垮公开上游。
- 每个工具有独立超时；审计工具超时可更长。
- 只缓存完整 `ToolEnvelope`，不能只缓存 `data`。
- 缓存命中仍检查 `queried_at`、源数据日期和 Schema 版本。
- 同参数请求使用 Redis single-flight 锁，防止缓存击穿。

### 7.7 错误和降级

- AKShare Schema 变化：映射 `UPSTREAM_SCHEMA_CHANGED`，禁止模型猜字段。
- 实体不唯一：返回候选列表，Agent 转 `NEED_CLARIFICATION`。
- 数据过期：保留原始结果供审计，但 `ok=false` 或标记不可进入完整报告。
- 非关键字段缺失：保留 warning，由 Evidence Gate 决定等级。
- 进程崩溃：MCP 客户端只重启一次，不能无限重试公开上游。

### 7.8 测试

- Tool 参数边界测试。
- Skill 返回值到 `ToolEnvelope` 的契约测试。
- 验证 `frame_sha256` 原样保留。
- 验证 Adapter 不改变任一数值。
- 并发信号量和相同请求 single-flight 测试。
- 模拟超时、空 DataFrame、列名变化和上游限流。

### 7.9 面试怎么讲

MCP 不是为了把 Python 函数“包装得更潮”，而是建立标准工具契约和隔离边界。最关键的设计是适配层不修改数据，Skill 的审计字段必须原样进入 Evidence。

### 7.10 Web Research MCP

网页研究独立部署，不并入 Fund Advisor MCP，暴露三个工具：

```text
web_search(query, max_results, freshness_days)
web_fetch(url, max_chars)
document_read(url, max_chars)
```

实现路径：

```text
src/financial_agent/web_research/
├── schemas.py
├── service.py
├── client.py
└── server.py
```

支持 `inprocess`、`stdio` 和 Streamable HTTP。Compose 使用 HTTP，
`agent-api` 通过内部网络访问 `web-research-mcp:8002`。

安全边界：

- API Key 只从本地配置或环境变量读取。
- 初始 URL 和最终 URL 都执行 DNS/SSRF 校验。
- 限制重定向、响应大小、内容类型和正文长度。
- 可选域名 allowlist。
- MCP 响应固定 `numeric_allowed=false`。
- 编排层将命中转为低置信度 Web/文档 Evidence，只用于定性背景。

`document_read` 按用户给定 URL 实时读取 HTML/纯文本/PDF 原文（PDF 用 `pypdf` 抽取），
复用与 `web_fetch` 相同的 SSRF、重定向和大小限制。详细配置和错误码见
[Web Research MCP](WEB_RESEARCH_MCP.md)。

## 8. LangGraph 状态模型

状态：`已实现`

### 8.1 为什么使用 LangGraph

金融 Agent 需要可预测路径，不适合多个 Agent 自由讨论。LangGraph 提供：

- 显式节点和条件边。
- 状态持久化和断点续跑。
- 节点级重试与人工确认中断。
- 图结构可视化。
- 每条路径可独立测试。

这里使用 LangGraph 的“受控状态机”能力，不让模型动态创建节点、工具或终止条件。

### 8.2 AgentState

```python
class AgentState(TypedDict, total=False):
    schema_version: str
    task_id: str
    conversation_id: str
    trace_id: str
    user_query: str
    resolved_query: str
    conversation_history: list[dict]

    intent: str
    intent_confidence: float
    entities: list[dict]
    clarification: dict | None

    user_context: dict | None
    tool_plan: list[dict]
    tool_results: list[dict]
    external_context: list[dict]

    evidence: list[dict]
    evidence_grade: str | None
    claims: list[dict]
    suitability: dict | None

    report_draft: dict | None
    final_report: dict | None
    warnings: list[str]
    errors: list[dict]
    status: str
```

大对象不长期塞进 State：

- 原始工具 JSON 存审计表，State 保存 `tool_call_id` 和必要摘要。
- 外部网页/文档命中以摘要形式保存在 `external_context`，不长期驻留原始长文。
- Evidence 和 Claim 可在当前任务中保留，完成后落 PostgreSQL。

### 8.3 节点返回状态增量

```python
async def classify_intent(
    state: AgentState,
    runtime: Runtime[AgentContext],
) -> dict:
    decision = await runtime.context.intent_classifier.classify(
        state["user_query"]
    )
    return {
        "intent": decision.intent,
        "entities": [item.model_dump() for item in decision.entities],
    }
```

节点不原地修改共享状态，便于回放和单元测试。

### 8.4 Checkpointer

- 本地调试可使用内存 checkpointer。
- 可恢复任务使用 LangGraph PostgreSQL checkpointer。
- `thread_id = conversation_id`。
- `checkpoint_ns` 区分主图和未来子图。
- Evidence/Report 仍写业务表，不依赖 checkpoint 作为永久主存。

**为什么**

Checkpoint 保存编排状态，不适合承担可查询、可版本化的金融审计模型。两者需要不同生命周期和查询方式。

### 8.5 测试

- State Pydantic/TypedDict 边界测试。
- 每个节点输入固定 State，断言只返回允许字段。
- Checkpoint 恢复后不重复调用已成功的金融工具。
- State 中不存在 API Key、完整原始持仓和超长文档正文。

### 8.6 面试怎么讲

LangGraph 在这里解决的是流程可控和可恢复，不是提高模型“自主性”。金融场景里，能证明模型不能跳过证据校验比展示自由规划更重要。

## 9. 状态图与条件路由

状态：`已实现`

### 9.1 主流程

```text
RECEIVED
  -> CLASSIFY_INTENT
  -> LOAD_USER_CONTEXT
  -> PLAN_TOOLS
  -> COLLECT_TOOL_FACTS
  -> GATHER_EXTERNAL_CONTEXT
  -> BUILD_EVIDENCE
  -> VALIDATE_EVIDENCE
  -> CHECK_SUITABILITY
  -> BUILD_CLAIMS
  -> COMPOSE_REPORT
  -> VALIDATE_RESPONSE
  -> PERSIST_RESULT
  -> COMPLETED
```

分支：

```text
NEED_CLARIFICATION
PARTIAL_RESULT
CANNOT_CONFIRM
POLICY_BLOCKED
FAILED
```

### 9.2 Graph 构建

```python
builder = StateGraph(AgentState, context_schema=AgentContext)
builder.add_node("classify_intent", classify_intent)
builder.add_node("plan_tools", plan_tools)
builder.add_node("collect_tool_facts", collect_tool_facts)
builder.add_node("gather_external_context", gather_external_context)
builder.add_node("build_evidence", build_evidence)
builder.add_node("validate_evidence", validate_evidence)
builder.add_node("compose_report", compose_report)
builder.add_node("validate_response", validate_response)

builder.add_edge(START, "classify_intent")
builder.add_conditional_edges(
    "collect_tool_facts",
    route_after_tools,
    {
        "continue": "gather_external_context",
        "clarify": "need_clarification",
    },
)
builder.add_edge("gather_external_context", "build_evidence")
graph = builder.compile(checkpointer=checkpointer)
```

### 9.3 路由必须由代码决定

示例：

```python
def route_after_evidence(state: AgentState) -> str:
    grade = state["evidence_grade"]
    if grade in {"A", "B"}:
        return "check_suitability"
    if grade == "C":
        return "partial_result"
    if grade == "D":
        return "cannot_confirm"
    return "policy_blocked"
```

模型可以提供候选意图，但不能直接设置 `evidence_grade`、`allowed` 或最终状态。

### 9.4 幂等性

每个有副作用的节点使用：

```text
idempotency_key = task_id + node_name + normalized_input_sha256
```

- 已存在成功记录时读取结果，不再次调用上游。
- 模型报告可重新生成，但绑定同一 Claim 版本。
- 外部通道命中按 `source_url + content_sha256` 去重，避免重复引用同一原文。

### 9.5 面试怎么讲

可以现场画出主图并强调三类决策：模型决策、代码决策、用户决策。意图和自然语言理解允许模型参与；时效、证据等级和策略阻断只能由代码决定；实体歧义由用户确认。

## 10. 意图识别、实体解析与工具规划

状态：`已实现`

### 10.1 意图枚举

```python
class Intent(StrEnum):
    FUND_SEARCH = "fund_search"
    FUND_ANALYSIS = "fund_analysis"
    FUND_STATUS = "fund_status"
    FUND_PROFILE = "fund_profile"
    FUND_RATING = "fund_rating"
    INDEX_VALUATION = "index_valuation"
    STOCK_VALUATION = "stock_valuation"
    FUND_COMPARE = "fund_compare"
    DCA_REFERENCE = "dca_reference"
    SELL_OR_REBALANCE = "sell_or_rebalance"
    DOCUMENT_QA = "document_qa"
    WEB_RESEARCH = "web_research"
    UNSUPPORTED = "unsupported"
```

### 10.2 两阶段解析

```text
阶段一：模型/规则提取候选
  "沪深300现在贵吗"
  -> intent=index_valuation
  -> candidate="沪深300"

阶段二：Skill 确认规范实体
  -> entity_type=index
  -> code=000300
  -> unique=true
```

**为什么**

模型擅长理解自然语言，但不应成为基金代码真值源。最终实体必须由 Skill 的真实目录确认。

### 10.3 歧义策略

以下情况必须追问：

- 同名 A/C 类。
- ETF 与 ETF 联接。
- 人民币与美元份额。
- 指数名称命中多个子指数。
- 用户说“这只基金”但会话中有多个候选。

Clarification：

```python
class Clarification(BaseModel):
    reason: str
    question: str
    candidates: list[ResolvedEntity]
```

### 10.4 工具规划

不用开放式 ReAct 生成任意工具名，而是使用意图到工具的白名单：

```python
TOOL_POLICY = {
    Intent.FUND_SEARCH: ["fund_search", "index_valuation(指数主题时)"],
    Intent.FUND_ANALYSIS: ["fund_analyze"],
    Intent.FUND_STATUS: ["fund_status"],
    Intent.FUND_PROFILE: ["fund_profile"],
    Intent.FUND_RATING: ["fund_rating"],
    Intent.INDEX_VALUATION: ["index_valuation"],
    Intent.STOCK_VALUATION: ["stock_valuation"],
    Intent.FUND_COMPARE: ["fund_compare"],
    Intent.DCA_REFERENCE: ["fund_analyze", "index_valuation"],
    Intent.WEB_RESEARCH: [],  # 只走受控 Web 通道，不调用金融工具
}
```

模型只允许填写受限参数或判断某个可选工具是否需要。代码验证参数范围后再执行。

### 10.5 测试

- 构建 A/C 类、ETF/联接、指数简称歧义集。
- 验证个股历史估值路由到 `stock_valuation`，股票预测类请求仍被拒绝。
- 验证模型产生未注册工具名时被拒绝。
- 工具参数使用 Hypothesis 做 years、limit、列表长度边界测试。

### 10.6 面试怎么讲

“LLM 提候选，权威工具做确认”是实体解析的核心。这样既利用语言理解，又不让模型决定金融产品身份。

## 11. Evidence 数据模型

状态：`已实现`

### 11.1 为什么需要 Evidence

Tool、外部网页/文档、用户输入和规则的可信度、时效与使用权限不同。若直接把它们拼进 Prompt，模型很容易把历史文档数值当成当前行情，或把用户猜测当成事实。

Evidence 是进入报告前的统一事实协议。

### 11.2 Schema

```python
class EvidenceType(StrEnum):
    TOOL_FACT = "TOOL_FACT"
    DERIVED_METRIC = "DERIVED_METRIC"
    DOCUMENT_FACT = "DOCUMENT_FACT"
    USER_FACT = "USER_FACT"
    POLICY_RULE = "POLICY_RULE"
    MODEL_INTERPRETATION = "MODEL_INTERPRETATION"


class EvidenceRecord(BaseModel):
    evidence_id: UUID
    task_id: UUID
    type: EvidenceType
    subject_type: str
    subject_id: str
    field: str
    value: Any
    display_value: str | None = None
    unit: str | None = None
    as_of: date | datetime | None = None
    source_ref: str
    audit_ref: str | None = None
    freshness: Literal["valid", "stale", "unknown"]
    confidence: Literal["high", "medium", "low"]
    numeric_allowed: bool
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 11.3 数值表示

为避免浮点格式和报告展示不一致：

- `value` 保存规范化值，金融金额和比例优先使用 `Decimal`。
- `display_value` 由确定性 formatter 生成，例如 `"31.20%"`。
- `unit` 单独保存，不能把单位只写在文本里。
- `as_of` 必须来自工具或文档元数据，不能使用报告生成时间代替。

### 11.4 Evidence Adapter

每类来源有独立 Adapter：

```text
ToolEnvelopeAdapter
DocumentHitAdapter
UserContextAdapter
PolicyRuleAdapter
DerivedMetricAdapter
```

`ToolEnvelopeAdapter` 的处理：

```text
检查 ok 和 data_policy
  -> 检查 data_audit.validation
  -> 提取字段及 subject
  -> 绑定 source_ref=tool_call_id
  -> 绑定 audit_ref=frame_sha256
  -> 根据字段策略设置 freshness
  -> 生成 Evidence
```

`DocumentHitAdapter`（`document_hit_to_evidence`）把外部网页/文档命中转为
`DOCUMENT_FACT`，固定 `numeric_allowed=false`、`confidence=low`。Adapter 不允许从
自然语言摘要提取市场数值，只能读取 Tool 的结构化字段或原文片段本身。

### 11.5 来源权限矩阵

| 来源 | 允许当前市场数值 | 允许产品条款 | 允许背景解释 |
| --- | --- | --- | --- |
| AKShare Tool | 是 | 少量静态资料 | 是 |
| 确定性计算 | 是 | 否 | 是 |
| 官方文档 | 否 | 是 | 是 |
| Web | 否 | 否，除非官方原文且验证版本 | 是，低置信度 |
| 用户输入 | 仅用户自己的成本/份额 | 否 | 是 |
| 模型 | 否 | 否 | 只允许解释 |

### 11.6 测试

- Golden ToolEnvelope 转 Evidence。
- 缺少 `frame_sha256` 时金融数值被拒绝。
- Web 文本中的百分数不能生成 `numeric_allowed=true`。
- Evidence 序列化后 Decimal、日期和单位不丢失。
- 同一 tool call 重放生成相同语义内容。

### 11.7 面试怎么讲

Evidence 层相当于金融事实的类型系统。来源不仅决定“可信不可信”，还决定“允许用于什么结论”，这比简单给外部文本打分更严格。

## 12. Claim 与确定性渲染

状态：`已实现`

### 12.1 Claim Schema

```python
class ClaimRecord(BaseModel):
    claim_id: UUID
    task_id: UUID
    claim_type: Literal["fact", "derived", "interpretation", "warning"]
    template_id: str
    arguments: dict[str, str]
    evidence_ids: list[UUID]
    allowed: bool = False
    rejection_reasons: list[str] = Field(default_factory=list)
```

`arguments` 的值不是用户可见数值，而是 Evidence 引用：

```json
{
  "template_id": "index_pe_position",
  "arguments": {
    "index_name": "ev_name",
    "pe_percentile": "ev_pe_percentile",
    "as_of": "ev_as_of"
  }
}
```

### 12.2 为什么不让模型直接写最终数字

即使 Prompt 明确要求不编造，模型仍可能：

- 四舍五入错误。
- 抄错日期或单位。
- 把 PE 分位写成 PB 分位。
- 在润色时增加一个没有来源的数字。

因此模型负责选择 Claim 结构和解释角度，数值由 Renderer 从 Evidence 插槽替换。

### 12.3 渲染流程

```text
ClaimDraft
  -> ClaimValidator
  -> allowed Claim
  -> TemplateRenderer 读取 Evidence
  -> 结构化 Report
  -> 可选 LLM 组织非数值过渡语
  -> ResponseValidator
```

模板示例：

```text
截至 {as_of}，{index_name} 的 PE TTM 历史分位为
{pe_percentile}。该分位只描述所选历史窗口中的相对位置。
```

PE 和 PB 使用不同模板，禁止生成平均后的“综合估值分”。

### 12.4 Claim 校验

- 至少一个 Evidence。
- 每个参数引用存在。
- Evidence subject 一致。
- 当前数值只能引用 `TOOL_FACT` 或 `DERIVED_METRIC`。
- 文档条款必须有 page/version/source_url。
- 解释性 Claim 不得改变 Evidence 的方向。
- Warning 不能被模型删除。

### 12.5 测试

- Claim 引用不存在的 Evidence 必须失败。
- PE Claim 绑定 PB Evidence 必须失败。
- 不同基金主体的 Evidence 混用必须失败。
- Snapshot 测试确保模板渲染稳定。
- 生成文本中的每个数值都能反查 Evidence。

### 12.6 面试怎么讲

可以把这一层概括为“先生成可验证的 Claim AST，再渲染文本”。这比生成后只做事实核查更可靠，因为非法数字从设计上没有生成通路。

## 13. Evidence Gate 与响应验证

状态：`已实现`

### 13.1 门禁输入与输出

```python
class GateDecision(BaseModel):
    grade: Literal["A", "B", "C", "D", "E"]
    allowed_claim_types: set[str]
    blocked_evidence_ids: list[UUID]
    warnings: list[str]
    reasons: list[str]
```

等级：

| 等级 | 条件 | 行为 |
| --- | --- | --- |
| A | 工具、审计、时效、实体均合格 | 完整分析 |
| B | 市场数据合格，文档缺失 | 数据分析并披露缺口 |
| C | PE/PB 单侧失败或非关键告警 | 有限分析 |
| D | 关键数据失败、过期、歧义 | 当前无法确认 |
| E | 保证收益、绕过审计、自动交易 | 策略拒绝 |

### 13.2 规则实现

首版使用版本化 Python 规则，不引入 OPA：

```python
class EvidenceGate:
    def evaluate(
        self,
        intent: Intent,
        evidence: Sequence[EvidenceRecord],
        warnings: Sequence[str],
    ) -> GateDecision:
        ...
```

规则文件带版本：

```python
GATE_POLICY_VERSION = "2026-07-01"
```

每个 Decision 保存该版本，保证历史报告可解释。

### 13.3 响应验证器

`ResponseValidator` 在 API 返回前执行：

1. 提取最终报告中所有阿拉伯数字、百分数、日期和金额。
2. 与 Renderer 产生的授权 token 清单比较。
3. 检查每个报告字段的 `evidence_id`。
4. 检查 Citation 是否可反查 URL、页码和版本。
5. 检查 warnings 是否完整出现。
6. 检查禁止表达，例如“稳赚”“必涨”“无风险”。

对自然语言中的章节编号、基金代码等非金融数字使用字段级白名单，不能简单地“禁止所有数字”。

### 13.4 为什么需要前后两道门

- Evidence Gate 决定哪些事实和 Claim 可以用。
- Response Validator 检查渲染后的最终产品有没有越界。

前者防止错误输入生成，后者防止模板、模型润色或程序拼装时发生回归。

### 13.5 测试

- 规则表驱动覆盖 A-E 所有等级。
- Mutation test：删除 audit_ref、改日期、换 subject，必须降级。
- 报告中手工插入无 Evidence 数值，必须阻断。
- 禁止词和条件式表达回归测试。
- 目标指标：无证据金融数值进入报告为 `0`。

### 13.6 面试怎么讲

反幻觉不是一条 Prompt，而是数据入口、Claim 生成和最终输出三处的纵深防御。即使模型失控，代码门禁仍应阻止错误数字到达用户。

## 14. 外部网页与文档背景

状态：`web-research MCP 已实现，按配置启用`

金融产品事实（净值、费率、资产配置、评级、基本信息、估值分位、申赎状态）全部来自
`fund-advisor-mcp` 的强类型工具，可审计、可追溯。系统不维护固定文档语料库，也不做
向量检索：条款、政策和新闻这类非数值背景改由 `web-research-mcp` 在需要时实时读取，
取不到就诚实返回“当前无法确认”。

### 14.1 单节点外部背景

编排层用单个节点 `_gather_external_context` 承接外部背景，只有 `WEB_RESEARCH` 与
`DOCUMENT_QA` 两种意图触发；其余意图直接跳过，不产生任何网络调用。

```text
COLLECT_TOOL_FACTS
  -> GATHER_EXTERNAL_CONTEXT
       | 非 WEB_RESEARCH/DOCUMENT_QA -> external_context=[]
       | DOCUMENT_QA -> 从用户原文提取 URL -> document_read
       | WEB_RESEARCH -> web_search -> 逐条 web_fetch
  -> BUILD_EVIDENCE
```

命中写入单一 state 字段 `external_context: list[dict]`，每条包含 `channel`、`title`、
`url`、`text` 和审计哈希。没有多轮检索、轮次上限或充分性判断：节点只做一次外部读取，
成功与否都进入证据构建。

### 14.2 web-research MCP 工具

`web-research-mcp` 暴露三个工具：

```text
web_search(query, max_results, freshness_days)
web_fetch(url, max_chars)
document_read(url, max_chars)
```

`document_read` 按用户给定的 URL 实时读取 HTML、纯文本或 PDF 原文（PDF 用 `pypdf`
抽取文本），复用与 `web_fetch` 相同的 SSRF 校验、逐跳重定向复验、响应大小限制和内容
类型白名单。它替代了早期的“指定文档读取器”和固定知识库：无需嵌入、向量库或离线
摄取，用户明确给出文档时直接读原文即可，既准确又省去建库维护成本。

### 14.3 两条读取路径

- `DOCUMENT_QA`：用正则从用户原文提取首个 `http(s)` URL，调用 `document_read` 读取
  原文；用户没给 URL 时不猜测、不检索，返回空背景。
- `WEB_RESEARCH`：先 `web_search` 拿到候选结果，再对前若干条并发 `web_fetch` 抓取
  正文；单条抓取失败时保留搜索摘要。

搜索供应商采用**多供应商兜底链**：按配置顺序尝试
`serper → tavily → google_cse → brave → serpapi`，前一个认证失败、限流、超额或上游
报错时自动降级到下一个，只调用填了凭证的供应商。搜索与抓取的响应哈希分别进入命中
审计元数据，搜索审计还记录最终命中的 `provider` 与降级 `attempts`。

### 14.4 转为低置信度 Evidence

命中经 `document_hit_to_evidence` 转为 Evidence，固定：

```text
type = DOCUMENT_FACT
confidence = low
freshness = unknown
numeric_allowed = false
source_ref = {channel}:{index}
```

即使网页来自财经媒体、文档来自官方站点，也不能提供当前价格、净值、PE/PB、收益率或
申赎状态。外部文本中的数字只能保留在引用原文里，不能进入数值 Claim。检测到疑似提示
注入的片段会在 metadata 标记，并按不可信数据处理。

### 14.5 失败即降级，不阻断

外部通道失败不影响主流程：节点捕获异常后追加一条
`category="retrieval"`、`code="EXTERNAL_CONTEXT_FAILED"` 的告警，并保留已确认的工具
事实，报告中声明“本次未附带外部背景”。没有多轮改写或重试循环。

### 14.6 安全

- 禁止访问 localhost、私网 IP、`file://` 和云元数据地址。
- 禁止 URL 携带用户名或密码。
- 初始 URL 和重定向后的最终 URL 都必须复验。
- 限制重定向次数、响应大小、内容类型和正文字符数。
- HTML 清洗脚本、表单和隐藏文本。
- 页面中的“忽略系统提示”等内容始终按不可信数据处理。
- 可选域名 allowlist；条款类问题优先官方域名原文。

### 14.7 面试怎么讲

外部背景是“即时读取（JIT）”而不是“检索系统”：没有知识库、向量库和摄取管线，只有一个
受控节点在特定意图下读用户指定文档或做网页背景补充。金融数值权威只属于 AKShare 工具，
网页与文档只能提供低置信度定性背景，二者不争夺当前市场事实。

## 15. PostgreSQL 数据模型

状态：`已实现；本地 SQLite、部署 PostgreSQL`

### 15.1 为什么使用 PostgreSQL

- 用户、任务、Evidence、Claim 和报告需要事务一致性。
- JSONB 适合保存版本化 Evidence 元数据。
- 个人部署和备份简单。
- 单库即可承载全部事务与审计数据，无需额外数据库。

### 15.2 核心表

```text
conversations
tasks
tool_calls
evidence_records
claim_records
reports
report_claims
risk_profiles
portfolio_positions
policy_versions
```

初始 Alembic 迁移当前落地 `conversations`、`tasks`、`evidence_records`、
`claim_records`、`reports` 和 `user_state`，不含任何文档或向量表，也不加载
`vector` 扩展。

### 15.3 关键关系

```text
conversation 1 -> N task
task 1 -> N tool_call
task 1 -> N evidence
task 1 -> N claim
claim N -> M evidence
report 1 -> N claim
```

Claim 和 Evidence 的多对多关系建议使用显式关联表，不只埋在 JSONB 中，便于做引用覆盖率查询。

### 15.4 事务边界

- 工具调用完成：`tool_call + 原始结果引用` 一次事务。
- Evidence 建立：Evidence 和来源关联一次事务。
- 报告完成：Report、Claim 关联和最终状态一次事务。

外部 API 调用不能放在数据库事务中，避免长事务锁。

### 15.5 Repository

```python
class EvidenceRepository(Protocol):
    async def add_many(
        self,
        task_id: UUID,
        records: Sequence[EvidenceRecord],
    ) -> None:
        ...

    async def list_by_report(self, report_id: UUID) -> list[EvidenceRecord]:
        ...
```

使用 SQLAlchemy 2.x async 或 psycopg 3 均可。MVP 推荐 SQLAlchemy 2.x + Alembic，减少手写映射并保留明确 Migration。

### 15.6 数据保留

- 原始工具 JSON 可加密保存或保存文件引用。
- Evidence、Claim 和报告保留，用于面试演示回放。
- 持仓与公开研究数据分表。
- 删除用户数据时，审计记录只保留匿名化必要字段。

### 15.7 测试

- Testcontainers 或 Docker Compose 启动真实 PostgreSQL。
- Migration 从空库升级测试。
- 事务回滚和唯一约束测试。
- ES 全部删除后可从 PG 重建。

### 15.8 面试怎么讲

JSONB 不是放弃关系建模。高变化的 Evidence 元数据放 JSONB，主体、来源、任务和 Claim 关联仍用关系字段和外键。

## 16. 用户画像与组合服务

状态：`已实现`

### 16.1 职责

- 保存用户确认的风险画像和持仓。
- 本地计算仓位、集中度、盈亏和再平衡差额。
- 向 Agent 输出脱敏后的定性结论和 Evidence。
- 不执行交易。

### 16.2 Schema

```python
class RiskProfile(BaseModel):
    risk_level: Literal["conservative", "balanced", "growth", "aggressive"]
    horizon_months: int = Field(ge=1)
    max_drawdown_tolerance_pct: Decimal = Field(ge=0, le=100)
    emergency_fund_ready: bool
    stable_cash_flow: bool
    target_allocation: dict[str, Decimal]
    assessed_at: datetime
    expires_at: datetime


class Position(BaseModel):
    fund_code: str
    share_class: str | None
    channel: str
    units: Decimal
    average_cost: Decimal
    currency: str
    target_weight_pct: Decimal | None
    updated_at: datetime
```

### 16.3 确定性计算

```text
market_value = units * current_nav
weight = market_value / portfolio_market_value
unrealized_return = (current_nav - average_cost) / average_cost
rebalance_amount = target_value - current_value
```

边界：

- 当前净值必须来自本次有效 Tool Evidence。
- 缺少某只持仓净值时，不计算完整组合权重。
- 币种不一致且没有合法汇率工具时，不合并金额。
- 计算过程和舍入规则版本化。

### 16.4 适当性检查

具体金额建议需要：

- 风险画像未过期。
- 投资期限、应急资金和现金流字段完整。
- 目标仓位已确认。
- 当前工具事实合格。

任何一项缺失，只输出一般研究结论和待补充信息。

### 16.5 隐私

- 原始 Position 不进入外部模型 Prompt。
- 模型只收到“单一指数基金仓位高于目标上限”等标签。
- 数据库日志不打印 ORM 对象。
- 本机备份也应排除明文密钥。

### 16.6 测试

- Decimal 计算和舍入测试。
- 零成本、零总资产、负数份额和币种不一致。
- 画像过期后具体金额建议被阻断。
- Prompt 快照不包含 units、average_cost 和具体金额。

### 16.7 面试怎么讲

组合服务体现“确定性计算下沉”。模型解释为什么需要再平衡，但金额和权重由代码算，用户隐私也无需发给外部模型。

## 17. Redis 缓存、限流与锁

状态：`已实现，Redis 不可用时降级进程内缓存`

### 17.1 Key 设计

```text
finagent:tool:v1:{tool}:{normalized_args_sha256}
finagent:lock:tool:{tool}:{normalized_args_sha256}
finagent:ratelimit:model:{provider}:{minute}
finagent:ratelimit:upstream:{interface}:{minute}
finagent:task:{task_id}:status
finagent:entity:v1:{query_sha256}
```

所有 Key 包含业务前缀和 Schema 版本。缓存值保存完整 `ToolEnvelope`。

### 17.2 TTL

| 数据 | TTL |
| --- | --- |
| 基金目录 | 6-24 小时 |
| 基金静态资料 | 24 小时 |
| 净值/历史分析 | 15-60 分钟 |
| ETF 行情 | 15-60 秒 |
| 申赎状态 | 5-15 分钟 |
| PE/PB 历史 | 30-60 分钟 |
| 实体候选 | 6 小时 |

TTL 不代表数据有效。取缓存后仍要检查 Skill 的源日期和 `data_audit`。

### 17.3 Single-flight

```text
GET cache
  -> miss
  -> SET lock token NX PX
  -> owner calls upstream
  -> write cache
  -> compare-and-delete lock
```

未获得锁的请求短暂等待并重查缓存，不直接同时打上游。释放锁用 Lua 比较 token，防止误删别人的锁。

### 17.4 降级

- Redis 不可用：允许直连工具，但进程内并发限制仍生效。
- 限流状态不可用：使用本地保守限流。
- Redis 不能作为 Evidence、任务或报告唯一存储。

### 17.5 测试

- 规范化参数顺序产生同一 Key。
- 缓存返回仍执行 freshness 校验。
- 锁超时、持有者崩溃和 token 安全释放。
- Redis 故障时主流程不丢 Evidence。

### 17.6 面试怎么讲

缓存提升可用性，但不能提升事实可信度。命中缓存仍走证据门禁，这一点是金融缓存与普通页面缓存的主要差别。

## 18. 可观测性与审计

状态：结构化日志、OpenTelemetry、ES 审计与报告检索副本 `已实现`

### 18.1 Trace 结构

每个请求生成 `trace_id`，Span 层级：

```text
http.request
  -> agent.graph
      -> node.classify_intent
      -> node.collect_tool_facts
          -> mcp.tool.index_valuation
              -> akshare.interface
      -> node.gather_external_context
      -> node.validate_evidence
      -> llm.compose_report
      -> node.validate_response
```

Span 属性只保存：

- `task_id`、`conversation_id`。
- 节点名、工具名、模型别名。
- 基金/指数规范代码。
- 耗时、状态、Token 数和错误码。
- `frame_sha256` 引用。

不保存完整 Prompt、API Key、持仓金额和私有文档正文。

### 18.2 OpenTelemetry 怎么用

- FastAPI instrumentation 生成入口 Span。
- HTTPX instrumentation 记录外部调用，但过滤 Authorization Header。
- LangGraph 节点用手工 span 包装，记录状态转移。
- 日志注入 `trace_id` 和 `span_id`。
- MVP 可只导出控制台/OTLP，后续接 Tempo。

### 18.3 Elasticsearch 索引

```text
finagent-logs-v1
finagent-audit-v1
finagent-reports-v1
```

通过 alias 指向版本化索引。审计文档只保存 PG 主键和可搜索摘要；详细 Evidence 回 PostgreSQL 查询。Elasticsearch 只做审计投影与报告检索，不存文档分块，也不做混合检索。

### 18.4 指标

- 工具成功率、超时率、Schema 变化率。
- 数据过期率。
- Evidence A-E 等级分布。
- 无 Evidence Claim 拒绝数。
- 外部背景通道失败率、引用覆盖率。
- P50/P95 延迟。
- 模型 Token 和估算成本。
- 缓存命中率。

### 18.5 测试

- 同一请求的 API、Graph、MCP 和模型日志共享 trace_id。
- 日志脱敏测试。
- ES 不可用不阻塞报告主事务。
- 从 trace_id 可以定位 ToolCall、Evidence 和 Report。

### 18.6 面试怎么讲

可观测性不仅看延迟，还要观测“事实质量”：过期率、证据等级、引用覆盖率和无证据 Claim 拒绝数才是金融 Agent 的核心业务指标。

## 19. 安全、隐私与提示注入

状态：工具白名单、URL/SSRF、日志脱敏和适当性规则 `已实现`

### 19.1 信任边界

```text
可信控制指令：
  代码规则、版本化 System Prompt、注册 Tool Schema

不可信数据：
  用户文本、网页、PDF、工具上游文本字段、模型输出
```

文档中的任何命令都不能升级为系统指令。

### 19.2 最小权限

- Agent 只能调用注册 MCP 工具。
- 无 Shell、任意 SQL、文件系统写入工具。
- 网页/文档抓取只能访问 allowlist 或经过 SSRF 检查的公网地址。
- 数据库账号按服务限制表权限。
- 模型 API Key 只在模型客户端进程内可见。

### 19.3 密钥

- 本地使用被忽略的 `config.local.yaml`。
- Git 和日志扫描阻止 `sk-` 等密钥模式。
- CI/部署使用环境变量或 Secret。
- 已在聊天或其他渠道暴露的 Key 应轮换。

### 19.4 Prompt injection 防护

1. 外部网页/文档内容使用明确的 `<untrusted_document>` 边界。
2. System Prompt 声明文档只能作为事实材料。
3. Tool Planner 只接受枚举工具。
4. 模型输出经过 Pydantic 和业务规则。
5. 文档要求泄露 Prompt、调用工具或忽略规则时记录 warning。

Prompt 不能单独构成防护，权限白名单和输出校验是最终边界。

### 19.5 测试

- Git Secret 扫描。
- 文档和网页提示注入样本。
- SSRF、超大文件、压缩炸弹和错误 MIME。
- 越权 Tool 名、任意 SQL 和本地文件请求。
- 日志与 Trace 隐私扫描。

### 19.6 面试怎么讲

强调“数据与指令分离”。外部网页/文档把外部文本带进上下文，扩大了提示注入面，因此 Tool 白名单和代码路由比 Prompt 约束更关键。

## 20. 错误模型、重试和降级

状态：核心错误映射和降级 `已实现`；跨实例熔断待增强

完整错误码、实体状态和 API 降级契约见
[错误处理与降级契约](ERROR_HANDLING.md)。

### 20.1 统一错误

```python
class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    AMBIGUITY = "ambiguity"
    UPSTREAM = "upstream"
    STALE_DATA = "stale_data"
    RETRIEVAL = "retrieval"
    MODEL = "model"
    POLICY = "policy"
    INTERNAL = "internal"


class AgentError(BaseModel):
    category: ErrorCategory
    code: str
    message: str
    retryable: bool
    source: str
    details_ref: str | None = None
```

`RETRIEVAL` 类目现仅表示外部网页/文档通道失败（`_gather_external_context` 抛出
`EXTERNAL_CONTEXT_FAILED`），与多轮检索无关。对外 message 不包含堆栈、路径、Key 和
上游敏感响应。

### 20.2 重试原则

| 操作 | 重试 |
| --- | --- |
| 参数校验失败 | 不重试 |
| 实体歧义 | 等用户确认 |
| AKShare 短暂网络失败 | 最多 2 次，指数退避 |
| Schema 变化 | 不重试 |
| 模型限流/5xx | 最多 2 次，可切备用模型 |
| 模型 JSON 非法 | 1 次格式修复 |
| 外部网页/文档通道失败 | 记 `EXTERNAL_CONTEXT_FAILED` 并降级，不做多轮重试 |
| 数据过期 | 不通过重试伪装为有效 |

### 20.3 降级矩阵

```text
PE 失败、PB 有效
  -> Grade C，只展示 PB

外部背景通道失败、Tool 有效
  -> 保留工具事实，声明本次未附带外部背景

模型失败、Claims 有效
  -> 使用确定性模板生成简版报告

Redis 失败
  -> 直连，但保守限流

Elasticsearch 失败
  -> 审计投影/报告检索降级；主流程与日志本地缓冲不受影响

关键 Tool 失败或数据过期
  -> CANNOT_CONFIRM，不用外部通道/模型补数
```

### 20.4 熔断

个人 MVP 可先用进程内连续失败计数：

- 同一上游连续失败达到阈值后短时打开熔断。
- 熔断期间立即返回 retryable error。
- 半开状态只放一个探测请求。

后续多实例时把状态迁移到 Redis 或使用成熟库。

### 20.5 测试

- 故障注入覆盖每个降级分支。
- 验证重试不会重复持久化 ToolCall。
- 模型失败时模板报告仍无新数字。
- ES/Redis 故障不破坏 PostgreSQL 主记录。

### 20.6 面试怎么讲

降级目标不是“无论如何都回答”，而是尽可能保留已验证事实。关键市场数据缺失时，正确降级就是拒绝确认。

## 21. 测试与金融评测

状态：Skill、Agent、集成、E2E 测试和工具路由评测 `已实现`

### 21.1 测试金字塔

```text
大量单元测试
  - Evidence Adapter/Gate
  - Claim/Renderer
  - 路由函数
  - Portfolio Calculator

适量集成测试
  - MCP + Skill
  - PostgreSQL/Redis
  - web-research MCP + 外部背景节点
  - LiteLLM mock server

少量 E2E
  - API -> Graph -> MCP -> Evidence -> Report
```

真实 AKShare 测试与确定性单测分开。CI 默认用录制/固定样本，定时任务再执行真实接口审计，避免公开上游波动导致普通提交随机失败。

### 21.2 评测数据集

建议 JSONL：

```json
{
  "case_id": "valuation_001",
  "query": "沪深300现在估值高吗",
  "expected_intent": "index_valuation",
  "expected_tools": ["index_valuation"],
  "expected_entity": {"type": "index", "code": "000300"},
  "forbidden_claims": ["guaranteed_return"],
  "expected_grade": "A"
}
```

数据集：

- `tool_routing.jsonl`
- `entity_resolution.jsonl`
- `numeric_faithfulness.jsonl`
- `freshness_gate.jsonl`
- `concept_boundaries.jsonl`
- `suitability.jsonl`
- `prompt_injection.jsonl`

### 21.3 核心评测器

**数值忠实度**

```text
报告中的金融数值集合
  subset of
Renderer 授权的 Evidence 展示值集合
```

**引用覆盖率**

```text
有文档事实且带有效 citation 的 Claim 数 / 文档事实 Claim 总数
```

**工具路由**

比较实际工具集合和期望工具集合，区分漏调和多调。

**概念边界**

规则检测“净值位置=估值”“PE/PB 平均”等禁止表达。

### 21.4 上线门槛

- 数值忠实度 `100%`。
- 过期数据拦截率 `100%`。
- 关键工具路由准确率 `>98%`。
- 实体歧义拒绝准确率 `>99%`。
- 关键产品条款引用率 `100%`。

### 21.5 面试怎么讲

不要只展示几个漂亮回答。展示固定评测集、失败样例和回归门槛，才能证明这是工程系统而不是 Prompt Demo。

## 22. Docker Compose 与本地运行

状态：`已实现`

### 22.1 MVP 进程

```text
agent-api
fund-advisor-mcp
web-research-mcp
postgres
redis
elasticsearch
```

LiteLLM 作为 Python 库内嵌，不单独部署 Gateway。Elasticsearch 承担审计投影与报告检索，
不在 API 在线路径解析任何文档。

### 22.2 Compose 原则

- PostgreSQL、Redis 和 ES 使用命名 volume。
- 锁定镜像版本或 digest。
- 健康检查通过后 API 才 ready。
- `config.local.yaml` 只读挂载，优先使用环境变量 Secret。
- MCP 与 API 分容器时使用受限内部网络。
- ES 设置适合本机的内存上限，避免开发机资源失控。

### 22.3 启动顺序

```text
postgres + redis
  -> migrations
  -> fund-advisor-mcp
  -> web-research-mcp
  -> agent-api
  -> elasticsearch
```

### 22.4 备份

- PostgreSQL：定期 `pg_dump`。
- ES：可从 PG 和日志源重建，不作为唯一备份。
- Redis：不要求持久化关键业务数据。

### 22.5 测试

- `docker compose config` 校验。
- 从空 volume 一键启动。
- Migration、readiness 和进程重启测试。
- 删除 ES volume 后重建索引。

### 22.6 面试怎么讲

个人 MVP 用 Compose 是主动控制复杂度。只有出现多用户、高并发、滚动升级和弹性需求后，Kubernetes 才有明确收益。

## 23. 实施顺序与验收

### 23.1 阶段一：可信工具闭环（已完成）

1. 把 Skill 核心改为可 import 包，CLI 保持兼容。
2. 实现 MCP 九个工具和 `ToolEnvelope`。
3. 实现 Evidence/Claim/Gate/Renderer。
4. 实现 LangGraph 的搜索、分析、估值三条路径。
5. 实现 FastAPI 和 PostgreSQL 任务/报告存储。
6. 接 Redis 缓存和基础 OTel。
7. 建数值忠实度、路由和歧义评测。

验收：

```text
用户问题
  -> 正确工具
  -> 带 frame_sha256 的 Evidence
  -> Claim
  -> 无新增数值的报告
  -> Evidence API 可追溯
```

### 23.2 阶段二：外部网页与文档背景（已完成）

1. `web-research-mcp` 的 `web_search` / `web_fetch` / `document_read` 三工具。
2. SSRF、重定向、大小与内容类型限制。
3. 多供应商搜索兜底链（serper → tavily → google_cse → brave → serpapi）。
4. 命中转低置信度 Evidence 与引用元数据。
5. 单节点 `_gather_external_context` 接入 WEB_RESEARCH / DOCUMENT_QA 意图。

### 23.3 阶段三：用户与组合（MVP 已完成）

1. 风险画像。
2. 持仓和确定性组合计算。
3. Prompt 隐私过滤。
4. 适当性门禁。

### 23.4 阶段四：治理（部分完成）

1. 多模型灾备。
2. 更完整的指标和告警。
3. 安全扫描、SBOM 和许可证检查。
4. 压测和定期红队评测。

## 24. 关键设计取舍

| 问题 | 当前选择 | 没选的方案 | 原因 |
| --- | --- | --- | --- |
| 编排 | LangGraph 固定图 | 多 Agent 自由讨论 | 金融路径需要可预测、可测试 |
| 工具协议 | MCP | 节点直接调用函数 | 标准契约、隔离和复用 |
| 市场事实 | AKShare Skill | 模型/Web | 当前数值必须可审计 |
| 报告生成 | Claim + 模板渲染 | LLM 直接写全文 | 阻止新增或抄错数字 |
| 外部背景 | web-research MCP 实时读取 | 固定知识库/向量检索 | 无需摄取与向量库，按需读原文 |
| 审计与报告检索 | Elasticsearch | 引入向量库 | 审计投影与报告全文检索复用，可从 PG 重建 |
| 模型接入 | LiteLLM 外部 API | 首版自建 GPU | 降低 MVP 运维成本 |
| 部署 | 模块化单体 + MCP 进程 | 首版微服务/K8s | 保持边界但控制复杂度 |

## 25. 面试讲解主线

建议按以下顺序讲项目，而不是按组件清单逐个介绍：

1. **问题**：金融 Agent 最大风险不是回答不流畅，而是数字错误、来源不明和概念混淆。
2. **事实边界**：市场数值只走 AKShare Skill/MCP，文档按需实时读取，模型只负责理解和表达。
3. **受控编排**：LangGraph 固定状态图，模型不能跳过工具、Evidence 和策略节点。
4. **反幻觉机制**：ToolEnvelope -> Evidence -> Claim -> 确定性 Renderer -> Response Validator。
5. **外部背景**：单节点按意图选择读用户指定文档或做网页背景，JIT 获取、低置信度、不参与数值。
6. **工程能力**：PostgreSQL 主数据、Redis 缓存、ES 审计与报告检索、OTel Trace、评测集和故障降级。
7. **取舍**：个人 MVP 不上 K8s、多 Agent、向量库和自建 GPU，先证明可信闭环。

### 25.1 常见追问

**为什么用了 LangGraph 还要自己写 Gate？**

LangGraph 负责节点和状态流转，不理解金融事实是否有效。Gate 是领域规则，必须独立实现和测试。

**MCP 是否只是多一层调用？**

在单项目里确实增加一跳，但换来强类型 Tool Schema、进程隔离、独立审计和跨 Agent 复用。AKShare 上游不稳定时，隔离价值尤其明显。

**为什么不让 LLM 生成后再做事实核查？**

生成后核查很难证明遗漏了哪个数字。本设计先生成 Claim 引用，再由 Evidence 渲染数字，非法数字没有正常生成路径。

**为什么移除了向量检索和知识库？**

金融事实（费率、评级、资产配置、估值）已经由实时可审计工具覆盖，条款类问题用 `document_read`
按需读官方原文即可。维护一套向量库、嵌入和摄取管线，收益远小于运维和一致性成本，还容易让
历史文档数值被误当成当前行情。移除后事实边界更清晰，Elasticsearch 也回归到审计与报告检索。

**Web 背景会不会污染市场数值？**

不会。网页与文档命中固定 `numeric_allowed=false`、`confidence=low`，只能进入定性解释，
其中的数字只保留在引用原文里，不能进入数值 Claim。

**如何证明没有幻觉？**

不能证明模型永远不幻觉，但可以证明金融数字进入报告的路径受控：所有数字必须匹配 Evidence，Evidence 必须匹配审计通过的工具或确定性计算，最终还有响应验证和回归评测。

**上游 AKShare 错了怎么办？**

系统能保证来源、时间、Schema 和内容哈希可追溯，不能保证公开源绝对正确。发生冲突时降级或拒绝确认，并保留审计记录，不用模型“修复”。

## 26. Definition of Done

首个可面试演示版本必须满足：

- 可以通过 API 提问基金搜索、分析和指数估值。
- LangGraph 路径和节点状态可展示。
- MCP 返回统一 ToolEnvelope 和 `frame_sha256`。
- 每个报告金融数值均可展开到 Evidence。
- 人工插入无 Evidence 数值时响应验证器会阻断。
- 实体歧义会追问，不自动选 A/C 类。
- 工具失败或数据过期时返回“当前无法确认”。
- 模型供应商可以通过配置替换。
- 持仓金额不会发送给外部模型。
- 至少有一组自动评测报告展示路由、忠实度和引用结果。

完成上述闭环后，再增加外部背景、组合和生产治理，能让项目演进路径清晰，也能在面试中准确区分“已实现”“正在实现”和“后续设计”。
