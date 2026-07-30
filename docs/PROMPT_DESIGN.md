# Prompt 设计与治理

## 1. 目的

本文档描述生产 Agent 使用的 Prompt、模型权限、版本策略和测试要求。

Prompt 不是金融事实校验器。以下规则必须由代码执行：

- 基金、股票和指数实体确认。
- 工具白名单和参数范围。
- 数据时效、Schema、审计和数值计算。
- Evidence 授权、Claim 生成和响应校验。
- 会话隔离、隐私脱敏和策略阻断。

## 2. Prompt 资产

生产 Prompt 的唯一代码来源：

```text
src/financial_agent/prompts/
├── __init__.py
└── catalog.py
```

当前 Prompt：

| Prompt | 版本常量 | 调用位置 | 模型职责 |
| --- | --- | --- | --- |
| Intent Classifier | `INTENT_CLASSIFIER_PROMPT_VERSION` | `orchestration/intent.py` | 规则无法覆盖时分类和提取实体候选 |
| Report Narrator | `REPORT_NARRATOR_PROMPT_VERSION` | `models/narrator.py` | 解释已授权 facts |

公共安全策略版本：

```python
PROMPT_POLICY_VERSION
```

业务模块不得新增内联 system prompt。新增模型节点时，先在 Prompt 目录登记版本化
Prompt，再由节点导入。

## 3. Prompt 与代码门禁

```text
用户问题
  -> 规则优先意图识别
  -> 可选 Intent LLM
  -> Pydantic IntentDecision
  -> 代码工具规划
  -> ToolEnvelope
  -> 可选外部背景（仅网页研究/读文档意图调用 web-research MCP）
  -> Evidence Gate
  -> 确定性 Report
  -> 可选 Narrator LLM
  -> Pydantic NarrationOutput
  -> Response Validator
```

模型失败、输出非法或越界时：

- 意图分类回到规则结果或要求澄清。
- 外部背景通道失败时保留已确认工具事实，不阻断主流程。
- 报告叙述回到确定性模板。
- 不通过模型重试补造工具数据。

## 4. Intent Classifier

### 4.1 输入

只输入当前已完成会话内上下文解析后的用户问题：

```text
resolved_query
```

新对话不会读取旧对话实体。

### 4.2 输出

输出必须通过 `IntentDecision`：

```json
{
  "intent": "unsupported",
  "entities": [],
  "needs_clarification": true,
  "clarification_question": "请补充具体研究标的。",
  "confidence": 0.8
}
```

### 4.3 边界

- 模型只能提取实体候选，不能确认实体存在。
- 模型不得创建工具名或工具参数。
- 代码和名称不得从训练记忆补齐。
- 用户输入中的 Prompt injection 只能作为待分类文本。
- 规则分类优先；默认配置不启用 LLM 意图分类。

## 5. Report Narrator

### 5.1 输入

Narrator 只接收：

```text
title
summary
facts[label, display_value, as_of, evidence_id]
evidence_grade
warnings
```

不发送原始 Tool DataFrame、完整持仓、金额、份额或成本。

### 5.2 输出

输出必须通过 `NarrationOutput`：

```json
{
  "analysis": [
    "只基于输入 facts 的解释"
  ]
}
```

Narrator 不能修改 facts、Evidence、引用、等级和报告状态。

### 5.3 二次校验

`ResponseValidator` 检查：

- Fact 是否能反查 Evidence。
- Fact 值和展示值是否被修改。
- 正文是否出现未经 Evidence 授权的数字。
- D/E 级报告是否包含金融事实。
- 是否出现确定性投资表达。

校验失败时丢弃模型叙述，保留确定性报告并记录告警。

## 6. 外部背景通道（无模型 Prompt）

网页研究和读文档意图会调用独立的 web-research MCP（`web_search` / `web_fetch` /
`document_read`），这是确定性工具调用，不使用模型 Prompt 规划检索：

- 只有 `WEB_RESEARCH` 和 `DOCUMENT_QA` 意图触发外部通道，其余意图只用市场工具事实。
- `DOCUMENT_QA` 从用户原文正则提取 URL 调 `document_read` 读取原文；找不到 URL 则不检索。
- `WEB_RESEARCH` 先 `web_search` 再逐条 `web_fetch`，命中转为低置信度背景证据。
- 所有外部命中固定 `numeric_allowed=false`，不能覆盖或提升为市场数值与官方产品条款。
- 通道失败只记录降级告警，保留已确认的工具事实，不阻断主流程。

## 7. Prompt 版本

版本格式：

```text
<prompt-name>-YYYY-MM-DD[.revision]
```

以下变更必须升级版本：

- 模型职责或允许输入变化。
- 输出字段或 Schema 变化。
- 金融红线、隐私规则或 Prompt injection 规则变化。
- 示例可能改变模型决策边界。

仅修正文档错别字且运行 Prompt 未变化时，不升级版本。

审计记录至少保留：

- Prompt 版本。
- 模型别名和供应商模型名。
- 调用时间和 Trace ID。
- 输入 Evidence/Claim 版本引用。
- 输出校验结果。

默认不记录 Prompt 正文和用户原文；只有在无隐私测试环境中才可临时开启
`observability.log_prompts`。

## 8. 变更流程

1. 修改 `src/financial_agent/prompts/catalog.py`。
2. 更新对应版本常量。
3. 确认 Pydantic Schema 未被绕过。
4. 更新 `tests/test_prompts.py` 和相关节点测试。
5. 运行工具路由、数值忠实度和 Prompt injection 评测。
6. 更新本文档中的职责或边界。

## 9. 评测要求

Intent Prompt：

- 未知名称不能被模型确认存在。
- 用户要求创建自由工具时必须拒绝。
- 不支持问题进入 `unsupported` 或澄清。
- 实体字段只能来自用户原文。

Narrator Prompt：

- 不增加新数字、日期、代码和名称。
- 不把历史分位写成未来概率。
- 不合并 PE/PB。
- 不弱化 warning。
- 不输出确定性交易指令。

外部背景通道（确定性，非 Prompt）：

- 只有网页研究/读文档意图触发外部通道，其余意图不调用。
- `DOCUMENT_QA` 找不到 URL 时不检索。
- 外部命中固定 `numeric_allowed=false`，不能覆盖市场数值。
- 通道失败时保留工具事实并记录降级告警。

Prompt 测试只能证明文本契约存在，不能替代 Evidence Gate 和 Response Validator。
