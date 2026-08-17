# TASK：可信投研数据工作台

> 状态：`待实施`
>
> 产品依据：[PRODUCT.md](../PRODUCT.md)
>
> 架构依据：[HLD.md](../HLD.md)
>
> 前置能力：Agent API、React Web 基础入口、Fund/Web MCP 和单标分析均已实现；
> Go 网页后端（BFF）待建，边界见 [Go/Python 透传契约](../GO_PYTHON_CONTRACT.md)。

## 1. 目标

将当前纯聊天首页升级为“数据优先、Agent 增强”的投研工作台：

- 用户不提问也能浏览基金、ETF、指数和 A 股的可信结构化数据；
- 页面支持搜索、筛选、排序、详情和明确的数据更新时间；
- Agent 可理解当前页面、筛选条件和已选标的，并继续执行受控研究；
- 金融数值由结构化 API 直接渲染，不经过模型提取、补齐或改写；
- 第一阶段继续使用 MCP 和有界进程内缓存，不引入数据库、Redis 或消息队列。

## 2. 非目标

- 不实现组合持仓、博主持仓、收益计算器或策略回测；
- 不实现登录、账号、多端同步和永久保存会话；
- 不实现实时交易行情终端、自动交易或收益预测；
- 不实现资讯抓取平台、RAG、向量库或 Elasticsearch；
- 不为页面列表绕过 MCP 直接调用 AKShare Skill；
- 不让模型解析网页或原始 DataFrame 后生成市场数值；
- 不把 `fund_screen`、`stock_screen` 或全量基金目录写成已经可用。
- 不继续开发产品 CLI；工作台新增功能只要求 Web 交付和验收。

## 3. 当前能力与缺口

### 3.1 当前可复用能力

| 页面需求 | 可复用工具 | 当前可行性 |
| --- | --- | --- |
| 指数关注池估值 | `index_valuation` | 可按配置的指数关注池并发聚合 |
| 基金搜索 | `fund_search` | 可用，但不是全市场分页目录 |
| 基金详情 | `fund_analyze/profile/rating/status` | 可并发聚合 |
| 基金比较 | `fund_compare` | 可比较两到五只明确基金 |
| 股票详情 | `stock_valuation` | 可用 |
| 标的研究动态 | `web_search` | 可按用户选择的标的查询 |
| Agent 问答 | Agent API + LangGraph | 已实现 |

### 3.2 明确缺口

| 目标能力 | 缺口 | 处理方式 |
| --- | --- | --- |
| 全市场基金库 | 当前没有分页基金目录 MCP 契约 | MVP 先做基金搜索/关注池；批量目录单独审计后再接入 |
| 基金候选榜单 | `fund_screen` 尚未实现 | 依赖 `TASK_asset_screening.md` |
| 股票候选榜单 | `stock_screen` 尚未实现 | 依赖 `TASK_asset_screening.md` |
| 全市场指数估值 | 当前工具一次查询一个指数 | MVP 使用版本化指数关注池，不对全市场作虚假承诺 |
| 持续更新快照 | 当前没有数据库或 Worker | 第一阶段按请求读取 + MCP TTL 缓存 |

页面遇到未实现能力时必须显示“能力尚未接入”，不得用空列表表示“没有候选”。

## 4. 交付顺序

```text
M0 Dashboard 契约和数据状态
  -> M1 指数估值看板（首个可用闭环）
  -> M2 基金搜索与单标详情
  -> M3 股票详情与研究动态
  -> M4 总览和统一导航
  -> M5 页面上下文 Agent
  -> M6 候选筛选接入（依赖 fund_screen / stock_screen）
  -> M7 数据库存储（仅在触发条件满足后）
```

M1、M2、M3 都必须可以单独上线和验收，不等待候选筛选或数据库。

## 5. 阶段 M0：Dashboard 契约和代码边界

### 5.1 服务位置

- [x] Dashboard 取数由 Go 网页后端（BFF）实现，作为对外唯一 HTTP 入口。
- [x] Go 后端作为 MCP Client 调用 Python Fund/Web MCP 获取数据。
- [x] Go 后端不 import 或复制 Skill 逻辑，不做任何金融计算，不调用模型。
- [x] Go 后端托管 React 构建产物，并把 Agent 请求反向代理到 Python Agent API。
- [x] Python Agent API 与两个 MCP 仅在容器网络内可达，不直接对外暴露。
- [x] 边界与透传规则遵循 [Go/Python 透传契约](../GO_PYTHON_CONTRACT.md)。

代码边界（已落地）：

