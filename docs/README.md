# 项目文档索引

## 推荐阅读顺序

1. [项目 README](../README.md)：产品定位、当前状态和稳定运行入口。
2. [HLD](HLD.md)：目标架构、数据分析边界和 LangGraph Agent 关联说明。
3. [LLD](LLD.md)：当前代码结构、MCP 契约和最小 LangGraph Agent 设计。
4. [错误处理](ERROR_HANDLING.md)：实体、工具和上游错误语义。
5. [Web Research MCP](WEB_RESEARCH_MCP.md)：搜索、抓取和 SSRF 边界。
6. [基金与股票候选筛选任务](tasks/TASK_asset_screening.md)：候选接口审计已完成，生产接入待实施。
7. [基金与个股数据分析任务](tasks/TASK_fund_stock_data_analysis.md)：P0、单标增强、测试和环境验证已完成。
8. [LangGraph Agent 任务](tasks/TASK_langgraph_agent.md)：核心固定图、门禁、CLI 和 Docker 闭环已完成。
9. [组合分析任务](tasks/TASK_portfolio_analysis.md)：后续扩展。

## Skill 文档

1. [Skill 入口](../skills/akshare-fund-advisor/SKILL.md)
2. [Skill 使用说明](../skills/akshare-fund-advisor/USAGE.md)
3. [Skill 内部设计](../skills/akshare-fund-advisor/DESIGN.md)
4. [AKShare 接口映射](../skills/akshare-fund-advisor/references/akshare_api.md)
5. [专业指标口径](../skills/akshare-fund-advisor/references/professional_metrics.md)
6. [估值图表契约](../skills/akshare-fund-advisor/references/valuation_chart.md)
7. [接口审计](../skills/akshare-fund-advisor/references/interface_audit.md)
8. [财务、行业与基金质量候选接口审计](../skills/akshare-fund-advisor/references/quality_interface_audit.md)

## 文档状态规则

| 状态 | 含义 |
| --- | --- |
| 已实现 | 当前代码和测试中存在 |
| 接线重构中 | 代码已移动，但包入口、import、测试或部署尚未恢复 |
| 待实现 | 只有设计，不应在 README 中声明可用 |
| 后续扩展 | 当前明确不做 |

当文档与代码不一致时：

- 运行能力以当前代码、安装入口和测试为准；
- 金融安全边界采用更严格的一侧；
- 必须修正文档，不能用“设计如此”掩盖实现缺失。

## 当前事实来源

```text
审计通过的 AKShare Skill / Fund MCP
  > 用户指定的官方文档原文
  > 非数值 Web 背景
  > 模型常识不得作为市场事实
```
