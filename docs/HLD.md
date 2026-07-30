# 金融投资研究 Agent 高层设计

> 飞书在线文档：https://bytedance.larkoffice.com/docx/EYPVdypEsoux0bxQMFackiUhnub

## 1. 文档目的

本文定义一个面向中国公募基金、ETF 和宽基指数估值研究的金融 Agent。系统以 [`skills/akshare-fund-advisor`](../skills/akshare-fund-advisor/) 为事实工具核心，通过 MCP、RAG、用户风险画像和证据门禁生成可追溯的投资研究报告。

该 Agent 不是通用聊天助手，不负责短线预测、自动交易或收益承诺。设计优先使用可自部署的开源组件；模型、对象存储和部署平台均保留替换选项。

## 2. 目标与非目标

### 2.1 目标

- 回答基金搜索、产品分析、申赎状态、指数 PE/PB、基金比较和定投条件。
- 所有市场数值均来自已审计工具调用，不由模型生成或补齐。
- 使用 RAG 解释基金合同、招募说明书、定期报告、指数规则和监管要求。
- 结合用户期限、现金流、仓位和回撤承受能力，生成条件式而非确定性建议。
- 每个重要结论可追溯到工具结果、文档片段、用户输入或确定性计算。
- 支持替换 LLM、向量库、对象存储和 Agent 框架，避免厂商锁定。

### 2.2 非目标

- 不预测具体涨跌、收益率、目标价或市场底部。
- 不自动下单，不保存券商交易凭证，不接管用户账户。
- 不把新闻情绪、模型记忆或网页摘要当作当前行情。
- 不使用多 Agent 自由讨论形成金融事实。
- 不在首个版本覆盖股票选股、期货、期权、加密资产和税务建议。

## 3. 设计原则

1. **事实先于生成**：先取得结构化证据，再允许模型组织语言。
2. **确定性计算下沉**：收益、回撤、分位、仓位和再平衡计算由代码完成。
3. **数据类型隔离**：实时/时序数据走工具，制度和产品文档走 RAG。
4. **默认拒绝猜测**：数据缺失、过期、冲突或实体不唯一时返回“当前无法确认”。
5. **单一受控编排**：使用显式状态机，不使用自治 Agent 群。
6. **最小工具权限**：Agent 只能调用注册工具，不能执行任意 Shell、SQL 或网页抓取。
7. **全链路可审计**：保留输入、工具参数、证据版本、模型版本、提示词版本和输出。
8. **开源优先、接口解耦**：核心组件均通过协议或仓储接口替换。

## 4. 范围与职责边界

### 4.1 当前 Skill 内

- 基金与指数精确解析、歧义拒绝。
- AKShare 查询、Schema 校验、时效检查和 `frame_sha256`。
- 收益、波动、回撤、历史位置、PE/PB 分位和 ETF 溢价计算。
- `search`、`status`、`analyze`、`valuation`、`compare`、`audit` 六个稳定 CLI 动作，以及可导入的个股估值能力。
- `sources`、`data_audit`、`data_warnings`、`data_policy` 和稳定错误码。

### 4.2 MCP 层

- 将基金、指数和个股能力暴露为九个强类型工具。
- 参数校验、进程隔离、并发限制、超时、缓存和调用日志。
- 将 CLI JSON 规范化为统一 `ToolEnvelope`，不修改金融数值。

### 4.3 RAG 层

- 检索基金合同、招募说明书、定期报告、指数编制方案和监管规则。
- 保存来源 URL、发布日期、生效日期、产品代码、文档版本和页码。
- 不保存或回答当前净值、实时价格、当前 PE/PB 和当前申赎状态。

### 4.4 Agent 层

- 意图分类、任务规划、工具路由、追问和多来源证据合并。
- 用户风险画像、持仓成本、目标仓位、预算和期限管理。
- 证据门禁、适当性检查、合规策略和最终报告。
- 组合级风险、资产配置和再平衡建议。

## 5. 总体架构

```text
Web / API / CLI
       |
       v
API Gateway + Auth
       |
       v
Financial Agent Orchestrator
  |-- Intent Router
  |-- Entity Resolver
  |-- User Context Loader
  |-- Tool Planner
  |-- Evidence Gate
  |-- Suitability / Policy Guard
  `-- Report Composer
       |
       +--------------------+----------------------+------------------+
       |                    |                      |                  |
       v                    v                      v                  v
Fund Advisor MCP      Portfolio Service       RAG Service       LiteLLM Gateway
       |                    |                      |                  |
       v                    v                      v                  v
akshare-fund-       PostgreSQL /            知识/文档/web        外部模型 API
advisor Skill       deterministic math      三通道 Agentic RAG   (OpenAI 兼容)
       |
       v
AKShare public upstreams