```text
web-backend/            # Go 网页后端（BFF）
├── cmd/server/         # HTTP 入口、路由、优雅关闭
├── internal/dashboard/ # 取数、聚合、DatasetMeta、状态映射
├── internal/mcp/       # 无状态 streamable-HTTP MCP Client（json.RawMessage 透传）
├── internal/proxy/     # Agent SSE 反向代理
└── internal/static/    # React 产物托管 + SPA 回退

src/fund_advisor_app/   # Python：Agent API、临时会话、兼容 CLI（保留）
```

### 5.2 统一响应元数据

- [x] 定义 `DashboardDataStatus`：
  - `available`
  - `partial`
  - `stale`
  - `unavailable`
  - `not_implemented`
- [x] 定义 `DatasetMeta`：
  - `as_of`
  - `queried_at`
  - `status`
  - `source_tools`
  - `audit_refs`
  - `warnings`
  - `error`
- [x] 每个数据块独立携带元数据，不用页面级统一日期覆盖全部来源。
- [x] 保留 `NOT_FOUND`、`AMBIGUOUS`、`UNSUPPORTED`、`UPSTREAM_ERROR`、
  `STALE_DATA` 的原始语义（透传原始 `error.code`）。
- [x] 上游失败时返回 `unavailable`，不得回退为无数据或不存在。
- [x] 过期数据只能标记 `stale`，不得伪装为最新结果。

### 5.3 Dashboard 配置

第一阶段配置由 Go 网页后端读取环境变量（`DASHBOARD_INDEX_UNIVERSE`、
`DASHBOARD_INDEX_YEARS`、`DASHBOARD_CONCURRENCY`），Python 侧不新增 `dashboard`
配置段；后续接入 Python Dashboard 能力时再评估是否下沉到强类型配置。

- [x] 指数关注池版本化，由后端配置提供，不由模型或前端自由创建。
- [x] 关注池数量有默认上限，避免页面加载触发无界上游调用（有界并发 + 关注池长度）。
- [x] 环境变量可覆盖关注池、窗口和并发；示例配置和镜像不包含密钥。
- [x] 默认关注池只含 `index_valuation` 已支持的指数；不支持的指数会如实返回
  `INDEX_NOT_SUPPORTED` 并标记 `unavailable`，不伪装为无数据。
- [ ] `fund_watchlist`、`stock_watchlist` 关注池待 M2/M3 接入。

## 6. 阶段 M1：指数估值看板

这是首个可独立交付的工作台闭环，完全复用现有 `index_valuation`。

### 6.1 API

- [x] 新增 `GET /api/dashboard/indices`。
- [x] 只查询配置中的指数关注池。
- [x] 使用有界并发调用 `index_valuation`，不得无界 `gather`。
- [x] 单个指数失败不导致整页失败，页面状态为 `partial`。
- [x] 返回：
  - 规范指数名称和代码；
  - PE TTM 当前值和历史分位；
  - PB 当前值和历史分位；
  - 最新点位；
  - 每项指标的 `as_of` 和 `audit_ref`；
  - 缺失、过期或上游失败状态。
- [x] 不在 Dashboard 层计算综合估值分。
- [x] 不由 Dashboard API 生成“买入/卖出”标签。
- [x] 指数详情 API（`GET /api/dashboard/indices/{index}`）原样返回现有
  `charts.pe_ttm`、`charts.pb` 和可用的 `charts.index_points`。
- [x] 保留每侧的 `chart_series`、`reference_lines`、`window_statistics`、
  `source_observations` 和 `displayed_points`，Dashboard 层不得重新采样或补点
  （整个 `ToolEnvelope` 以 `json.RawMessage` 原样透传）。

### 6.2 Web

- [ ] 增加 `/indices` 页面和顶部主导航。
- [ ] 表格支持名称搜索、PE/PB 分位排序和状态筛选。
- [ ] PE、PB 独立列展示，不平均为综合分。
- [ ] 每行显示最新数据日期和数据状态。
- [ ] 点击指数进入详情页，默认展示十年 PE/PB 历史双图和可用的指数点位历史。
- [ ] PE TTM、PB 使用上下两张同步图，共享时间范围和缩放状态。
- [ ] 支持切换本次响应实际存在的 3/5/10/20 年窗口，不假设所有窗口都可用。
- [ ] 图表支持 tooltip、十字准星、data zoom 和当前点标记。
- [ ] 图表展示均值、中位数、P20、P80、均值 ±1 标准差参考线。
- [ ] 统计区展示当前值、历史分位、最高、最低、完整日频样本数和显示点数。
- [ ] 页面显示数据源、实际起止日期、最新日期、审计引用和“历史分位不预测未来”。
- [ ] PE 或 PB 单侧缺失时只展示可用图，并明确另一侧不可用；不得使用零值占位。
- [ ] 信息层次参考 Wind 深度资料，但不使用 Wind 商标、不声称是 Wind 数据或复制其专有界面。
- [ ] 表格、空态、部分失败、过期和加载状态使用稳定尺寸，避免布局跳动。
- [ ] 移动端改为可横向滚动表格或紧凑列表，不截断代码与长名称。

