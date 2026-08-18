# 文档索引

> 最后按代码、Compose、路由、工具注册和浏览器验收核对：2026-08-18。

## 仓库文档

| 文档 | 唯一职责 |
| --- | --- |
| [项目 README](../README.md) | 当前状态、快速运行、当前任务入口 |
| [产品范围](PRODUCT.md) | 做什么、不做什么、产品原则 |
| [系统架构](HLD.md) | 组件职责、数据流、状态和技术边界 |
| [Go/Python 透传契约](GO_PYTHON_CONTRACT.md) | Data API、跨语言字段、状态和 SSE 透传规则 |
| [错误语义](ERROR_HANDLING.md) | 错误码、降级和重试 |
| [Web Research MCP](WEB_RESEARCH_MCP.md) | 搜索、抓取、文档读取和 SSRF 边界 |

不再维护独立 LLD。当前代码结构写在 HLD，字段级细节以 Pydantic/Go Schema、测试和专用
契约为准，避免文档复制代码后漂移。

## 活跃开发任务

| 任务 | 状态 | 下一步 |
| --- | --- | --- |
| [投研数据工作台](tasks/TASK_research_dashboard.md) | M1 指数、M2 ETF 终端和 ETF Agent 抽屉已完成 | 补主动基金产品档案和非 ETF 详情 |
| [数据源交叉校验审计](tasks/TASK_data_source_cross_validation.md) | A 股首个闭环和已接入页面 warning 展示完成 | 推进 ETF/基金净值和指数生产校验 |
| [候选筛选](tasks/TASK_asset_screening.md) | 接口审计已完成，工具未实现 | 完成筛选 Schema 和确定性工具 |

已完成任务不保留独立文档；实现事实由代码、测试、Git 历史和 HLD 状态表承载。当前暂缓的
组合分析不保留 TASK，重新立项时再按实际需求创建。

## Skill 文档

Skill 目录需要独立拷贝和运行，因此保留自己的文档体系：

| 文档 | 职责 |
| --- | --- |
| [SKILL.md](../skills/akshare-fund-advisor/SKILL.md) | Agent 调用指令和安全规则 |
| [README.md](../skills/akshare-fund-advisor/README.md) | 独立包入口和快速使用 |
| [USAGE.md](../skills/akshare-fund-advisor/USAGE.md) | CLI 参数和示例 |
| [DESIGN.md](../skills/akshare-fund-advisor/DESIGN.md) | Skill 内部数据与计算设计 |
| [AKShare 接口映射](../skills/akshare-fund-advisor/references/akshare_api.md) | 接口、字段和口径 |
| [专业指标](../skills/akshare-fund-advisor/references/professional_metrics.md) | 公式和限制 |
| [估值图表](../skills/akshare-fund-advisor/references/valuation_chart.md) | 图表数据契约 |
| [接口审计](../skills/akshare-fund-advisor/references/interface_audit.md) | 单标接口审计结果 |
| [候选接口审计](../skills/akshare-fund-advisor/references/quality_interface_audit.md) | 筛选接口审计结果 |
| [多源交叉校验](../skills/akshare-fund-advisor/references/source_cross_validation.md) | Baostock/efinance 许可、接口、实测和接入边界 |

## 维护规则

- 产品范围只改 `PRODUCT.md`。
- 架构和组件职责只改 `HLD.md`。
- 跨语言字段只改 `GO_PYTHON_CONTRACT.md`。
- 错误码只改 `ERROR_HANDLING.md`。
- 当前进度和实施步骤只改活跃 TASK。
- 已完成实现不创建“历史任务总结”文档，使用 Git 记录。
- 文档与代码冲突时，以代码、测试和更严格的金融安全边界为准，并立即修正文档。