Shared infrastructure:
PostgreSQL | Redis | 本地文件对象存储 | Elasticsearch（RAG + 日志/审计检索） | OpenTelemetry
```

### 5.1 推荐部署单元

| 服务 | 职责 | 是否持有金融事实 |
| --- | --- | --- |
| `agent-api` | 会话入口、认证、流式响应 | 不持有原始行情 |
| `agent-worker` | 状态机编排、证据门禁、报告生成 | 持有单次任务证据 |
| `fund-advisor-mcp` | Skill 的 MCP 适配和隔离执行 | 返回当前工具事实 |
| `portfolio-service` | 用户持仓、目标仓位和确定性计算 | 持有用户私有数据 |
| `rag-api` | 文档摄取、检索、引用 | 持有文档事实 |
| `model-gateway` | LiteLLM 路由外部模型 API、配额和调用观测 | 不作为事实来源 |
| `scheduler` | 文档更新、接口审计、评测任务 | 不参与在线回答 |

MVP 可将 `agent-api`、`agent-worker`、`rag-api` 合并为一个 Python 服务，`model-gateway` 用 LiteLLM 库内嵌调用（无需独立进程），但代码边界和数据表保持独立。`fund-advisor-mcp` 仍建议隔离进程，避免上游阻塞拖垮 Agent。

## 6. Agent 编排设计

### 6.1 状态机

推荐使用固定状态图：

```text
RECEIVED
  -> CLASSIFY_INTENT
  -> LOAD_USER_CONTEXT
  -> RESOLVE_ENTITIES
  -> COLLECT_TOOL_FACTS
  -> RETRIEVE_DOCUMENTS
  -> BUILD_EVIDENCE
  -> VALIDATE_EVIDENCE
  -> CHECK_SUITABILITY
  -> BUILD_CLAIMS
  -> COMPOSE_REPORT
  -> VALIDATE_RESPONSE
  -> COMPLETED

任意节点
  -> NEED_CLARIFICATION
  -> PARTIAL_RESULT
  -> CANNOT_CONFIRM
  -> POLICY_BLOCKED
