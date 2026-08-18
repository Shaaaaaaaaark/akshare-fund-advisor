# TASK：投研数据工作台

> 状态：`进行中`
>
> 已完成：M0 Go BFF；M1 指数工作台；M2 ETF 搜索与高密度五联图终端。
>
> 当前批次：M2 主动基金产品档案与非 ETF 详情。ETF 终端和 ETF 研究 Agent 抽屉已完成。
>
> 产品范围：[PRODUCT.md](../PRODUCT.md)
>
> 架构边界：[HLD.md](../HLD.md)

## 1. 目标

把原纯聊天页升级为“数据优先、Agent 增强”的网页工作台：

- 用户不提问也能浏览可信结构化数据；
- 页面显示实际日期、状态、warning 和审计引用；
- Agent 可从页面上下文继续研究，但必须重新调用工具确认事实；
- 金融数值直接渲染工具结果，不经过模型提取或前端计算。

## 2. 非目标

- 不开发新的产品 CLI；
- 不实现组合分析、回测、收益预测和自动交易；
- 不引入数据库、Redis、消息队列、RAG 或长期记忆；
- 不把未实现的全市场目录或候选筛选伪装成可用；
- 不在 Go 或 React 中重算、四舍五入、插值或补齐金融数据。

## 3. 当前基线

### 已实现

- Go 是对外唯一 HTTP 入口，Python 服务只在容器网络内可达。
- Dashboard 通过独立 Data API REST 取数，不依赖 Agent、LangGraph 或 MCP 协议。
- `GET /api/dashboard/indices` 返回配置关注池的指数摘要。
- `GET /api/dashboard/indices/{index}` 原样返回指数 `ToolEnvelope`。
- Go 使用有界并发，保留 `data_audit`、`frame_sha256`、warnings 和错误码。
- Agent SSE 经 Go 逐帧透传。
- React 使用“数据面板 / Agent”两个一级入口；数据面板内部提供 `/`、`/indices`、
  `/funds` 和 `/stocks`。
- `/` 只提供已接入数据模块入口；Agent 独立使用 `/chat`。
- `/indices` 和指数详情已接入真实 Dashboard API；所有列表数据列支持升降序。
- `/funds` 支持 ETF 搜索、真实日线五联图、日期窗口和最近交易日全字段排序。
- ETF 详情支持桌面三栏、移动端主图/趋势切换和右侧研究 Agent 抽屉；抽屉只预填当前
  ETF 问题，市场事实仍由 Agent API 重新调用工具确认。
- `/stocks` 当前只展示接入边界和 Agent 入口，不展示虚构数据。

### 当前缺口

- 没有主动基金产品档案页、股票、研究动态和完整总览 Dashboard API；
- 没有可持久化关注池；
- `/` 当前是分类入口，不等同于 M4 的跨模块总览；
- 没有通用 `PageContext` 契约；ETF 抽屉的代码预填不等同于该契约；
- `fund_screen`、`stock_screen` 尚未实现。

## 4. 交付状态板

| 批次 | 交付 | 状态 | 前置 |
| --- | --- | --- | --- |
| M0 | Go BFF、独立 Data API、透传契约、指数 API、SSE 代理 | 已完成 | 无 |
| M1 | 顶部分类、总览入口、指数列表、指数详情、PE/PB 双图 | 已完成 | M0 |
| M2 | ETF 终端和 ETF Agent 抽屉已完成；主动基金产品档案和详情继续实施 | **当前** | M1 |
| M3 | 股票详情、研究动态 | 待实施 | M1 |
| M4 | 总览和统一状态展示 | 待实施 | M2/M3 |
| M5 | 页面上下文 Agent | 待实施 | M1-M4 |
| M6 | 候选筛选接入 | 阻塞 | `fund_screen` / `stock_screen` |

同一时间只推进一个当前批次。批次完成后更新本表和 README，不创建新的历史 TASK。

## 5. 已完成 M1：应用骨架与指数看板

### 5.1 代码范围

主要修改：

```text
web/package.json
web/src/main.tsx
web/src/App.tsx
web/src/api.ts
web/src/types.ts
web/src/styles.css
web/src/layout/
web/src/pages/
web/src/components/
```

