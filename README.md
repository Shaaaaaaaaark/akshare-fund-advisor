# Financial Investment Agent

面向个人使用和 GitHub 开源的基金与指数投资研究 Agent。项目采用 Docker Compose 统一运行，核心原则是：市场数据只来自可审计工具，金融计算由确定性代码完成，大模型负责受控编排与解释。

当前已打通 `API -> LangGraph -> MCP -> AKShare Skill -> Evidence -> Claim -> Report` 主链路，并实现三通道 RAG、用户画像、组合计算、持久化、缓存、可观测性和 Docker Compose。

## Web 界面

API 启动后访问 `http://127.0.0.1:8000/`，即可使用内置的轻量研究界面。界面支持问题输入、示例查询、可选 Bearer Token，以及证据等级、关键事实、分析、风险和来源引用展示。

产品采用 Agent Chat 结构：

- 左侧管理多个独立对话；
- 中间进行连续追问，同一对话会继承已确认的基金或指数实体；
- 新建对话不继承旧对话内容，不提供跨对话全局记忆；
- 右侧固定展示研究摘要、关键数据、分析、风险和 Evidence；
- 指数估值报告展示 PE/PB 历史曲线、P20 机会值、P80 危险值和指数点位曲线。

前端由 FastAPI 直接托管，不需要安装 Node.js 或运行额外构建命令。

## 目录结构

```text
.
├── AGENTS.md                           # 代码助手与仓库级金融约束
├── CONTRIBUTING.md                     # 开发、测试和提交规范
├── SECURITY.md                         # 漏洞、密钥和隐私策略
├── docs/
│   ├── README.md                       # 文档索引与阅读顺序
│   ├── HLD.md                          # Agent 高层设计
│   ├── LLD.md                          # Agent 低层设计与面试讲解
│   ├── PROMPT_DESIGN.md                # Prompt 版本、边界与评测
│   ├── ERROR_HANDLING.md               # 错误码、状态与降级契约
│   └── WEB_RESEARCH_MCP.md              # 网页搜索与抓取工具
├── skills/
│   └── akshare-fund-advisor/          # 可独立打包的 AKShare Skill
├── src/
│   └── financial_agent/
│       ├── api/                       # HTTP/API 入口
│       ├── orchestration/             # LangGraph 受控状态机
│       ├── prompts/                   # 版本化生产 Prompt
│       ├── mcp_client/                # inprocess/stdio/http MCP 客户端
│       ├── mcp_server/                # 七个强类型 MCP 工具
│       ├── evidence/                  # Evidence/Claim 与证据门禁
│       ├── rag/
│       │   ├── ingestion/             # 官方文档摄取
│       │   └── retrieval/             # 混合检索与引用
│       ├── web_research/               # 独立网页研究 MCP 与客户端
│       ├── portfolio/                 # 用户画像与组合计算
│       ├── policies/                  # 适当性与合规规则
│       ├── observability/             # Trace、指标和审计
│       └── web/                       # 内置单页研究界面
├── mcp_servers/
│   ├── fund_advisor/                  # Skill 的 MCP 适配层
│   └── web_research/                  # 网页搜索 MCP 启动入口
├── evals/
│   ├── datasets/                      # 金融 Agent 评测集
│   └── runners/                       # 自动评测执行器
├── tests/
│   ├── integration/                   # 跨模块测试
│   └── e2e/                           # 端到端测试
└── deploy/
    └── compose/                       # 个人部署编排
```

这些目录是代码职责边界。Compose 将 API、MCP 和各存储组件隔离为独立容器。

## 当前能力

