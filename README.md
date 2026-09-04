# AKShare Financial Research Agent

面向中国基金、ETF、指数和 A 股研究的可信投研数据工作台，也是用于展示受控 Agent
工程能力的项目。

项目不预测涨跌、不荐股、不执行交易。金融数值只能来自经过 Schema、时效和
`frame_sha256` 审计的 AKShare 数据；模型只解释已验证事实。

## 当前状态

产品 MVP 已可运行：首页为高密度 ETF 数据终端，总览、指数、主动基金、股票、自选和
Agent 页面均可进入，并提供 MySQL 持久化自选列表、匿名投票和反馈。网页后端为 Java 21
+ Spring Boot MVC、MyBatis、MySQL 和 Redis。研究动态、候选筛选和通用
`PageContext` 作为后续增强。

模块级实现状态、优先级和完成标准统一维护在 [Roadmap](docs/ROADMAP.md)。

## 架构

```text
React Web
  -> Java 网页后端（对外唯一 HTTP 入口）
     |-- 数据面板请求 -> Data API (Python) -> data_core -> providers(AKShare/...)
     |-- 自选列表、匿名投票和反馈 -> MySQL
     |-- 面板接入限流 -> Redis
     `-- Agent SSE 代理 -> Agent API (Python) -> LangGraph -> MCP / Agent Skill
```

职责边界：Python 承担全部金融计算与审计（`data_core`、Data API、Agent、MCP、Agent
Skill）；Java 网页后端负责取数聚合、自选列表、接入限流、静态托管和 Agent SSE 代理；
React 只渲染结构化结果。三者都不得生成、补齐或改写市场事实。

组件职责、协议契约、错误语义和安全边界见 [整体架构](docs/ARCHITECTURE.md)。

## 已实现能力

- 基金搜索、产品档案、评级、申赎状态、历史收益、波动和回撤。
- ETF/LOF 历史价格或净值、实时价格、IOPV 和统一方向的溢价率。
- ETF 价格、成交额、成交量、涨跌幅和回撤五联历史图，以及最近交易日排序表。
- 上交所 ETF 最近 7 日份额、沪深 ETF 最近 7 日融资余额及相邻交易日变化；精确匹配
  底层宽基指数时同步汇总最新成份股融资余额和覆盖率。
- ETF/A 股未复权收盘价支持 Baostock 独立交叉校验，ETF 单位净值另由东方财富与同花顺
  同日交叉校验；校验只追加审计和 warning，不覆盖 AKShare 主源。
- 指数 PE TTM、PB、历史分位和历史曲线数据。
- A 股 PE TTM、PB 和前复权价格历史曲线。
- 两到五只基金的同口径比较和不可比提示。
- 公开研究文章、财经媒体和社区链接的非数值背景搜索。
- 固定 LangGraph 研究流程、事实引用、关联说明和响应门禁。
- Dashboard 指数列表与详情 API：
  - `GET /api/dashboard/overview`
  - `GET /api/dashboard/overview/{index|etf|fund|stock}`
  - `GET /api/dashboard/indices`
  - `GET /api/dashboard/indices/{index}`
- Dashboard 基金搜索与 ETF 详情 API：
  - `GET /api/dashboard/funds/search?query=&limit=`
  - `GET /api/dashboard/funds/{fund}`
  - `GET /api/dashboard/funds/{fund}/product?years=1|3|5`
- Dashboard 股票单标 API：
  - `GET /api/dashboard/stocks/{stock}?years=1|3|5|10&max_points=`
- Dashboard QDII/海外限额榜 API：
  - `GET /api/dashboard/boards/qdii-purchase`
- Java 自选列表 API：
  - `GET /api/watchlist`
  - `POST /api/watchlist`
  - `DELETE /api/watchlist/{id}`
- Java 面板互动 API：
  - `GET /api/panel/interactions`
  - `POST /api/panel/interactions`

Web 默认进入 ETF 数据终端，并提供总览、自选和 Agent 等入口。ETF 终端包含分组选择、
列表、六项摘要、区间切换、五联历史图、价格/份额融合图、趋势表、指标说明、持久投票与
反馈、桌面可调分栏和移动端视图切换；指数详情
展示 PE/PB 历史双图，主动基金页展示产品、收益风险、费率、评级和申赎状态，股票页展示
前复权价格、PE TTM 和 PB 三个独立历史视图。自选页通过 Java、MyBatis 和 MySQL 保存
用户输入的标的元数据，进入详情后仍由 Data API 确认标的和市场事实。

## Docker 运行

项目以 Docker 为准运行：

```bash
docker compose -f deploy/compose/compose.yaml up --build -d
```

默认入口：

```text
http://127.0.0.1:8080
```

若端口被占用：

```bash
FUND_ADVISOR_PORT=8090 \
  docker compose -f deploy/compose/compose.yaml up --build -d
```

Compose 包含七个服务：

```text
web-backend       # Java Spring Boot，对外暴露
mysql             # Java 产品元数据，仅容器网络
redis             # Java 接入限流，仅容器网络
data-api          # Python，数据面板 REST，仅容器网络
agent-api         # Python，仅容器网络
fund-advisor-mcp  # Python，仅容器网络
web-research-mcp  # Python，仅容器网络
```

只有 `web-backend` 对外暴露，其余六个服务仅在容器网络内可见。

## 分离部署（前端 GitHub Pages + 后端服务器）

前端可静态托管到 GitHub Pages，后端整套 Compose 部署在自有服务器，`web-backend`
仍是唯一对外入口。默认同源部署不受影响：下列变量为空时行为与单机一致。

前端构建期变量（GitHub Actions Variables）：

```text
VITE_API_BASE    后端对外地址，必须 HTTPS，例如 https://api.your-domain.com
VITE_BASE_PATH   部署子路径，默认 /<repo>/；根站点设为 /
```

后端运行期变量：

```text
WEB_CORS_ALLOWED_ORIGINS   允许的前端来源，逗号分隔，例如 https://user.github.io
                           为空表示不启用 CORS（同源部署默认）
```

要点：

- 浏览器要求 HTTPS 页面只能调用 HTTPS 接口，后端需经 Caddy/Nginx 自动证书或
  Cloudflare Tunnel 提供 TLS；
- Pages 工作流将构建后的 `index.html` 复制为 `404.html`，支持直接刷新前端子路由；
- GitHub Actions 工作流见 `.github/workflows/deploy-web-pages.yml`，仅发布前端；
- 后端不使用 Cookie，CORS 固定 `allowCredentials=false`，只放行精确来源。

## 验证

Python 全量检查、Java BFF `mvnw verify`、Skill 单测和真实接口审计的完整命令统一维护在
[AGENTS.md](AGENTS.md#验证)。

## 文档

- [整体架构](docs/ARCHITECTURE.md)：组件边界、协议契约、错误语义、安全边界
- [Roadmap](docs/ROADMAP.md)：实现状态、优先级、完成标准
- [AGENTS.md](AGENTS.md)：开发约束、验证命令、提交前检查
- [Skill 调用规范](skills/akshare-fund-advisor/SKILL.md)：模型调用顺序与禁止事项
- [Skill 安装与命令](skills/akshare-fund-advisor/USAGE.md)：独立安装、命令示例、错误码
- [安全策略](SECURITY.md)：漏洞报告、密钥、Web 与 Agent 安全

## 免责声明

本项目仅用于金融信息分析和个人研究参考，不构成投资建议。历史统计和关联说明不代表
因果关系，也不代表未来表现。