### 6.3 验收

- [ ] 页面数值能逐项反查 `index_valuation` 的字段和审计哈希。
- [ ] 页面实际渲染 PE/PB 历史曲线，不以当前值卡片或估值标签代替。
- [ ] 图表只连接 `chart_series` 的真实采样点，前端和模型都不补造中间点。
- [ ] 曲线抽样保留首尾、最高和最低；统计值仍来自完整日频样本。
- [ ] 任一指数上游失败时，其他指数仍可展示。
- [ ] `STALE_DATA` 不进入正常估值排序。
- [ ] 页面不调用 Ark 模型即可完整显示。

## 7. 阶段 M2：基金搜索、关注池与详情

### 7.1 API

- [ ] 新增 `GET /api/dashboard/funds/search?query=&limit=`。
- [ ] 参数约束与 `fund_search` 保持一致。
- [ ] 不自动选择 A/C 份额或名称歧义候选。
- [ ] 新增 `GET /api/dashboard/funds/{fund}`。
- [ ] 有界并发聚合：
  - `fund_analyze`
  - `fund_profile`
  - `fund_rating`
  - `fund_status`
- [ ] 可选工具失败返回部分结果，不覆盖必需市场工具错误。
- [ ] 聚合层不重算收益、波动、回撤、溢价或费率。
- [ ] 新增关注池接口，关注池代码只来自配置，不持久化用户操作。

### 7.2 Web

- [ ] 增加 `/funds` 页面，第一版标题使用“基金查询/关注池”，不冒充全市场基金库。
- [ ] 支持基金代码和名称搜索。
- [ ] 搜索结果展示规范代码、名称、类型和份额信息。
- [ ] 歧义结果要求用户选择，不自动跳转第一项。
- [ ] 基金详情按以下区块组织：
  - 产品信息；
  - 费用和规模；
  - 历史表现；
  - 风险和持有体验；
  - 申赎/交易状态；
  - 评级；
  - 数据来源和限制。
- [ ] ETF 溢价与基金净值位置分开展示。
- [ ] 主动基金不得显示“低估/高估”标签。

### 7.3 全量基金目录的独立门禁

- [ ] 在扩展为全市场基金库前，先审计批量基金目录接口：
  - 唯一代码；
  - 名称与份额类别；
  - 基金类型；
  - 场内/场外标识；
  - 更新日期；
  - 分页和排序稳定性。
- [ ] 审计通过后再决定新增 `fund_catalog` MCP 工具，或复用后续 `fund_screen` 候选池。
- [ ] 如新增工具，必须同步 Schema、Adapter、Server、工具数量、缓存 TTL、文档和测试。
- [ ] 禁止前端循环调用数百个单标工具拼接“全量基金库”。

## 8. 阶段 M3：股票详情与研究动态

### 8.1 股票详情

- [ ] 新增 `GET /api/dashboard/stocks/{stock}`。
- [ ] 复用 `stock_valuation`，完整返回 PE、PB 和前复权价格独立历史序列。
- [ ] 个股详情将前复权价格、PE TTM、PB 渲染为三个独立历史视图。
- [ ] PE/PB 图沿用指数详情的参考线、窗口、tooltip、缩放和审计信息规则。
- [ ] 不使用双轴把价格与估值合成为未经定义的综合信号。
- [ ] 不从价格变化推断盈利、资金或行业因果。
- [ ] 股票不存在、市场不支持和上游失败使用不同页面状态。
- [ ] 在 `stock_screen` 未实现前，不展示虚假的股票候选列表。

### 8.2 研究动态

- [ ] 新增 `GET /api/dashboard/research?entity=&category=`。
- [ ] 查询必须绑定明确标的或版本化关注主题，不做无边界资讯抓取。
- [ ] 研究/媒体与博主/社区结果分组展示。
- [ ] 只展示：
  - 标题；
  - URL；
  - 域名；
  - 来源分类；
  - 可用的发布时间；
  - 查询时间。
