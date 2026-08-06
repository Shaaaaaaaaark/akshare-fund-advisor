# 错误处理与降级

## 1. 原则

- 不存在、歧义、不支持、过期和上游失败必须区分。
- 上游失败只表示“当前无法确认”，不表示实体不存在或数值为零。
- 可选数据失败可以保留主要结果，但必须写入 warning。
- Agent 不得吞掉、改写或用模型补齐工具错误。

## 2. 错误传播

```text
AKShare / Web 上游异常
  -> Skill AdvisorError / WebResearchError
  -> MCP ToolError
  -> LangGraph Agent 状态与固定用户表达
```

MCP 信封失败时：

```text
ok=false
data=null
error.code
error.message
error.retryable
error.details
```

已经产生的 `sources`、`data_audit` 和 `data_warnings` 应尽可能保留，便于排查。

## 3. 实体语义

| 状态 | 含义 | 用户表达 |
| --- | --- | --- |
| `NOT_FOUND` | 目录成功但无匹配 | 未找到该标的 |
| `AMBIGUOUS` | 多个候选 | 展示候选并追问 |
| `UNSUPPORTED` | 实体可能存在，但当前接口不支持 | 当前数据能力不支持 |
| `UPSTREAM_ERROR` | 数据源失败 | 当前无法确认 |
| `STALE_DATA` | 数据存在但过期 | 数据过期，不用于当前结论 |

## 4. Fund Advisor 错误码

### 4.1 参数与实体

| 错误码 | 含义 | 是否重试 |
| --- | --- | --- |
| `INVALID_ARGUMENT` | 参数为空或超出范围 | 否 |
| `FUND_NOT_FOUND` | 基金目录成功但无匹配 | 否 |
| `AMBIGUOUS_FUND` | 基金名称对应多个候选 | 用户确认后重试 |
| `FUND_RATING_NOT_FOUND` | 评级接口成功但未收录该基金 | 否 |
| `STOCK_NOT_FOUND` | A 股目录成功但无匹配 | 否 |
| `ENTITY_AMBIGUOUS` | 股票或通用实体有多个候选 | 用户确认后重试 |
| `INDEX_NOT_SUPPORTED` | 当前没有可靠指数映射 | 否 |
| `STOCK_MARKET_UNSUPPORTED` | 当前不支持对应市场 | 否 |
| `STATUS_NOT_FOUND` | 状态接口未收录已解析基金 | 否，表达为当前无法确认 |
| `UNSUPPORTED_EXCHANGE_FUND` | 无法确认 ETF/LOF 类型 | 否 |

### 4.2 数据源和契约

| 错误码 | 含义 | 是否重试 |
| --- | --- | --- |
| `DATA_SOURCE_ERROR` | AKShare 上游或网络失败 | 是 |
| `RATE_LIMITED` | 上游明确限流 | 是 |
| `DATA_CONTRACT_ERROR` | 返回类型、重复列或字段不符合契约 | 否 |
| `DUPLICATE_DATE_CONFLICT` | 同一日期存在冲突数值 | 否 |
| `DATA_EMPTY` | 必需接口返回空数据 | 否 |
| `INSUFFICIENT_HISTORY` | 样本不足，不能计算目标指标 | 否 |
| `STALE_OR_INVALID_DATA` | 日期异常或数据过期 | 否 |
| `AKSHARE_INDEX_UNAVAILABLE` | AKShare 没有可用的同口径指数回退接口 | 否 |
| `VALUATION_SOURCE_UNAVAILABLE` | PE/PB 均不可用 | 是 |
| `VALUATION_DATA_EMPTY` | PE/PB 没有可用且时效合格的数据 | 否 |
| `STOCK_DATA_EMPTY` | 个股估值和价格均不可用 | 否 |
| `FUND_CODE_MISMATCH` | 产品详情代码与请求基金不一致 | 否 |
| `FUND_PROFILE_UNAVAILABLE` | 档案结果未通过代码一致性校验 | 否 |
| `AUDIT_CHECK_FAILED` | 真实接口审计缺少可验证结果 | 否 |
| `MISSING_DEPENDENCY` | Skill 运行依赖缺失 | 否，修复环境后重试 |
| `AKSHARE_VERSION_MISMATCH` | AKShare 版本未经当前 Skill 验证 | 否，修复环境后重试 |
| `UPSTREAM_TIMEOUT` | 工具调用超时 | 是 |
| `INTERNAL_ERROR` | 未分类程序错误 | 否，排查代码后重试 |

`data_warnings` 可以记录上述数据类错误而不让整个工具失败。例如 PE 可用、PB 过期时，
工具仍可成功，但 PB 的 `STALE_OR_INVALID_DATA` 必须保留。

## 5. Web Research 错误码