- AKShare Skill：基金搜索/状态/分析、指数与个股 PE/PB、价格曲线、比较和接口审计。
- MCP：七个基金、指数与个股工具，支持 `inprocess`、`stdio`、Streamable HTTP 三种传输。
- Web Research MCP：独立提供 `web_search` 和 `web_fetch`，RAG 与其他 Agent 可共用。
- LangGraph：固定状态图、工具白名单、实体歧义追问和 A-E 证据等级。
- 反幻觉：金融数字按 `ToolEnvelope -> Evidence -> Claim -> Renderer` 流转，最终响应再次校验。
- LiteLLM：可选意图分类和报告叙述；模型输出越界时回退确定性模板。
- Prompt：集中版本管理、结构化输出约束和契约测试，业务节点不使用内联 system prompt。
- Agentic RAG：LangGraph 显式执行检索规划、三通道检索、充分性判断和最多三轮缺口重查；简单市场问题通过 JIT 跳过文档检索。
- 存储：PostgreSQL + pgvector、Redis 和 Elasticsearch 容器化部署。
- 用户服务：风险画像、持仓存储、Decimal 组合计算和模型输入脱敏。
- 会话记忆：仅从当前 `conversation_id` 的历史 Task/Report 构造上下文。

## Docker Compose 运行

本机只需要 Docker Desktop，不需要安装 Python、Node.js、PostgreSQL、Redis 或 Elasticsearch。

```bash
cp config/config.example.yaml config/config.local.yaml
```

在 `config/config.local.yaml` 中填写 DeepSeek API Key。该文件只读挂载到 API 容器，不会写入镜像或 Git。

启用网页搜索时还需填写 Brave Search API Key：

```yaml
web_research:
  enabled: true
  api_key: "YOUR_BRAVE_SEARCH_API_KEY"
```

启动全部服务：

```bash
docker compose -f deploy/compose/compose.yaml up --build -d
```

Web 界面：`http://127.0.0.1:8000/`。

接口文档：`http://127.0.0.1:8000/docs`。

查看状态和日志：

```bash
docker compose -f deploy/compose/compose.yaml ps
docker compose -f deploy/compose/compose.yaml logs -f agent-api fund-advisor-mcp
```

停止服务：

```bash
docker compose -f deploy/compose/compose.yaml down
```

PostgreSQL、Redis、Elasticsearch 和文档使用 Docker named volume 持久化。仅在明确需要删除全部数据时执行：

```bash
docker compose -f deploy/compose/compose.yaml down -v
```

默认只有 `127.0.0.1:8000` 暴露给宿主机。MCP、PostgreSQL、Redis 和 Elasticsearch 只在 Compose 内部网络访问。

## 测试与评测

测试依赖只安装在 `test` 镜像，不进入运行镜像。该命令依次执行 Ruff 和 Pytest：

```bash
docker compose -f deploy/compose/compose.yaml \
  --profile test run --rm test
```

服务启动后执行工具路由评测：

```bash
docker compose -f deploy/compose/compose.yaml \
  exec agent-api python evals/runners/run_tool_routing.py
```

数据库迁移由 `migrate` 容器在启动时自动执行。

## 文档摄取

先将文档复制到容器持久卷：

```bash
docker compose -f deploy/compose/compose.yaml \
  cp ./document.pdf agent-api:/app/data/documents/document.pdf
```

再在 API 容器中摄取；未配置 Embedding API 时使用 `--without-embeddings`：

```bash
docker compose -f deploy/compose/compose.yaml exec agent-api \
  python scripts/ingest_document.py /app/data/documents/document.pdf \
  --source-url 'https://www.sse.com.cn/example/document.pdf' \
  --title '基金招募说明书' \
  --doc-type fund_prospectus \
  --version 2026-01 \
  --subject-code 000001 \
  --without-embeddings
```

配置 `rag.embedding_api_base` 和 BGE-M3 后移除 `--without-embeddings`，分块向量会写入 pgvector。

## 文档

- [文档索引](docs/README.md)
- [仓库 Agent 规范](AGENTS.md)
- [金融 Agent HLD](docs/HLD.md)
- [金融 Agent LLD](docs/LLD.md)
- [Prompt 设计与治理](docs/PROMPT_DESIGN.md)
- [错误处理与降级](docs/ERROR_HANDLING.md)
- [Web Research MCP](docs/WEB_RESEARCH_MCP.md)
- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [Skill 调用规范](skills/akshare-fund-advisor/SKILL.md)
- [Skill 使用说明](skills/akshare-fund-advisor/USAGE.md)
- [Skill 内部设计](skills/akshare-fund-advisor/DESIGN.md)

## 边界

本项目不执行交易、不承诺收益，也不允许模型生成或补齐净值、价格、PE、PB、收益率、回撤、申赎状态等金融事实。