```

模型可以在受限 Schema 内完成意图分类、查询改写和文字表达，但不能跳过节点或决定数据是否合格。证据校验、时效和数值一致性由代码控制。

该状态图用 **LangGraph** 实现：每个节点是一个纯函数，状态在节点间显式传递，条件边负责路由到 `NEED_CLARIFICATION`、`CANNOT_CONFIRM` 等分支。选择 LangGraph 是为了获得内置的状态持久化（checkpointer）、断点续跑和可视化，同时保持「固定图、不自治」的约束。

### 6.2 意图类型

| 意图 | 必需工具 | 可选 RAG | 必需用户信息 |
| --- | --- | --- | --- |
| 基金搜索 | `fund_search` | 无 | 模糊名称 |
| 产品分析 | `fund_analyze` | 招募说明书、定期报告 | 无 |
| 能否申赎 | `fund_status` | 交易规则 | 无 |
| 产品档案 | `fund_profile` | 无（费率/配置走实时接口） | 无 |
| 基金评级 | `fund_rating` | 无 | 无 |
| 指数估值 | `index_valuation` | 指数编制方案 | 无 |
| 个股估值 | `stock_valuation` | 公司公告和定期报告 | 无 |
| 基金比较 | `fund_compare` | 产品文档 | 同类产品确认 |
| 定投参考 | `fund_analyze`、必要时 `index_valuation` | 方法论和产品风险 | 期限、预算、目标仓位、最大回撤 |
| 卖出/再平衡 | `fund_analyze`、`portfolio_analyze` | 产品变化文档 | 成本、仓位、目标、资金用途 |

### 6.3 禁止的动态行为

- 不允许模型创建任意工具名或自由拼接 Shell。
- 不允许根据工具失败改用模型记忆给出数值。
- 不允许未确认 A/C 类、ETF/联接或币种时自动选产品。
- 不允许把基金净值历史位置写成估值分位。
- 不允许把 PE 与 PB 平均成综合估值。
- 不允许将 RAG 中历史报告的数值描述为当前数据。

## 7. MCP 工具设计

### 7.1 工具集合

| MCP 工具 | Skill 动作 | 关键参数 |
| --- | --- | --- |
| `fund_search` | `search` | `query`, `limit` |
| `fund_status` | `status` | `fund` |
| `fund_analyze` | `analyze` | `fund`, `years` |
| `fund_profile` | `profile` | `fund` |
| `fund_rating` | `rating` | `fund` |
| `index_valuation` | `valuation` | `index`, `years`, `max_points` |
| `stock_valuation` | 可导入方法 | `stock`, `years`, `max_points` |
| `fund_compare` | `compare` | `funds`, `years` |
| `interface_audit` | `audit` | 代表基金、ETF、LOF、指数 |

`fund_profile` 聚合基金基本信息、费率规则和资产配置，`fund_rating` 返回多家机构
评级；两者把原本依赖固定文档的产品事实收敛为实时可审计工具，均带 `frame_sha256`。

网页研究使用独立 `web-research-mcp`，不与市场事实工具混用：

| MCP 工具 | 用途 | 关键参数 |
| --- | --- | --- |
| `web_search` | 搜索公开网页背景 | `query`, `max_results`, `freshness_days` |
| `web_fetch` | 安全抓取并清洗网页正文 | `url`, `max_chars` |

Web 工具固定返回 `numeric_allowed=false` 和 `purpose=background_only`，不能覆盖
`fund-advisor-mcp` 的市场事实。详细契约见
[Web Research MCP](WEB_RESEARCH_MCP.md)。

### 7.2 统一工具信封

```json
{
  "schema_version": "1.0",
  "request_id": "uuid",
  "tool": "index_valuation",
  "ok": true,
  "data": {},
  "sources": [],
  "data_audit": [],
  "data_warnings": [],
  "data_policy": {
    "ai_may_generate_market_data": false
  },
  "queried_at": "RFC3339",
  "error": null
}
```

适配器只增加信封和传输元数据，不修改 `data` 内的值。`frame_sha256`、源日期和告警必须原样保留。

### 7.3 MCP 实现选项

| 方案 | 推荐场景 | 优点 | 代价 |
| --- | --- | --- | --- |
| Python MCP SDK | **推荐 MVP** | 与现有 Python Skill 集成最直接 | 需要独立进程治理 |
| FastMCP | 快速开发 | 声明式、样板代码少 | 生产约束需自行补齐 |
| Go MCP SDK | 高并发网关 | 易部署、资源占用低 | 仍需调用 Python 核心 |
| HTTP/OpenAPI Tool | 不支持 MCP 的平台 | 兼容性广 | Agent 工具发现能力较弱 |

MCP 服务调用 `FundAdvisor` Python API 优于启动一次 CLI 子进程；但必须保留 CLI 作为独立验证和故障诊断入口。

## 8. 证据与反幻觉设计

### 8.1 证据类型

| 类型 | 来源 | 示例 |
| --- | --- | --- |
| `TOOL_FACT` | MCP 工具 | PE、PB、净值、申赎状态 |
| `DERIVED_METRIC` | 确定性代码 | 回撤、分位、组合权重 |
| `DOCUMENT_FACT` | RAG 文档片段 | 投资范围、费用条款 |
| `USER_FACT` | 用户确认 | 持仓成本、投资期限 |
| `POLICY_RULE` | 版本化规则 | 高溢价暂停当前场内渠道 |
| `MODEL_INTERPRETATION` | LLM | 对已验证事实的自然语言解释 |

### 8.2 Evidence Record

```json
{
  "evidence_id": "ev_uuid",
  "type": "TOOL_FACT",
  "subject": {"type": "index", "id": "000300"},
  "field": "pe_ttm.percentile",
  "value": 31.2,
  "unit": "percent",
  "as_of": "2026-07-22",
  "source_ref": "tool_call_uuid",
  "audit_ref": "frame_sha256",
  "freshness": "valid",
  "confidence": "high"
}
```

### 8.3 Claim Record

报告生成前先产出结构化 Claim：

```json
{
  "claim_id": "cl_uuid",
  "text_template": "沪深300 PE TTM 位于所选历史区间的中低位置",
  "evidence_ids": ["ev_1", "ev_2"],
  "claim_type": "interpretation",
  "allowed": true
}
```

数值只能从 `evidence_ids` 指向的结构化字段渲染，禁止模型在正文中自行写入新数值。最终验证器应检查：

- 每个数值是否存在证据字段。
- 单位、日期和主体是否一致。
- 工具审计是否通过。
- 数据是否超过时效阈值。
- 告警是否已在报告中披露。
- Claim 是否把事实、计算、规则和观点混写。

### 8.4 证据门禁结果

| 等级 | 条件 | 输出权限 |
| --- | --- | --- |
| `A` | 工具成功、审计通过、时效合格、实体唯一 | 完整分析 |
| `B` | 市场数据合格，产品文档缺失 | 数据分析并披露文档缺失 |
| `C` | PE/PB 单侧可用或存在非关键告警 | 有限分析，不给强操作倾向 |
| `D` | 数据过期、实体歧义、关键工具失败 | 当前无法确认 |
| `E` | 要求保证收益、规避审计或自动交易 | 策略拒绝 |

## 9. RAG 高层设计

### 9.1 文档范围

| 文档类型 | 来源优先级 | 更新策略 |
| --- | --- | --- |
| 基金合同/招募说明书 | 基金公司、证监会指定披露站点 | 新版本触发更新 |
| 定期报告 | 官方披露源 | 季报/半年报/年报 |
| 指数编制方案 | 指数公司官网 | 版本变更更新 |
| 监管规则 | 证监会、交易所、基金业协会 | 公告触发更新 |
| 内部方法论 | 经审核的版本库 | 人工发布 |

新闻和自媒体默认不进入核心 RAG。若后续增加新闻服务，必须单独标记为低置信度事件证据，且不能覆盖工具事实。

### 9.2 索引与 JIT 的取舍

本项目参考 Mira 的 **JIT（Just-In-Time）按需检索**理念：**默认不预先把所有文档灌进大索引**，而是保留文档入口（URL/token + 轻量元数据），模型按当前问题按需调用检索工具。这样上下文更干净、时效更好、成本更低。

仅对**需要语义检索**的内部文档做轻量索引（解析 → 分块 → 向量化），供「基金文档知识检索」通道使用；指定文档直接读取、互联网检索都**不预建索引**。

```text
轻量索引（仅知识检索通道用）：
  Source Registry -> Fetch -> MIME 校验
    -> Parse (MinerU) -> Structure-aware Chunking
    -> Metadata Enrichment -> Embedding (BGE-M3)
    -> 向量库 -> Publish Version