| 错误码 | 含义 | 是否重试 |
| --- | --- | --- |
| `WEB_RESEARCH_DISABLED` | Web MCP 未启用 | 配置后 |
| `WEB_SEARCH_NOT_CONFIGURED` | 无有效供应商凭证 | 配置后 |
| `WEB_SEARCH_AUTH_FAILED` | API Key 无效 | 更新凭证后 |
| `WEB_SEARCH_RATE_LIMITED` | 限流或额度耗尽 | 是 |
| `WEB_SEARCH_UPSTREAM_ERROR` | 供应商或网络失败 | 是 |
| `WEB_SEARCH_INVALID_RESPONSE` | 返回结构不合法 | 视具体异常 |
| `WEB_SEARCH_ALL_PROVIDERS_FAILED` | 所有已配置供应商失败 | 继承最后一次失败 |
| `WEB_FETCH_INVALID_URL` | URL 不符合要求 | 否 |
| `WEB_FETCH_PRIVATE_ADDRESS` | 指向私网或保留地址 | 否 |
| `WEB_FETCH_DOMAIN_BLOCKED` | 域名不在 allowlist | 配置后 |
| `WEB_FETCH_DNS_FAILED` | 域名解析失败 | 是 |
| `WEB_FETCH_INVALID_REDIRECT` | 重定向缺少目标 | 否 |
| `WEB_FETCH_TOO_MANY_REDIRECTS` | 重定向超过限制 | 否 |
| `WEB_FETCH_UPSTREAM_ERROR` | 目标站点返回 5xx | 是 |
| `WEB_FETCH_HTTP_ERROR` | 目标站点返回其他 HTTP 错误 | 否 |
| `WEB_FETCH_TOO_LARGE` | 响应超过大小限制 | 否 |
| `WEB_FETCH_UNSUPPORTED_CONTENT` | 内容类型不支持 | 否 |
| `DOCUMENT_EMPTY` | 文档没有可抽取正文 | 否 |
| `DOCUMENT_PARSE_FAILED` | PDF 无法解析 | 否 |
| `WEB_RESEARCH_INTERNAL_ERROR` | 未分类 Web Research 错误 | 否 |

## 6. 必需接口和可选接口

### 必需接口失败

- 工具 `ok=false`；
- 不生成对应分析结论；
- 保留错误和已产生的审计信息。

### 可选接口失败

- 主要工具结果可以 `ok=true`；
- 对应字段为 `null` 或 unavailable；
- `data_warnings` 记录失败接口、错误类型和影响；
- Agent 必须在限制部分说明缺失。

示例：

- 基金净值成功、持仓接口失败：可以分析历史收益和回撤，但不能说明持仓集中度。
- 个股 PE 成功、PB 失败：可以解释 PE，PB 明确缺失，禁止推断综合估值。
- ETF 历史价格成功、实时 IOPV 失败：可以分析历史风险，不能判断当前溢价。
- 单标市场工具成功、可选 Web 搜索失败：保留市场分析并返回 `partial_result`。

单标分析中的文章和博主搜索均为可选工具。若必需的 Fund MCP 调用失败，即使 Web 搜索
成功也必须保留 `NOT_FOUND`、`UNSUPPORTED`、`UPSTREAM_ERROR` 或 `STALE_DATA` 原始
语义，不能降级成只含网页链接的成功回答。

## 7. LangGraph Agent 映射

| 工具结果 | 图状态 | Agent 行为 |
| --- | --- | --- |
| 成功且审计通过 | `running` | 展示事实并允许关联说明 |
| 成功但有 warning | `partial_result` | 展示事实，同时披露限制 |
| `AMBIGUOUS` | `need_clarification` | 列出候选并结束本轮 |
| `NOT_FOUND` | `not_found` | 明确未找到 |
| `UNSUPPORTED` | `unsupported` | 说明当前能力不支持 |
| `UPSTREAM_ERROR` | `cannot_confirm` | 回答当前无法确认 |
| `STALE_DATA` | `stale_data` | 明确数据过期，不用于当前判断 |

状态由 `VALIDATE_TOOL_ENVELOPES` 节点产生，模型不能修改。关联说明不得弱化错误。例如
基金持仓接口失败后，不得根据基金名称猜测其行业或重仓股。

## 8. 重试

当前实现只负责标记 `error.retryable`，不包含通用自动重试器：

- Fund Adapter 把 `DATA_SOURCE_ERROR`、`VALUATION_SOURCE_UNAVAILABLE`、
  `RATE_LIMITED` 和 `UPSTREAM_TIMEOUT` 标为 `retryable=true`；
- Web 搜索会在一次调用内按供应商链降级，但不会对同一供应商无限重试；
- 失败信封不进入结果缓存。

当前 LangGraph Agent 不执行自动重试。后续如增加，必须使用代码定义的条件边，只处理
`retryable=true`，并设置次数上限、指数退避和随机抖动。参数、歧义、Schema 和安全错误
不自动重试，所有 MCP 调用保持幂等。

## 9. 测试要求

- 不存在实体返回 `NOT_FOUND`；
- 歧义实体返回候选；
- 上游异常不得映射成 `NOT_FOUND`；
- 必需接口失败时工具失败；
- 可选接口失败时保留主要结果和 warning；
- PE/PB 单侧失败不互相替代；
- Web SSRF、安全和内容限制错误稳定；
- LangGraph 条件边保持各类错误语义；
- Agent 关联说明不引用失败或过期字段。
