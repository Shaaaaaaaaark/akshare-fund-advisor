# TASK：投研数据工作台

> 状态：`进行中`
>
> 已完成：M0 Go BFF、指数列表 API、指数详情 API。
>
> 当前批次：M1 指数看板前端和 PE/PB 历史双图。
>
> 产品范围：[PRODUCT.md](../PRODUCT.md)
>
> 架构边界：[HLD.md](../HLD.md)

## 1. 目标

把当前纯聊天页升级为“数据优先、Agent 增强”的网页工作台：

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
- `GET /api/dashboard/indices` 返回配置关注池的指数摘要。
- `GET /api/dashboard/indices/{index}` 原样返回指数 `ToolEnvelope`。
- Go 使用有界并发，保留 `data_audit`、`frame_sha256`、warnings 和错误码。
- Agent SSE 经 Go 逐帧透传。
- React 对话页可使用，但仍是单文件 `App.tsx`，没有路由和数据页面。

### 当前缺口

- 没有 `/indices` 和指数详情页面；
- 没有 PE/PB 历史图表组件；
- 没有基金、股票、研究动态和总览 Dashboard API；
- 没有页面上下文 Agent 契约；
- `fund_screen`、`stock_screen` 尚未实现。

## 4. 交付状态板

| 批次 | 交付 | 状态 | 前置 |
| --- | --- | --- | --- |
| M0 | Go BFF、透传契约、指数 API、SSE 代理 | 已完成 | 无 |
| M1 | Web 应用骨架、指数列表、指数详情、PE/PB 双图 | **当前** | M0 |
| M2 | 基金搜索、关注池、基金详情 | 待实施 | M1 |
| M3 | 股票详情、研究动态 | 待实施 | M1 |
| M4 | 总览和统一状态展示 | 待实施 | M2/M3 |
| M5 | 页面上下文 Agent | 待实施 | M1-M4 |
| M6 | 候选筛选接入 | 阻塞 | `fund_screen` / `stock_screen` |

同一时间只推进一个当前批次。批次完成后更新本表和 README，不创建新的历史 TASK。

## 5. 当前批次 M1：指数看板

### 5.1 代码范围

主要修改：

```text
web/package.json
web/src/main.tsx
web/src/App.tsx
web/src/api.ts
web/src/types.ts
web/src/styles.css
web/src/routes/
web/src/layout/
web/src/pages/
web/src/components/
```

Go API 已完成，除非发现契约缺陷，不扩展 `web-backend/` 的金融字段处理。

### 5.2 应用骨架

- [ ] 引入 `react-router-dom`、ECharts React 绑定和 `lucide-react`。
- [ ] 将 561 行 `App.tsx` 拆为路由、布局、页面和共享组件。
- [ ] 保留现有聊天能力并迁移到 `/chat`。
- [ ] 增加 `/indices` 和 `/indices/:index` 路由。
- [ ] 根路径暂重定向到 `/indices`，总览完成后再切换到 `/`。
- [ ] 桌面端提供固定主导航，移动端提供不遮挡内容的导航。
- [ ] 不使用营销式 Hero、装饰性渐变或卡片套卡片。

### 5.3 API 与类型

- [ ] 在 `types.ts` 定义 `DatasetMeta`、指数摘要和指数详情类型。
- [ ] 在 `api.ts` 增加指数列表和详情请求。
- [ ] 不在前端复制 `ToolEnvelope` 金融计算。
- [ ] 未知字段保持兼容；缺失数值使用 `null`，不转成 `0`。
- [ ] 请求失败、工具失败和单侧指标缺失使用不同状态。

### 5.4 指数列表页

- [ ] 展示名称、PE TTM 当前值/分位、PB 当前值/分位、最新点位和 `as_of`。
- [ ] PE 与 PB 独立展示，不合成总分。
- [ ] 支持名称搜索、状态筛选、PE/PB 分位排序。
- [ ] 过期、失败和缺失项不进入正常数值排序。
- [ ] 每行可进入详情，并提供明确的状态和错误信息。
- [ ] 加载、空态、部分失败和不可用状态使用稳定布局。
- [ ] 移动端可横向滚动或使用紧凑列表，不截断代码和名称。

### 5.5 指数详情页

- [ ] 默认请求十年数据，只提供响应实际存在的 3/5/10/20 年窗口。
- [ ] PE TTM、PB 使用上下两张独立历史图，共享时间范围和缩放状态。
- [ ] 只连接 `chart_series` 的真实点，不插值、不前向填充、不补点。
- [ ] 展示当前值、分位、均值、中位数、极值、P20/P80 和均值 ±1 标准差。
- [ ] 展示 `source_observations`、`displayed_points`、实际起止日期和最新日期。
- [ ] 展示来源、warning、审计哈希和“历史分位不预测未来”。
- [ ] PE 或 PB 单侧缺失时只展示可用侧，并说明另一侧不可用。
- [ ] 可用时单独展示指数点位历史，不与 PE/PB 合成双轴信号。
- [ ] tooltip、十字准星、缩放和当前点标记在桌面与移动端可用。

### 5.6 M1 验收

- [ ] 页面无需 Ark 模型即可完整显示。
- [ ] 页面数值可逐项反查 API 字段和 `frame_sha256`。
- [ ] 图表点数等于 `displayed_points`，统计样本显示为 `source_observations`。
- [ ] 单个指数失败不影响其他指数。
- [ ] 创业板 50 等单侧缺失场景不显示零值或空图占位。
- [ ] `/chat` 原有提交、SSE 进度和最终结果不回归。
- [ ] TypeScript 构建通过，浏览器控制台无错误。
- [ ] 桌面和移动截图无文本溢出、控件重叠或布局跳动。

## 6. 后续批次

### M2：基金搜索和详情

后端：

- `GET /api/dashboard/funds/search?query=&limit=`
- `GET /api/dashboard/funds/{fund}`
- 有界并发聚合 `fund_analyze/profile/rating/status`
- 关注池只来自配置，不持久化用户操作

Web：

- `/funds` 和 `/funds/:code`
- 歧义份额必须由用户选择
- 产品、费用、历史表现、风险、交易状态、评级和限制分区展示
- ETF 溢价与净值历史位置分开，主动基金不显示“高估/低估”

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

### M5：页面上下文 Agent

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

- [ ] 修改范围与本任务一致，无无关重构。
- [ ] 新增状态有加载、空、失败、过期和部分结果处理。
- [ ] 文档只更新 README、HLD 状态表和本任务，不复制实现细节。

### 自动验证

```bash
docker compose -f deploy/compose/compose.yaml --profile test build test
docker compose -f deploy/compose/compose.yaml run --rm test

docker run --rm -v "$PWD/web-backend":/src -w /src golang:1.22-alpine \
  sh -c "gofmt -l . && go vet ./... && go test ./..."

docker compose -f deploy/compose/compose.yaml up --build -d
```

### 黑盒验证

- [ ] 四个服务 healthy。
- [ ] Fund/Web MCP 工具发现数量正确。
- [ ] Go 到 MCP 的 Dashboard 取数可用。
- [ ] Go 到 Agent API 的 SSE 顺序不变。
- [ ] 浏览器完成当前批次主流程。
- [ ] 桌面与移动视口无重叠，浏览器控制台无错误。
- [ ] `config/config.local.yaml` 未进入镜像或 Git。
