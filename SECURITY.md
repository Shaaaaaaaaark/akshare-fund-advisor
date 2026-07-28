# 安全策略

## 支持范围

当前项目处于个人使用和开源展示阶段，只维护默认分支的最新版本。
历史提交和第三方数据源本身不提供安全支持承诺。

## 漏洞报告

请优先使用 GitHub Security Advisory 私下报告以下问题：

- API Key、Token 或个人持仓泄露。
- 未授权访问会话、报告或文档。
- SSRF、路径穿越、SQL 注入或 Prompt injection 绕过。
- 模型可以绕过 Evidence Gate 生成金融事实。
- 未经审计的市场数值进入报告或图表。
- 跨 `conversation_id` 的上下文泄露。

报告中请提供：

- 影响范围。
- 最小复现步骤。
- 涉及的接口、模块和版本。
- 是否包含真实密钥或个人数据。

不要在公开 Issue 中提交可用密钥、完整持仓、私有文档或漏洞利用载荷。

## 密钥

- 真实密钥只允许存放在 `config/config.local.yaml` 或环境变量中。
- `config/config.local.yaml` 已被 Git 忽略，并以只读方式挂载到 API 容器。
- 日志默认不记录 Prompt 和模型响应。
- 对外监听 API 时必须配置 Bearer Token，并由反向代理提供 TLS。
- 已泄露的密钥必须立即吊销，不能只从 Git 最新提交中删除。

## 金融数据安全

金融事实采用默认拒绝策略：

```text
ToolEnvelope
  -> Schema/时效/审计校验
  -> Evidence
  -> Evidence Gate
  -> Claim
  -> 确定性渲染
  -> Response Validator
```

缺少 `validation=passed` 和 `frame_sha256` 的数值不得进入报告。Web 和模型
不得补齐净值、价格、PE、PB、收益率、回撤、交易状态或实体存在性。

## 隐私

- 会话上下文只在相同 `conversation_id` 内使用。
- 持仓进入外部模型前必须删除金额、份额、成本和精确比例。
- 文档摄取应使用有权处理的资料。
- Elasticsearch 是可重建检索和审计副本，PostgreSQL 是事实主库。
- 不在日志中记录完整持仓、原始私有文档、Token 或模型密钥。

## 外部数据源

AKShare 聚合多个公开数据源，上游失败、改版或限流不等于：

- 标的不存在。
- 价格或净值为零。
- 停牌、休市或暂停申赎。

发生失败时必须返回可审计错误，必要时降级为“当前无法确认”。

网页研究额外执行：

- 仅允许不含用户凭证的公网 `http/https` URL。
- 初始 URL 与重定向后的最终 URL 都进行 DNS/SSRF 校验。
- 禁止本机、私网、链路本地、多播和保留地址。
- 限制重定向次数、响应大小、内容类型和正文长度。
- 可配置域名 allowlist。
- 网页结果固定 `numeric_allowed=false`，不能覆盖市场工具。

## 非目标

本项目：

- 不执行交易。
- 不托管券商账户。
- 不承诺收益。
- 不替代持牌投资顾问。
- 不绕过 Wind 等商业数据授权。
