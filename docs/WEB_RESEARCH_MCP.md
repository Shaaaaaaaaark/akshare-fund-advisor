# Web Research MCP

## 1. 目标

`web-research-mcp` 为 Agent 和 Agentic RAG 提供统一的公网搜索与网页读取能力。
它与 `fund-advisor-mcp` 独立部署：

```text
fund-advisor-mcp
  -> AKShare 市场事实

web-research-mcp
  -> 公开网页的定性背景
```

网页结果不能覆盖 AKShare 返回的净值、价格、PE、PB、收益率、回撤和交易状态。

搜索走**多供应商兜底链**：按配置顺序依次尝试 `serper → tavily → google_cse →
brave → serpapi`，前一个供应商认证失败、限流、超额或上游报错时自动降级到下一个，
任一供应商 HTTP 正常即返回其结果。只有填了凭证的供应商才会被真正调用，其余自动
跳过。无论命中哪个供应商，网页内容始终是非数值背景。

## 2. MCP 工具

### `web_search`

参数：

```json
{
  "query": "近期基金监管政策",
  "max_results": 5,
  "freshness_days": 7
}
```

返回：

- 标题
- URL
- 搜索摘要
- 排名
- 可用时的发布时间和语言
- 搜索响应 SHA-256

`freshness_days` 会映射为各供应商的时间窗口（Brave 用 `pd/pw/pm/py`，
谷歌系用 `qdr:d/w/m/y`）。审计记录里的 `provider` 和 `attempts` 会写明最终命中的
供应商以及降级过程。

### `web_fetch`

参数：

```json
{
  "url": "https://example.com/article",
  "max_chars": 12000
}
```

返回：

- 请求 URL 和最终 URL
- 页面标题
- 清洗后的 HTML/纯文本/Markdown 正文
- 是否截断
- 正文 SHA-256

抓取前后都会执行 URL 和 DNS 校验，禁止本机、私网、保留地址、带用户凭证的 URL
以及未授权域名。

## 3. 数据策略

每个工具响应固定包含：

```json
{
  "data_policy": {
    "purpose": "background_only",
    "numeric_allowed": false,
    "ai_may_generate_market_data": false,
    "may_override_market_tools": false
  }
}
```

Web 命中进入 Evidence 后：

- `channel=web`
- `confidence=low`
- `numeric_allowed=false`
- 检测 Prompt injection
- 只生成来源引用和定性背景提示
- 不生成金融数值 Fact

## 4. 你需要提供的信息

### 必需

1. **至少一个搜索供应商的 API Key**

   兜底链支持以下供应商，任填一个即可用，填多个可自动降级：

   | 供应商 | 结果来源 | 免费额度（以官网为准） | 需提供 |
   | --- | --- | --- | --- |
   | `serper` | 谷歌 | 注册送约 2,500 次 | `api_key` |
   | `tavily` | Agent 原生 | 约 1,000 次/月 | `api_key` |
   | `google_cse` | 谷歌官方 | 约 100 次/天 | `api_key` + `cx` |
   | `brave` | 独立索引 | 约 2,000 次/月 | `api_key` |
   | `serpapi` | 谷歌 | 约 100 次/月 | `api_key` |

   密钥不要在聊天、代码或 Git 中发送，只写入 `config.local.yaml` 或环境变量。

2. **是否允许容器访问公网**

   Docker 网络至少需要访问：

   ```text
   所选供应商的 API 域名（如 google.serper.dev / api.tavily.com 等）
   搜索结果对应的公网 https/http 页面
   DNS 解析服务
   ```

   谷歌系与 Brave 在中国大陆通常需要代理，`tavily` / `serper` 亦然。

### 可选

- 自定义 `search_chain` 顺序（默认 `serper → tavily → google_cse → brave → serpapi`）。
- 允许抓取的域名列表；空列表表示任意公网域名。
- 默认搜索语言，当前为 `zh-hans`。
- 单次最大结果数，当前为 `10`。
- 网页最大正文字符数，当前为 `12000`。
- 网页最大下载字节数，当前为 `2 MiB`。
- 是否需要公司代理，以及代理地址和认证方式。
- 若要接入表中之外的供应商，需提供其 API 文档、Endpoint、认证方式、请求/响应
  示例、限流和计费规则。