Go API 已完成，除非发现契约缺陷，不扩展 `web-backend/` 的金融字段处理。

### 5.2 应用骨架

- [x] 引入 `react-router-dom`、ECharts 和 `lucide-react`。
- [x] 将 561 行 `App.tsx` 拆为路由、布局、页面和共享组件。
- [x] 保留现有聊天能力并迁移到 `/chat`。
- [x] 增加 `/indices` 和 `/indices/:index` 路由。
- [x] 根路径提供总览入口页，聚合已实现的指数状态但不伪装成完整总览 API。
- [x] 全站使用“数据面板 / Agent”两个一级入口；ETF 详情额外提供不改变主布局的右侧
  Agent 抽屉。
- [x] 数据详情页可提供 Agent 快捷入口，但数据渲染不依赖 Agent 服务。
- [x] 独立 Agent 页的临时会话使用页面内横向标签；ETF Agent 使用独立临时抽屉会话。
- [x] 不使用营销式 Hero、装饰性渐变或卡片套卡片。

### 5.3 API 与类型

- [x] 在 `types.ts` 定义 `DatasetMeta`、指数摘要和指数详情类型。
- [x] 在 `api.ts` 增加指数列表和详情请求。
- [x] 不在前端复制 `ToolEnvelope` 金融计算。
- [x] 未知字段保持兼容；缺失数值使用 `null`，不转成 `0`。
- [x] 请求失败、工具失败和单侧指标缺失使用不同状态。

### 5.4 指数列表页

- [x] 展示名称、PE TTM 当前值/分位、PB 当前值/分位、最新点位和 `as_of`。
- [x] PE 与 PB 独立展示，不合成总分。
- [x] 支持名称搜索和状态筛选。
- [x] 名称、点位、PE 当前值/分位、PB 当前值/分位、日期和状态均支持升降序。
- [x] 过期、失败和缺失数值在升降序中始终沉底。
- [x] 每行可进入详情，并提供明确的状态和错误信息。
- [x] 加载、空态、部分失败和不可用状态使用稳定布局。
- [x] 移动端可横向滚动或使用紧凑列表，不截断代码和名称。

### 5.5 指数详情页

- [x] 默认请求十年数据，只提供响应实际存在的 3/5/10/20 年窗口。
- [x] PE TTM、PB 使用上下两张独立历史图，共享时间范围和缩放状态。
- [x] 只连接 `chart_series` 的真实点，不插值、不前向填充、不补点。
- [x] 展示当前值、分位、均值、中位数、极值、P20/P80 和均值 ±1 标准差。
- [x] 展示 `source_observations`、`displayed_points`、实际起止日期和最新日期。
- [x] 展示来源、warning、审计哈希和“历史分位不预测未来”。
- [x] PE 或 PB 单侧缺失时只展示可用侧，并说明另一侧不可用。
- [x] 可用时单独展示指数点位历史，不与 PE/PB 合成双轴信号。
- [x] tooltip、十字准星、缩放和当前点标记在桌面与移动端可用。

### 5.6 M1 验收

- [x] 页面无需 Ark 模型即可完整显示。
- [x] 页面数值可逐项反查 API 字段和 `frame_sha256`。
- [x] 图表点数等于 `displayed_points`，统计样本显示为 `source_observations`。
- [x] 单个指数失败不影响其他指数。
- [x] 创业板 50 等单侧缺失场景不显示零值或空图占位。
- [x] `/chat` 原有提交、SSE 进度和最终结果不回归。
- [x] TypeScript 构建通过，浏览器无应用脚本错误。
- [x] 桌面和移动布局无文本溢出、控件重叠或页面横向滚动。

## 6. 后续批次

### M2：基金搜索和详情

后端：

- [x] `GET /api/dashboard/funds/search?query=&limit=`
- [x] `GET /api/dashboard/funds/{fund}` 原样透传 `etf_dashboard`。
- [x] Skill 生成价格、成交额、成交量、涨跌幅和回撤五联真实序列。
- [x] 东财 ETF 历史失败时按既有契约回退新浪未复权行情并披露 warning。
- [ ] 有界聚合 `fund_analyze/profile/rating/status`。
- [ ] 关注池只来自配置，不持久化用户操作。

