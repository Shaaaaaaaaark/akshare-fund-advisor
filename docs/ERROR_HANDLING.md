# 错误处理与降级契约

## 1. 目标

金融研究系统必须区分“没有这个标的”和“当前查不到这个标的”。错误语义错误会直接
造成错误金融事实，因此错误处理属于业务契约，不只是异常日志。

## 2. 分层错误模型

```text
Skill AdvisorError
  -> MCP ToolError
  -> ToolEnvelope(ok=false, data=null)
  -> AgentFailure / Clarification
  -> Evidence Gate
  -> TaskStatus
  -> API 与前端
```

错误情况下不得把其他标的数据、缓存示例、模型记忆或零值放入 `data`。

## 3. 实体状态

| 状态 | 含义 | 用户结果 | 是否重试 |
| --- | --- | --- | --- |
| `FOUND` | 目录成功且唯一匹配 | 继续查询 | 否 |
| `NOT_FOUND` | 目录成功但没有记录 | 明确未找到 | 否 |
| `AMBIGUOUS` | 多个同等候选 | 要求确认 | 等用户 |
| `UNSUPPORTED` | 实体可能存在，但当前能力不支持 | 说明边界 | 否 |
| `UNAVAILABLE` | 目录或上游请求失败 | 当前无法确认 | 可重试 |

关键规则：

```text
上游失败 != 实体不存在
无搜索结果 != 价格为零
无行情 != 停牌
接口失败 != 暂停申购或赎回
```

## 4. 当前错误码

### 4.1 参数与实体

| 错误码 | 场景 | 预期状态 |
| --- | --- | --- |
| `INVALID_ARGUMENT` | 空参数或参数范围错误 | `cannot_confirm` |
| `FUND_NOT_FOUND` | 基金目录成功但无匹配 | `cannot_confirm` |
| `STOCK_NOT_FOUND` | A 股目录成功但无匹配 | `cannot_confirm` |
| `AMBIGUOUS_FUND` | 基金名称对应多个候选 | `need_clarification` |
| `ENTITY_AMBIGUOUS` | 股票或通用实体多个候选 | `need_clarification` |
| `INDEX_NOT_SUPPORTED` | 指数没有可靠映射 | `cannot_confirm` |
| `STOCK_MARKET_UNSUPPORTED` | 当前不支持对应市场 | `cannot_confirm` |

### 4.2 数据源与契约

| 错误码 | 场景 | 是否重试 |
| --- | --- | --- |
| `UPSTREAM_TIMEOUT` | MCP 调用超时 | 是 |
| `DATA_SOURCE_ERROR` | AKShare 或上游网络失败 | 是 |
| `SCHEMA_MISMATCH` | 返回字段变化 | 否，需修复代码 |
| `EMPTY_DATA` | 必需接口返回空表 | 视接口而定 |
| `STALE_OR_INVALID_DATA` | 日期过期、未来日期或非法 | 否 |
| `VALUATION_SOURCE_UNAVAILABLE` | PE/PB 均不可用 | 是 |
| `STOCK_DATA_EMPTY` | 个股估值和价格均不可用 | 是 |
| `INTERNAL_ERROR` | 未分类程序错误 | 否，需排查 |

具体 Skill 错误码以 `AdvisorError` 调用点为准；新增错误码必须同步本文档和测试。

### 4.3 Web Research MCP

| 错误码 | 场景 | 是否重试 |
| --- | --- | --- |
| `WEB_RESEARCH_DISABLED` | 网页研究未启用 | 否 |
| `WEB_SEARCH_NOT_CONFIGURED` | 兜底链无凭证齐全的供应商 | 否 |
| `WEB_SEARCH_AUTH_FAILED` | 某供应商 Key 无效或权限不足 | 否 |
| `WEB_SEARCH_RATE_LIMITED` | 某供应商限流或额度用尽 | 是 |
| `WEB_SEARCH_UPSTREAM_ERROR` | 某供应商 5xx | 是 |
| `WEB_SEARCH_INVALID_RESPONSE` | 某供应商返回无效响应 | 是 |
| `WEB_SEARCH_ALL_PROVIDERS_FAILED` | 兜底链所有供应商均失败 | 视情况 |
| `WEB_FETCH_INVALID_URL` | URL 协议或凭证不合规 | 否 |
| `WEB_FETCH_PRIVATE_ADDRESS` | URL 指向私网或保留地址 | 否 |
| `WEB_FETCH_DOMAIN_BLOCKED` | 域名不在 allowlist | 否 |
| `WEB_FETCH_INVALID_REDIRECT` | 重定向缺少目标地址 | 否 |
| `WEB_FETCH_TOO_MANY_REDIRECTS` | 重定向超过三次 | 否 |
| `WEB_FETCH_TOO_LARGE` | 页面超过下载限制 | 否 |
| `WEB_FETCH_UNSUPPORTED_CONTENT` | 内容类型不受支持 | 否 |