JIT 通道（无需预建索引）：
  指定文档读取 / 互联网检索在问答时实时拉取
```

### 9.3 文档元数据

```json
{
  "document_id": "uuid",
  "doc_type": "fund_prospectus",
  "fund_code": "000001",
  "issuer": "基金管理人",
  "title": "更新的招募说明书",
  "source_url": "https://official.example/...",
  "publish_date": "2026-06-30",
  "effective_date": "2026-07-01",
  "version": "2026-01",
  "page": 32,
  "section_path": ["基金的投资", "投资范围"],
  "content_sha256": "...",
  "access_level": "public"
}
```

### 9.4 检索策略（Agentic RAG）

本项目的 RAG **参考飞书 Mira 的 Agentic RAG 设计**：RAG 不是单一模块，而是**分布在多个检索工具中的能力**，由 LangGraph 编排的 Agent 自主决定「要不要检索、用哪个通道、要不要多轮换词、要不要深挖原文」。三个检索通道如下（对标 Mira 的 `knowledge_answer` / `read_lark_content` / `web_search`）：

| 通道 | 对标 Mira | 本项目用途 | 检索方式 |
| --- | --- | --- | --- |
| 通道一 · 基金文档知识检索 | `knowledge_answer` | 招募书、定期报告、指数方案、监管规则的语义检索 | 轻量索引 + 向量语义检索（默认关闭） |
| 通道二 · 指定文档精确读取 | `read_lark_content` | 用户给出基金公告/文档 URL 时直接读全文 | JIT 直接读取，不做语义检索 |
| 通道三 · 互联网背景检索 | `web_search` + `web_fetch` | 政策、新闻等**定性背景**补充 | JIT 实时搜索 + 抓原文 |

> **金融红线（本项目对 Mira 的关键收紧）**：通道三只用于**非数值的定性背景**，结果标记为低置信度事件证据；**任何净值、PE/PB、收益率、申赎状态等市场数值只能来自 AKShare Skill/MCP**，web 与文档 RAG 一律不得产出或覆盖数值。

> **通道一默认关闭（`rag.knowledge_enabled=false`）**：金融投资场景不依赖固定文档语料库。费率、资产配置、评级、基本信息等**产品事实优先走实时 Skill 工具**（`fund_profile`、`fund_rating` 等）；条款类问题优先通道二 JIT 读原文，取不到就诚实返回“当前无法确认”。仅在确有官方语料索引需求时才开启通道一。

### 9.5 Agentic 检索循环

由 LangGraph 编排，检索是图中的可循环节点：

1. **规划**：判断是否需要检索、拆解子问题、选择通道（简单问题可不检索，对应 JIT）。
2. **检索**：调用对应通道；通道一按 `fund_code`、`doc_type`、`effective_date` 过滤后语义检索。
3. **充分性判断**：Agent 评估召回是否覆盖问题；不足则换词重搜、换通道或深挖原文（多轮）。
4. **证据化**：命中内容转成带 `source_ref`、`page`、`version` 的 Evidence；同一事实优先最新有效官方文档。
5. **生成**：模型仅基于通过门禁的 Evidence 生成，并按 `[[标题]](url)` 标注引用；检索不到就明说，不编造。

检索循环的**步数、换词/深挖次数有硬上限**，每一跳的通道、参数和命中都进审计，保证可追溯、不失控。这套设计对应 Mira 的 Agentic RAG（自主编排）+ JIT（按需检索）+ 多源融合 + 引用标注。

当前实现已将 `PLAN_RETRIEVAL`、`RETRIEVE` 和 `ASSESS_SUFFICIENCY` 作为
LangGraph 显式节点。LLM 可以提出候选查询和缺口判断，代码负责通道权限、可信 URL、
实体过滤、查询数、上下文长度和最大轮次；异常时回退确定性策略。每轮
`retrieval_trace` 进入 Task State 和 Elasticsearch 审计索引。

### 9.6 组件选型

| 能力 | 选定 | 备选 |
| --- | --- | --- |
| 检索范式 | Agentic RAG（LangGraph 编排，参考 Mira） | 一次性检索→生成（Naive RAG） |
| 通道一：知识检索 | 简单向量语义检索起步（默认关闭） | LightRAG/GraphRAG（进阶可选）、LlamaIndex、Haystack |
| 通道二：精确读取 | 自建文档读取工具（走对象存储/URL） | — |
| 通道三：互联网 | 独立 `web-research-mcp`：web_search + web_fetch（仅非数值背景，已实现） | 多供应商搜索兜底链 |
| 文档解析 | MinerU（含内置 OCR，强表格/公式/扫描件） | Docling、Unstructured、Tika |
| Embedding | BGE-M3（走 API 或 CPU） | `multilingual-e5-large`、GTE |
| 向量存储 | pgvector（复用 PostgreSQL） | Qdrant、Milvus |
| 关键词/全文检索 | Elasticsearch（并复用于日志/审计） | pgvector + PG FTS |
| Reranker | `bge-reranker-v2-m3` | Jina reranker、本地 cross-encoder |

知识检索通道 MVP **先用简单向量语义检索**（pgvector + BGE-M3）快速跑通，把重点放在 Agentic 编排和 Evidence 门禁上；**LightRAG/GraphRAG 作为「通道一的进阶实现」可选项**，在需要实体关系推理（如"某基金经理管过哪些产品"）时再引入，不作为 MVP 必需。

阶段落地顺序：先做通道二（指定文档读取，最简单）→ 通道一（文档语义检索 + Evidence）→ 用 LangGraph 把单通道升级为 Agentic 多通道循环 → 最后接通道三（web，严格限定非数值）。

## 10. 用户画像与组合服务

### 10.1 用户画像

- 风险等级和评估时间。
- 投资期限、应急资金状态、稳定现金流。
- 最大可承受回撤。
- 目标资产配置和单品上限。
- 是否允许场内交易、QDII 和汇率风险。

画像必须由用户确认并设置有效期。缺少关键字段时，Agent 只能给一般研究结论，不能给具体金额。

### 10.2 持仓数据

- 基金代码、份额类型、交易渠道。
- 持有份额、平均成本、当前目标权重。
- 录入来源、更新时间和币种。

持仓应与对话文本分离存储，按用户授权读取。组合收益、权重、集中度和再平衡金额全部由确定性服务计算。

## 11. 数据存储

| 数据 | 推荐存储 | 保留策略 |
| --- | --- | --- |
| 用户、画像、持仓、任务元数据 | PostgreSQL | 按隐私和审计策略 |
| 文档元数据、Claim、Evidence | PostgreSQL JSONB | 支持版本和追踪 |
| 文档分块与语义向量 | PostgreSQL + pgvector | 与文档版本同步 |
| 文档关键词索引 | Elasticsearch | PostgreSQL 文档分块的可重建检索副本 |
| 审计/证据/报告全文检索 | Elasticsearch（PG 的检索副本，非主库） | 与 PG 同步，可重建 |
| 原始文档 | SeaweedFS 或 MinIO | 不可变对象和哈希 |
| 短期缓存、限流、任务锁 | Redis | TTL |
| 指标和 Trace | Prometheus / Tempo | 分层保留 |
| 日志 | Elasticsearch + Kibana（复用 RAG 集群） | 脱敏后保留 |

不得在日志中记录完整持仓、访问令牌、模型密钥或原始私有文档。工具原始 JSON 可加密保存到审计存储，但在线日志只保留引用 ID 和摘要。

由于 RAG 已部署 Elasticsearch，关键词检索、日志、审计与报告的全文检索一并复用同一集群，减少组件数量。但复用有边界：语义向量由 PostgreSQL + pgvector 保存，ES 只作**关键词检索与日志层**；PostgreSQL 仍是用户、持仓、文档分块、Evidence 的**强一致主库**，指标仍归 Prometheus。进入 ES 的文档、审计和证据都是 PG 的检索副本，可从 PG 重建，ES 不承担事务一致性。

## 12. 缓存与时效

缓存不能绕过 Skill 自身的时效检查。

| 数据 | 建议缓存 | 备注 |
| --- | --- | --- |
| 基金目录 | 6-24 小时 | 支持手动失效 |
| 基金资料/费用 | 24 小时 | 仍展示源日期 |
| 净值和历史指标 | 交易日内 15-60 分钟 | 以源最新日期为准 |
| ETF 即时行情 | 15-60 秒 | 不作为券商级实时行情 |
| 申赎状态 | 5-15 分钟 | 平台状态可能不同 |
| PE/PB 历史 | 30-60 分钟 | 最新日期仍须合格 |
| RAG 文档 | 按版本长期缓存 | 新版本原子切换 |

缓存键必须包含工具名、规范化参数、Skill 版本和 Schema 版本。缓存值保留完整审计字段，不只缓存业务数据。

## 13. 模型层

### 13.1 模型职责

- 意图分类和实体候选提取。
- RAG 查询改写与文档摘要。
- 根据通过门禁的 Claims 生成专业中文报告。
- 不负责金融数值计算、时效判断或工具结果修复。

### 13.2 模型接入方式

MVP 默认通过 **LiteLLM 直连外部 OpenAI 兼容模型 API**，不自建推理服务，降低运维和 GPU 成本。

| 类型 | MVP 默认 | 可选 |
| --- | --- | --- |
| 接入方式 | LiteLLM 直连外部模型 API | 后续自建推理服务 |
| 主报告模型 | 一个可配置的外部 API 模型 | 更换为其他 API 或本地权重模型 |
| 意图/分类 | 与主模型同一 API（或规则） | 小参数本地模型、BERT/RoBERTa |
| 自建推理（可选） | 不启用 | vLLM、SGLang、TGI、llama.cpp |

LiteLLM 的作用是隔离供应商：业务代码只面向统一接口，换模型或换厂商不改编排和证据门禁。所有模型密钥经环境变量或密钥管理注入，不写入代码或日志。

具体模型需基于中文金融评测选择，不能只看通用榜单。生产环境应支持：

- 一个默认外部 API 模型作为主路径。
- 一个备用模型作为灾备或高难度报告路径。
- 后续可切换为完全私有部署（自建推理 + 本地权重）。

所有模型调用必须使用结构化输出 Schema、固定温度区间和版本化提示词。模型切换不得改变证据门禁规则。

生产 Prompt 统一在 `src/financial_agent/prompts/` 中版本化管理，业务节点不得维护内联
system prompt。Prompt 只能约束模型语言行为，不能替代实体解析、数据审计、Evidence
Gate 和 Response Validator。详细规则见
[Prompt 设计与治理](PROMPT_DESIGN.md)。

外部 API 会把用户问题和部分上下文发送给第三方；启用前必须确认数据出境、隐私和合规要求。若不允许外部传输，则改用自建推理的私有部署模式。模型“可下载权重”不等于 OSI 定义的开源软件，逐模型审查许可证和使用政策。

**持仓脱敏（个人自用约定）**：问题原文和公开基金数据可进外部模型 prompt，但持仓、成本、金额等隐私字段必须先脱敏或改为定性描述（如「某沪深300指数基金、仓位偏高」而非具体金额）再进 prompt；确定性的组合计算在本地完成，不依赖外部模型。

## 14. 开源组件推荐矩阵

| 层 | MVP 推荐 | 可选方案 |
| --- | --- | --- |
| API | FastAPI | Gin、Litestar |
| Agent 编排 | LangGraph | 自研有限状态机、Haystack Pipeline |
| MCP | Python MCP SDK | FastMCP、Go MCP SDK、OpenAPI Tool |
| 任务队列 | 不引入（同步执行） | Dramatiq、Celery、Arq、Temporal |
| 数据库 | PostgreSQL | YugabyteDB（多地域） |
| 检索范式（RAG） | Agentic RAG on LangGraph（参考 Mira） | 一次性检索→生成 |
| RAG 通道 | 知识检索 + 指定文档读取 + web 背景 | 单一向量库检索 |
| 知识检索实现 | 向量语义检索（pgvector + BGE-M3） | LightRAG/GraphRAG（进阶）、LlamaIndex |
| 文档解析（RAG） | MinerU | Docling、Unstructured、Tika |
| 向量存储（RAG） | pgvector（复用 PostgreSQL） | Qdrant、Milvus |
| 关键词检索 + 日志/审计 | Elasticsearch | pgvector + PG FTS |
| 对象存储 | 本地文件 | SeaweedFS、MinIO、Ceph |
| 模型接入 | LiteLLM + 外部模型 API | 自建推理：vLLM、SGLang、TGI、llama.cpp |
| 缓存/限流 | Redis | 内存缓存（更简）、KeyDB |
| 策略引擎 | Python/Pydantic 规则 | OPA、Cedar |
| 可观测性 | OpenTelemetry + 结构化日志 | Prometheus、Grafana、Tempo |
| 日志/审计检索 | Elasticsearch + Kibana（复用 RAG 集群） | Loki、OpenSearch |
| 身份认证 | 本地 token / 单用户 | Keycloak、Zitadel、Authentik |
| 密钥管理 | 环境变量 / `.env` | OpenBao、云 KMS |
| 容器 | Docker Compose | Kubernetes、Nomad |

MVP 目标是「先能跑通产品」，因此默认**不引入**：独立向量库、独立对象存储、任务队列、独立监控栈、认证系统和自建推理。这些都放在可选列，等容量、并发或多用户需求出现后再逐项加入。

### 14.1 开源与许可证治理

组件选型必须同时满足功能、运维和许可证要求。下表中的许可证分类仅用于架构阶段筛选，最终以锁定版本仓库中的 `LICENSE`、模型许可证和法律审核为准：

| 分类 | 组件示例 | 架构处理 |
| --- | --- | --- |
| 宽松开源 | PostgreSQL、Redis、Qdrant、OpenSearch、OpenTelemetry、Prometheus、SeaweedFS、Keycloak | 默认优先，仍需保留版权声明和 NOTICE |
| Copyleft 开源 | MinIO、Grafana、Loki、Tempo、部分插件 | 可以自部署，但需评估网络分发、修改和源码提供义务 |
| 开放权重模型 | Qwen、DeepSeek、Llama、Mistral 的具体版本 | 逐模型审核，不笼统标记为开源 |
| Source-available | Elasticsearch（SSPL/Elastic License）、部分数据库或商业增强版 | 个人自用无碍；若做纯开源发行或对外托管需评估，或换 OpenSearch |
| SaaS/商业 API | 外部模型 API（MVP 默认经 LiteLLM 接入）、云 KMS、托管数据库 | 必须可关闭，并提供自建推理的私有部署替代路径 |

供应链要求：

- 锁定直接和传递依赖版本，保存容器镜像 digest。
- 使用 Syft 生成 SPDX/CycloneDX SBOM。
- 使用 Grype 或 Trivy 扫描漏洞，使用 ScanCode Toolkit 或 ORT 扫描许可证。
- 记录模型权重哈希、模型卡、许可证和推理镜像版本。
- 禁止运行时从未登记地址下载模型、代码、插件或提示词。
- 每次升级重新执行许可证、漏洞、金融回归和证据忠实度测试。

## 15. API 设计

### 15.1 用户接口

```text
POST /v1/conversations
POST /v1/conversations/{id}/messages
GET  /v1/tasks/{id}
GET  /v1/reports/{id}
GET  /v1/reports/{id}/evidence
PUT  /v1/users/me/risk-profile
PUT  /v1/users/me/portfolio
```

消息接口返回：

- `task_id`
- 当前状态
- 需要补充的问题
- 流式报告事件
- 最终报告 ID

### 15.2 报告结构

```json
{
  "summary": {},
  "position_and_valuation": {},
  "product_fit": {},
  "buy_conditions": [],
  "sell_or_rebalance_conditions": [],
  "dca_reference": {},
  "risks": [],
  "missing_information": [],
  "warnings": [],
  "citations": [],
  "evidence_grade": "A",
  "generated_at": "RFC3339"
}
```

报告中的每个数值字段携带 `evidence_id`，前端可展开查看来源、日期、接口和审计状态。

## 16. 安全、隐私与合规

### 16.1 安全控制

- OIDC/OAuth2 登录，服务间使用短期凭证。
- MCP 工具白名单和 Pydantic/JSON Schema 参数验证。
- 出站网络白名单，只允许 AKShare 所需上游和登记文档源。
- RAG 文档视为不可信输入，过滤提示注入和外部指令。
- 上传文件进行 MIME、大小、压缩炸弹和恶意软件检查。
- PostgreSQL 行级权限或服务层租户隔离。
- TLS、静态加密、密钥轮换和日志脱敏。

### 16.2 金融合规边界

- 明确区分事实、派生指标、规则和模型解释。
- 不使用“必买、必卖、稳赚、无风险、抄底、逃顶”等表达。
- 未完成用户画像时不输出具体金额。
- 高风险产品、数据冲突或异常大额建议进入人工复核。
- 保留免责声明、数据日期和来源，但免责声明不能代替事实校验。
- 上线前需由目标运营地区的法律与合规人员审查适当性和数据授权。

## 17. 可观测性与审计

每个请求生成统一 `trace_id`，关联：

- 用户请求和规范化意图。
- Agent 状态迁移。
- MCP 工具参数、耗时、返回状态和 `frame_sha256`。
- RAG 查询、命中文档版本和片段。
- Evidence、Claim、策略决策和拒绝原因。
- 模型、提示词、温度、Token 和结构化输出校验。
- 最终报告版本。

关键指标：

- 工具成功率、超时率、Schema 失败率和数据过期率。
- RAG 无结果率、引用覆盖率和版本冲突率。
- 数值引用覆盖率、无证据 Claim 拒绝数。
- 澄清率、“当前无法确认”率和策略阻断率。
- P50/P95 延迟、模型 Token 成本和缓存命中率。

日志、trace 关联字段和审计留痕统一写入 Elasticsearch（复用 RAG 集群），通过 Kibana 按 `trace_id`、基金代码、时间或来源检索历史调用与结论；指标仍由 Prometheus 抓取，不进 ES。

## 18. 可靠性与降级

### 18.1 降级顺序

1. PE/PB 单侧失败：展示有效侧并降低证据等级。
2. RAG 失败：保留工具事实，明确缺少产品文档解释。
3. 用户画像缺失：只给一般研究结论并追问。
4. 主模型失败：切换已配置模型；证据和 Claims 不变。
5. Skill 关键数据失败或过期：返回“当前无法确认”，不调用模型补数据。
6. 审计字段缺失：阻止数值进入最终报告。

不存在、歧义、不支持和上游不可用必须使用不同错误语义，详细映射见
[错误处理与降级契约](ERROR_HANDLING.md)。

### 18.2 服务目标建议

- Agent API 月可用性：MVP `99.5%`，生产 `99.9%`。
- 已缓存简单查询 P95：小于 5 秒。
- 完整基金分析 P95：小于 30 秒，不含上游长时间故障。
- 无证据金融数值进入报告：目标为 0。
- 所有最终报告证据可追溯率：100%。

## 19. 测试与评测

### 19.1 工程测试

- Skill 单元测试和真实接口审计。
- MCP 参数、错误映射和并发隔离测试。
- RAG 解析、版本、元数据过滤和引用测试。
- 状态机路径、超时、重试、幂等和降级测试。
- 权限、租户隔离、提示注入和日志泄漏测试。

### 19.2 金融 Agent 评测集

至少建立以下数据集：

- 工具路由：问题是否选择正确工具。
- 实体解析：A/C 类、ETF/联接、同名产品和子指数歧义。
- 数值忠实度：报告数值是否逐项匹配 Evidence。
- 时效性：过期数据是否被拒绝。
- 概念边界：净值位置与估值分位、PE 与 PB 是否混淆。
- RAG 引用：产品条款是否来自正确版本和页码。
- 适当性：缺少风险画像时是否避免具体金额。
- 对抗测试：用户诱导编造、提示注入、工具失败和证据冲突。

上线门槛建议：

- 数值忠实度 `100%`。
- 关键工具路由准确率大于 `98%`。
- 实体歧义拒绝准确率大于 `99%`。
- 过期数据拦截率 `100%`。
- 无引用产品事实率小于 `1%`，关键条款为 `0%`。

## 20. 分阶段实施

### 阶段 1：可信工具闭环（已完成）

- 实现 `fund-advisor-mcp` 九个工具。
- 定义 `ToolEnvelope`、Evidence 和 Claim Schema。
- 用 LangGraph 状态机完成搜索、分析、估值三条链路。
- 用 LiteLLM 直连外部模型 API 生成报告。
- 接入 PostgreSQL、Redis、结构化日志。
- 建立数值忠实度和工具路由评测。

### 阶段 2：Agentic RAG（三通道，主链路已完成）

- **通道二先行**：实现指定文档精确读取工具（最简单，JIT 直接读全文）。
- **通道一**：MinerU 解析 + BGE-M3 向量化建轻量索引，pgvector 语义检索，自建 Evidence 适配层（命中转带页码/版本的 Evidence，接证据门禁）。
- **Agentic 编排**：用 LangGraph 把单通道升级为多通道检索循环（规划、选通道、充分性判断、多轮，步数设上限）。
- **通道三**：接 web_search + web_fetch，**严格限定非数值背景**，结果标记低置信度事件证据。
- 加引用标注 `[[标题]](url)`、提示注入防护和文档质量审核；进阶可选 LightRAG/GraphRAG 增强通道一。

### 阶段 3：用户与组合（MVP 已完成）

- 增加风险画像、持仓和组合计算服务。
- 实现仓位、集中度、回撤承受和再平衡条件。
- 对具体金额和高风险建议增加人工复核。

### 阶段 4：生产治理（部分完成）

- 模型网关、多模型灾备、配额和成本控制。
- Keycloak/OpenBao、安全审计和数据保留策略。
- 压测、灾备、SLO、告警和定期红队评测。
- 根据规模决定是否迁移 Kubernetes、OpenSearch、Temporal 或 OPA。

## 21. 推荐 MVP 技术栈

目标是最快跑通一个可用产品，只保留必要组件：

```text
Python 3.11+
FastAPI + Pydantic
LangGraph（编排状态机）
Python MCP SDK
PostgreSQL
Redis（缓存/限流）
MinerU + BGE-M3 + pgvector + Elasticsearch（三通道 Agentic RAG）
LiteLLM + 外部模型 API
OpenTelemetry + 结构化日志
Docker Compose
```

当前已用 `FastAPI + LangGraph + MCP + PostgreSQL + Redis + LiteLLM` 打通
「搜索→分析→估值→带证据报告」主链路，并实现第 9 节的三通道 Agentic RAG。
外部 Embedding、MinerU 和 Web Search 按配置启用。扩展方向仍保留在第 14 节：
知识检索需要实体关系推理时再上 LightRAG/GraphRAG，需要私有部署时再用自建推理替换
外部 API，需要多用户时再增加认证和监控栈。

## 22. 关键架构决策

| 决策 | 选择 | 原因 |
| --- | --- | --- |
| Agent 形态 | LangGraph 单一受控状态机 | 固定图可预测、可测试，优于自治多 Agent |
| 市场数据 | 只走 Skill/MCP | 防止 RAG 和模型记忆污染当前事实 |
| 文档知识 | 官方来源 RAG | 保留版本、页码和来源 |
| RAG 范式 | 三通道 Agentic RAG（参考 Mira） | 多工具编排、JIT 按需检索、多源融合、引用标注 |
| 数值生成 | Evidence 模板渲染 | 阻止模型创造新数值 |
| 计算位置 | Skill/组合服务 | 确定性、可回归、可审计 |
| 模型选择 | LiteLLM + 外部 API，可换自建 | MVP 免运维，网关解耦避免锁定 |
| 首版部署 | Docker Compose | 控制复杂度并快速闭环 |
| 交易能力 | 不支持 | 降低安全、合规和资金风险 |

## 23. 已确认事项（个人自用）

- **定位**：个人自用，非公开产品、非持牌机构工具；不做多租户、认证、人工投顾审核。
- **外部模型**：可用 LiteLLM + 外部 API 处理问题和公开基金数据；**持仓/成本等隐私先脱敏再进 prompt**（如只发「某沪深300指数基金」不发金额）。
- **文档来源**：仅从官方公开披露渠道（基金公司官网、交易所、巨潮资讯等）下载，个人研究用途；按季报/年报节奏手动更新；保留历史版本以支持结论追溯。
- **数据存储**：用户画像与持仓存本机，保留周期自定，不涉及跨地区合规。
- **规模与算力**：个人小规模、不使用 GPU；MinerU、Embedding 走 CPU 或外部 API。
- **目标地区**：仅本人（中国大陆），不涉及对外发行的适当性与隐私法规。
- **RAG 范式**：参考飞书 Mira 做三通道 Agentic RAG（知识检索 / 指定文档读取 / web 背景）；web 通道严格限定非数值，市场数值只走 AKShare。

仍需在锁定版本/实现时以真实情况核对（不臆断）：

- MinerU 在无 GPU（纯 CPU）下的解析速度是否可接受；不行则退回 Docling 等更轻方案。
- 互联网通道 `web_search` / `web_fetch` 的具体实现（用哪个搜索 API 或库），个人自用需可获取且合规。
- 通道一进阶选项 LightRAG/GraphRAG 引入时，其后端支持与成本再评估。