## 5. 配置

在被 Git 忽略的 `config/config.local.yaml` 中填入你有的供应商 Key（填几个都行）：

```yaml
web_research:
  # 可选：自定义顺序；留空用内置默认
  search_chain: [serper, tavily, google_cse, brave, serpapi]
  providers:
    serper:
      api_key: "YOUR_SERPER_API_KEY"
    tavily:
      api_key: "YOUR_TAVILY_API_KEY"
    google_cse:
      api_key: "YOUR_GOOGLE_API_KEY"
      cx: "YOUR_SEARCH_ENGINE_ID"
    brave:
      api_key: "YOUR_BRAVE_API_KEY"
    serpapi:
      api_key: "YOUR_SERPAPI_API_KEY"

rag:
  enabled: true
  web_enabled: true
```

也可以只通过环境变量注入单个密钥（嵌套用 `__` 分隔）：

```bash
export FINAGENT__WEB_RESEARCH__PROVIDERS__SERPER__API_KEY='YOUR_SERPER_API_KEY'
```

Compose 已配置：

```text
web-research-mcp:8002
agent-api -> http://web-research-mcp:8002/mcp
```

宿主机不会暴露 `8002`。

## 6. Agent 与 RAG 的使用方式

Agent 显式问题：

```text
网页搜索一下最近的基金监管政策
搜索股票 600519 的近期新闻
查一下某项政策的背景和影响
```

会路由为：

```text
intent=web_research
  -> 不调用金融工具
  -> PLAN_RETRIEVAL
  -> web_search
  -> web_fetch
  -> ASSESS_SUFFICIENCY
  -> WEB Evidence
```

基金研究问题如果同时包含新闻、政策或事件背景，Agentic RAG 可以在知识检索之外选择
Web 通道，但市场数值仍只来自 `fund-advisor-mcp`。

## 7. 启动与验证

配置 API Key 后重建：

```bash
docker compose -f deploy/compose/compose.yaml up -d --build
```

检查服务：

```bash
docker compose -f deploy/compose/compose.yaml ps
curl -fsS http://127.0.0.1:8000/health/ready
```

API readiness 应包含：

```json
{
  "checks": {
    "database": true,
    "mcp": true,
    "web_mcp": true
  }
}
```

`web_mcp=true` 表示协议和工具发现正常，不代表任一供应商 API Key 一定有效。必须再
执行一次真实 `web_search` 冒烟测试确认供应商认证。

## 8. 错误语义

| 错误码 | 含义 |
| --- | --- |
| `WEB_RESEARCH_DISABLED` | 工具未启用 |
| `WEB_SEARCH_NOT_CONFIGURED` | 兜底链中没有任何凭证齐全的供应商 |
| `WEB_SEARCH_AUTH_FAILED` | 某供应商 API Key 无效或权限不足 |
| `WEB_SEARCH_RATE_LIMITED` | 某供应商限流或免费额度用尽 |
| `WEB_SEARCH_UPSTREAM_ERROR` | 某供应商服务临时失败 |
| `WEB_SEARCH_INVALID_RESPONSE` | 某供应商返回无效响应 |
| `WEB_SEARCH_ALL_PROVIDERS_FAILED` | 兜底链中所有已配置供应商均失败 |
| `WEB_FETCH_INVALID_URL` | URL 非公网 HTTP/HTTPS 或包含凭证 |
| `WEB_FETCH_PRIVATE_ADDRESS` | 指向本机、私网或保留地址 |
| `WEB_FETCH_DOMAIN_BLOCKED` | 不在域名 allowlist |
| `WEB_FETCH_INVALID_REDIRECT` | 重定向响应缺少目标地址 |
| `WEB_FETCH_TOO_MANY_REDIRECTS` | 重定向次数超过限制 |
| `WEB_FETCH_TOO_LARGE` | 页面超过下载限制 |
| `WEB_FETCH_UNSUPPORTED_CONTENT` | 不是 HTML/纯文本/Markdown |