Web：

- [x] `/funds` 和 `/funds/:code`
- [x] 搜索结果由用户选择，不自动决定歧义份额。
- [x] 复刻高密度摘要、三档区间、日期窗口、五联图和趋势表信息结构。
- [x] 最近交易日每个数据列支持升降序。
- [x] 未可靠取得的份额变化、净申赎和融资余额明确省略，不生成替代数值。
- [x] ETF 详情展示 warning、来源与审计哈希。
- [x] ETF 详情提供右侧 Agent 抽屉，并在移动端使用全屏抽屉。
- [ ] 主动基金产品、费用、历史表现、风险、交易状态、评级和限制分区展示。
- [ ] ETF 溢价与净值历史位置分开，主动基金不显示“高估/低估”。

### M3：股票详情和研究动态

- `GET /api/dashboard/stocks/{stock}`
- 个股价格、PE TTM、PB 三个独立历史视图
- `GET /api/dashboard/research?entity=&category=`
- 研究/媒体与社区观点分组
- Web 数字不得进入市场事实或排序
- `stock_screen` 未实现前不展示股票候选列表

### M4：总览

- `GET /api/dashboard/overview`
- 只聚合已完成模块
- 每个区块独立状态、刷新和失败
- 未实现候选返回 `not_implemented`
- 页面隐藏时停止轮询；日频数据不高频刷新

### M5：通用页面上下文 Agent

新增受控 `PageContext`：

```text
page_type
selected_entities       # 最多五个
active_filters          # 页面白名单字段
sort
visible_fact_refs       # 只传事实 ID
```

页面上下文只用于指代消解和缩小范围。Agent 必须重新调用工具确认市场事实，模型不能修改
上下文、工具计划或图状态。

当前 ETF 抽屉只把规范代码写入建议问题和用户问题，不发送 `PageContext` 或页面市场数值，
因此不把它计为 M5 完成。

### M6：候选筛选

依赖 [TASK_asset_screening.md](TASK_asset_screening.md)。

- 工具未实现时保持 `not_implemented`；
- 只展示工具返回的候选和三态规则；
- 不生成综合 AI 分数或买卖标签。

## 7. 全局数据契约

所有批次必须遵守：

- 每个数据块有 `as_of`、`queried_at`、`status`、warnings 和审计引用；
- 保留 `NOT_FOUND`、`AMBIGUOUS`、`UNSUPPORTED`、`UPSTREAM_ERROR`、
  `STALE_DATA`；
- 上游失败不能转成空列表或“不存在”；
- Go 只读少量展示字段，其余 `ToolEnvelope` 原样透传；
- React 不计算收益、回撤、分位、溢价或参考线；
- 排序只作用于同口径、状态可用的数据。

## 8. Definition of Done

每个批次完成前必须满足：

### 代码

- [x] 当前已完成切片的修改范围与本任务一致。
- [x] 当前已完成页面包含加载、空、失败、过期和部分结果处理。
- [x] 当前实现状态已同步 README、HLD 和本任务。

### 自动验证

```bash
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test

docker run --rm -v "$PWD/web-backend":/src -w /src golang:1.22-alpine \
  sh -c "gofmt -l . && go vet ./... && go test ./..."

docker compose -f deploy/compose/compose.yaml up --build -d
```

### 最近一次黑盒基线（2026-08-18）

- [x] 五个服务 healthy。
- [x] Data API REST 健康且返回完整审计 Envelope。
- [x] Fund MCP 10 个、Web MCP 3 个工具发现正确。
- [x] Go 到 Data API 的指数与 ETF Dashboard 取数可用。
- [x] Go 到 Agent API 的 SSE 代理和独立 Agent 页可用。
- [x] 浏览器完成指数、ETF 和 Agent 主流程。
- [x] 1720px 三栏、909px 无横向溢出、390px 主图/趋势切换与 Agent 抽屉通过。
- [x] 新标签浏览器控制台无应用错误。
- [x] `config/config.local.yaml` 未进入镜像或 Git。

后续批次完成时仍须重新执行全部自动与黑盒验证，不得复用本基线代替新验收。