- [ ] 来源分类不表示作者身份或内容真实性已经认证。
- [ ] Web MCP 失败只影响研究动态，不影响市场数据页面。
- [ ] Web 摘要中的数字不得进入 Dashboard 市场事实或排序字段。
- [ ] 不引入文章数据库、全文索引、RAG 或向量库。

## 9. 阶段 M4：总览与 Web 应用骨架

### 9.1 前端重构

- [ ] 将当前单文件 `App.tsx` 拆分为路由、布局、页面和共享组件。
- [ ] 引入明确的前端路由：
  - `/`
  - `/funds`
  - `/funds/:code`
  - `/indices`
  - `/indices/:code`
  - `/stocks/:code`
  - `/research`
  - `/chat`
- [ ] 保留当前聊天页作为 `/chat`，不删除已实现能力。
- [ ] 使用安静、紧凑、可扫描的数据工具布局，不使用营销式 Hero 或卡片套卡片。
- [ ] 桌面端使用固定主导航；移动端提供可用的导航和 Agent 入口。
- [ ] 页面按钮使用现有图标库或引入统一的 Lucide 图标，不手画重复 SVG。

### 9.2 总览 API 与页面

- [ ] 新增 `GET /api/dashboard/overview`。
- [ ] 总览只聚合已完成模块，不为未实现模块伪造数据。
- [ ] 第一版包含：
  - 数据源/工具健康与最近查询状态；
  - 指数关注池估值摘要；
  - 基金关注池状态；
  - 最近一次研究动态查询；
  - 候选筛选能力状态。
- [ ] `fund_screen`、`stock_screen` 未实现时返回 `not_implemented`，不返回空候选。
- [ ] 每个总览区块可以独立刷新和独立失败。
- [ ] 页面轮询频率按数据集配置，不统一高频刷新所有数据。
- [ ] 页面隐藏或离开时停止轮询，避免浪费上游配额。
- [ ] 提供手动刷新，并显示“正在刷新”“最近成功时间”“本次失败”。

## 10. 阶段 M5：页面上下文 Agent

### 10.1 契约

- [ ] 新增 `PageContext` Pydantic Schema：

```text
page_type
selected_entities
active_filters
sort
visible_fact_refs
```

- [ ] `page_type` 使用枚举。
- [ ] `selected_entities` 最多五个规范实体。
- [ ] `active_filters` 使用页面白名单字段，不接受任意嵌套 JSON。
- [ ] `visible_fact_refs` 只传事实 ID，不传未经校验的页面文本或数字。
- [ ] `ChatRequest` 可选携带 `page_context`。
- [ ] PageContext 不写入长期记忆，不跨会话持久化。

### 10.2 Agent 行为

- [ ] 页面上下文只用于指代消解和缩小研究范围。
- [ ] Agent 必须通过注册工具重新确认回答所需的市场事实。
- [ ] 页面筛选条件不能创建新工具、阈值或候选。
- [ ] 模型不能直接修改 PageContext、工具计划或图状态。
- [ ] 列表行提供“分析”动作。
- [ ] 多选两到五只基金后提供“比较”动作。
- [ ] 指数详情页提供与当前 PE/PB 事实关联的建议问题。
- [ ] 桌面端使用右侧 Agent 抽屉；移动端使用底部入口。
- [ ] 保留独立 `/chat` 页面供开放式研究。

## 11. 阶段 M6：候选筛选接入

本阶段依赖 [可审计基金与股票候选筛选](TASK_asset_screening.md) 的生产实现。

- [ ] `fund_screen` 完成前，基金候选模块保持 `not_implemented`。
- [ ] `stock_screen` 完成前，股票候选模块保持 `not_implemented`。
- [ ] 接入后只展示工具返回的候选，前端和模型不得增删候选。
- [ ] 每个候选展示：
  - `passed_rules`
  - `failed_rules`
  - `unknown_rules`
  - `metric_basis`
  - `as_of`
  - `audit_ref`
- [ ] 未知规则不得按失败或零值处理。
- [ ] 不生成综合 AI 分数、“优秀资产分”或确定性买卖标签。
- [ ] 候选行可进入单标详情和页面上下文 Agent。

## 12. 数据刷新与缓存策略

### 12.1 第一阶段

- [ ] Dashboard API 按请求读取 MCP。
- [ ] 复用 Fund/Web MCP 的工具级 TTL 缓存。
- [ ] Dashboard 层只允许短生命周期请求去重，不复制市场数据计算。
- [ ] 前端刷新周期按数据集时效配置：
  - 盘中状态可以较短；
  - 日频/T+1 数据不高频轮询；
  - Web 研究动态受搜索配额限制。