## 5. 搜索与分析语义

### 基金搜索

```text
搜索不存在的主题
  -> fund_search ok=true
  -> count=0
  -> results=[]
  -> 展示“未找到匹配基金”
```

零结果是成功执行的搜索结果，不是上游失败。

### 基金或股票分析

```text
分析不存在的代码
  -> 目录接口通过审计
  -> FUND_NOT_FOUND / STOCK_NOT_FOUND
  -> ToolEnvelope ok=false, data=null
  -> 不生成金融 Evidence
  -> cannot_confirm
```

### 名称歧义

```text
分析名称相似的基金
  -> AMBIGUOUS_FUND
  -> 返回候选代码
  -> need_clarification
  -> 用户确认前不查询行情
```

## 6. ToolEnvelope 契约

成功：

```json
{
  "ok": true,
  "data": {},
  "error": null,
  "data_audit": []
}
```

失败：

```json
{
  "ok": false,
  "data": null,
  "error": {
    "code": "STOCK_NOT_FOUND",
    "message": "未找到 A 股",
    "retryable": false,
    "details": {}
  }
}
```

只有 `ok=true` 的结果可进入成功缓存。失败结果保留错误码、来源、已产生的审计记录和
数据策略，但不得包含伪造业务数据。

## 7. Agent 状态

| 条件 | TaskStatus | 行为 |
| --- | --- | --- |
| 实体信息不足 | `need_clarification` | 请求补充 |
| 实体歧义 | `need_clarification` | 返回候选 |
| 关键工具失败 | `cannot_confirm` | 不生成事实 |
| Evidence 为空或均被阻断 | `cannot_confirm` | 确定性空报告 |
| 非关键数据缺失 | `partial_result` | 只展示有效部分 |
| 安全策略违规 | `policy_blocked` | 不调用市场工具 |
| 响应验证失败 | `failed` | 不返回越界报告 |

`cannot_confirm` 是合法业务结果，不应统一映射为 HTTP 500。HTTP 500 只表示 Agent
执行本身发生未处理故障。

## 8. Evidence 降级

| 情况 | Evidence Grade | 输出 |
| --- | --- | --- |
| 工具和推荐文档完整 | A | 完整研究报告 |
| 工具有效、官方文档缺失 | B | 工具事实和文档缺失提示 |
| 部分指标失败 | C | 仅有效指标和明确告警 |
| 无可用工具事实 | D | 当前无法确认 |
| 策略违规 | E | 安全阻断 |

模型只允许参与 A、B、C 级报告叙述。D、E 级由确定性模板输出。

## 9. 重试规则

- 参数错误、实体不存在、实体歧义和不支持市场不重试。
- 网络超时、限流和临时 5xx 可以有限重试。
- Schema 变化不重试，避免把错误字段解释成金融事实。
- 数据过期不通过重试或改日期伪装成有效。
- 模型失败不触发市场工具重查，直接回退确定性报告。
- 重试必须幂等，不重复写入 Task、Evidence 和报告。

## 10. 日志与对外信息

日志保留：

- `trace_id`
- `task_id`
- 工具名和错误码
- 是否可重试
- 数据源和审计引用

对外不返回：

- Python 堆栈。
- 本地绝对路径。
- API Key、Token 和上游敏感响应。
- 完整持仓和私有文档内容。

## 11. 测试清单

- 不存在基金返回 `FUND_NOT_FOUND`。
- 不存在股票返回 `STOCK_NOT_FOUND`。
- 上游超时不能返回 `NOT_FOUND`。
- 歧义实体进入 `need_clarification`。
- 搜索零结果保持 `ok=true`。
- D/E 级报告没有金融事实和图表。
- 非关键 PE 或 PB 单侧失败只展示有效侧。
- 模型不能把错误信息改写成市场结论。
