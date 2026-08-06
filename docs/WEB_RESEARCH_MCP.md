# Web Research MCP

## 1. 目标

`web-research-mcp` 提供公网搜索、网页读取和用户指定文档读取。它只提供**非数值背景**，
不能确认基金/股票/指数是否存在，也不能覆盖 Fund Advisor MCP 的市场事实。

当前代码位于：

```text
src/fund_advisor_mcp/web/
```

顶层包、stdio/HTTP Client、FastMCP Server 和 `web-research-mcp` 命令入口均已接线。

## 2. 工具

### `web_search`

```json
{
  "query": "近期基金监管政策",
  "max_results": 5,
  "freshness_days": 7,
  "source_types": ["official", "research", "media"]
}
```

返回标题、URL、摘要、排名、可用的发布时间以及搜索审计哈希。

搜索结果还包含确定性来源分类：

```text
official | research | media | creator | other
```

分类只依据公开 URL 域名和标题关键词，用于区分官方、机构研究、财经媒体和博主/社区
入口，不代表平台账号身份或内容真实性已经核验。`source_types` 可按上述类别过滤结果；
不传时保留全部类别。

### `web_fetch`

```json
{
  "url": "https://example.com/article",
  "max_chars": 12000
}
```

读取并清洗 HTML、纯文本或 Markdown。

### `document_read`

```json
{
  "url": "https://example.com/document.pdf",
  "max_chars": 20000
}
```

在 `web_fetch` 基础上额外支持 PDF 文本抽取，适用于用户明确给出的基金合同、招募说明书、
公司公告或监管文档 URL。

## 3. 固定数据策略

每个工具信封固定包含：

```json
{
  "purpose": "background_only",
  "numeric_allowed": false,
  "ai_may_generate_market_data": false,
  "may_override_market_tools": false
}
```

因此：

- 文本中的价格、净值、PE、PB、收益率和日期不能升级为市场事实；
- Web 内容不能确认实体存在；
- Web 内容只能用于政策、事件、公告和条款背景；
- Agent 必须把外部文本视为不可信数据，而不是指令。

## 4. 搜索供应商

默认降级顺序：

```text
serper -> tavily -> google_cse -> brave -> serpapi
```

只调用配置完整且已启用的供应商。

| 供应商 | 必需配置 |
| --- | --- |
| Serper | `api_key` |
| Tavily | `api_key` |
| Google CSE | `api_key` + `cx` |
| Brave | `api_key` |
| SerpAPI | `api_key` |

认证、限流、5xx、无效响应或网络异常触发降级。正常返回空结果视为成功，不继续调用其他
供应商。

## 5. SSRF 和下载安全

每次请求必须：

1. 只允许不含用户凭证的公网 HTTP/HTTPS URL；
2. DNS 解析后拒绝本机、私网、链路本地、多播和保留地址；
3. 每次重定向重新执行 URL 和 DNS 校验；
4. 限制重定向次数；
5. 限制 `Content-Length` 和实际读取字节数；
6. 限制正文字符数；
7. 校验内容类型；
8. 可选启用域名 allowlist。

禁止只校验初始 URL 后自动跟随重定向。

## 6. LangGraph Agent 使用方式

```text
政策/新闻问题
  -> CLASSIFY
  -> PLAN_REGISTERED_TOOLS
  -> web_search
  -> VALIDATE_TOOL_ENVELOPES
  -> 非数值背景

明确文档 URL
  -> CLASSIFY
  -> document_read
  -> VALIDATE_TOOL_ENVELOPES
  -> 文档条款背景
```

当前固定图对政策/新闻问题只执行 `web_search`；`web_fetch` 已作为独立 MCP 工具提供，
但尚未加入搜索结果后的自动二次抓取链。

基金单标分析和股票单标估值在启用 Web Research 后，固定追加两次可选搜索：

```text
"标的" + 深度分析/研究报告/财经媒体
"标的" + 观点/分享 + site:xueqiu.com OR site:zhihu.com
```

两次搜索均为 `required=false`：

- 第一条只保留 `official/research/media`，第二条只保留 `creator`；
- Web 搜索失败时，保留通过审计的市场分析并返回 `partial_result`；
- Fund MCP 失败时，不能使用文章或博主观点替代市场事实；
- 输出直接展示标题、链接、域名和来源类别，不把摘要中的数字渲染为市场事实；
- 当前不自动抓取搜索结果全文，避免把外部页面中的提示文本带入模型上下文。

LangGraph Agent 可以把 Web 背景与市场工具事实并列说明，例如“监管规则发生变化，同时
基金状态工具显示当前可申购”，但 Web 结果必须保持 `numeric_allowed=false`，也不能宣称
前者导致后者，除非存在明确官方依据。

## 7. 配置示例

```yaml
web_research:
  enabled: true
  search_chain: [serper, tavily, google_cse, brave, serpapi]
  providers:
    serper:
      api_key: ""
    tavily:
      api_key: ""
    google_cse:
      api_key: ""
      cx: ""
    brave:
      api_key: ""
    serpapi:
      api_key: ""
  allowed_domains: []
  max_results: 10
  max_content_chars: 12000
  max_fetch_bytes: 2097152
```

真实密钥只放在被忽略的本地配置或环境变量中。

## 8. 测试

当前测试覆盖：

- 多供应商顺序与凭证过滤；
- 认证、限流和网络错误降级；
- 正常空结果；
- HTML 清洗；
- PDF 内容类型与抽取；
- 私网地址拦截；
- 重定向逐跳校验；
- 内容哈希与 `numeric_allowed=false`。

stdio 和 Compose 内 HTTP 工具发现均已验证为 `web_search`、`web_fetch`、
`document_read` 三个工具，Docker 服务健康检查通过。

详细错误码见 [ERROR_HANDLING.md](ERROR_HANDLING.md)。