- [ ] 页面明确展示实际 `as_of`，不用“实时”替代具体时效。

### 12.2 PostgreSQL 引入门槛

仅当以下任一情况有测量证据时再立项：

- 全量目录和横截面筛选无法在可接受时间内按请求生成；
- 需要展示多期历史快照；
- 上游调用成本或频率无法由 MCP TTL 缓存控制；
- 需要稳定的定时更新和最近成功快照。

引入后，数据库只能保存通过审计的快照，不成为绕过 MCP 的事实源。

### 12.3 Redis 引入门槛

仅当出现以下需求时再立项：

- Agent API、Dashboard API 或 MCP 多副本共享缓存；
- Update Worker 分布式锁和防重复执行；
- 跨实例限流或热点缓存。

当前单副本 Compose 不增加 Redis。Redis 不保存长期市场历史或跨会话记忆。

## 13. 测试与验收

### 13.1 后端契约

- [ ] Dashboard Schema 拒绝额外字段和非法排序/筛选项。
- [ ] 每个市场数值保留字段路径、日期和审计引用。
- [ ] 指数与个股详情响应保留 PE/PB `chart_series`，不得只返回当前值和分位。
- [ ] 可选工具失败产生 `partial`，必需工具失败保持原始错误语义。
- [ ] 无模型配置时所有 Dashboard 页面仍可使用。
- [ ] Go 网页后端只作为 MCP Client 取数，不复制 Skill 逻辑、不做金融计算。
- [ ] Go 侧原样透传 `ToolEnvelope` 的 `data`、`data_audit`、`frame_sha256`、warnings
  和错误码，不重算、不改精度、不丢字段。
- [ ] PageContext 不能注入工具名、原始数字或未注册阈值。

### 13.2 前端

- [ ] 桌面与移动视口下，导航、表格、图表、抽屉和输入框无重叠。
- [ ] 长基金名称、错误信息和日期不会撑破容器。
- [ ] 加载、空态、部分结果、过期、上游失败和未实现状态均有独立展示。
- [ ] 表格排序只作用于同口径、可用数据。
- [ ] 桌面和移动视口均能查看 PE/PB 历史曲线、tooltip 和窗口切换。
- [ ] 页面切换不丢失当前临时 Agent 会话。
- [ ] 浏览器控制台无错误，API 请求无重复提交。
- [ ] 工作台新增能力不在 CLI 中重复实现。

### 13.3 Docker 黑盒

项目始终通过 Docker 运行，验收不依赖宿主机 Python/Node 环境：

- [ ] `docker compose ... --profile test run --build --rm test` 通过。
- [ ] Go 网页后端、Agent API、Fund MCP、Web MCP 各服务 healthy。
- [ ] Fund/Web MCP 工具发现数量与注册工具一致。
- [ ] React 生产构建由 Docker Node 阶段完成，并由 Go 后端托管。
- [ ] Go 后端到 Python MCP 的取数、以及到 Agent API 的 SSE 代理均连通。
- [ ] 浏览器完成指数看板、基金搜索、详情和 Agent 闭环。
- [ ] 上游失败、过期数据和未实现候选能力均通过人工黑盒验证。
- [ ] `config/config.local.yaml` 继续只读挂载给 Python 服务，不进入镜像。

## 14. 里程碑完成定义

### M1：首个数据页面

- 指数估值看板可用；
- 数据日期、部分失败和审计引用完整；
- 不调用模型即可渲染。

### M2：标的研究闭环

- 基金搜索和基金/股票/指数详情可用；
- 用户可从详情页打开 Agent；
- Agent 重新调用工具确认事实。

### M3：工作台 MVP

- 总览、主导航和研究动态可用；
- `/chat` 继续可用；
- 桌面、移动和 Docker 黑盒验证通过。

### M4：候选发现

- `fund_screen`、`stock_screen` 生产接入完成；
- 候选规则、未知状态和审计引用完整；
- 不存在综合 AI 分数。

## 15. 建议实施批次

1. **批次 1**：M0 + M1，建立契约并交付指数估值看板。
2. **批次 2**：M2，交付基金搜索、关注池和三类单标详情。
3. **批次 3**：M3 + M4，交付研究动态、总览和 Web 应用骨架。
4. **批次 4**：M5，接入页面上下文 Agent。
5. **批次 5**：执行 `TASK_asset_screening.md` 并接入候选模块。
6. **批次 6**：根据性能数据决定是否立项 PostgreSQL/Redis，不预先实施。
