# 项目文档索引

本文档是仓库文档入口，用于区分架构设计、运行约束、Prompt 和 Skill 文档。

## 阅读顺序

首次了解项目：

1. [项目 README](../README.md)：产品能力、启动方式和目录结构。
2. [HLD](HLD.md)：目标、边界、总体架构和技术选型。
3. [LLD](LLD.md)：模块实现、数据结构、状态机和面试讲解。
4. [Prompt 设计](PROMPT_DESIGN.md)：模型职责、Prompt 版本和变更流程。
5. [错误处理](ERROR_HANDLING.md)：实体、工具、证据和 API 错误语义。
6. [Web Research MCP](WEB_RESEARCH_MCP.md)：网页搜索、抓取、安全和配置。

参与开发：

1. [AGENTS.md](../AGENTS.md)：代码助手和贡献者必须遵循的仓库规则。
2. [CONTRIBUTING.md](../CONTRIBUTING.md)：开发、测试和提交要求。
3. [SECURITY.md](../SECURITY.md)：漏洞、密钥、隐私和安全边界。

Skill 独立使用：

1. [Skill 入口](../skills/akshare-fund-advisor/SKILL.md)
2. [Skill 使用说明](../skills/akshare-fund-advisor/USAGE.md)
3. [Skill 内部设计](../skills/akshare-fund-advisor/DESIGN.md)
4. [AKShare 接口映射](../skills/akshare-fund-advisor/references/akshare_api.md)
5. [专业指标口径](../skills/akshare-fund-advisor/references/professional_metrics.md)
6. [估值图表规范](../skills/akshare-fund-advisor/references/valuation_chart.md)
7. [接口审计](../skills/akshare-fund-advisor/references/interface_audit.md)

## 文档职责

| 文档 | 说明 | 何时更新 |
| --- | --- | --- |
| `README.md` | 用户入口和运行命令 | 能力、配置、目录或部署变化 |
| `AGENTS.md` | 仓库级开发约束 | 工程规则或金融红线变化 |
| `HLD.md` | 高层架构与技术决策 | 组件、边界或部署单元变化 |
| `LLD.md` | 代码级设计与状态 | Schema、流程或模块实现变化 |
| `PROMPT_DESIGN.md` | 生产 Prompt 契约 | Prompt、模型职责或版本变化 |
| `ERROR_HANDLING.md` | 错误码和降级语义 | 工具错误、状态或重试变化 |
| `WEB_RESEARCH_MCP.md` | 网页研究 MCP | 搜索供应商、工具或安全策略变化 |
| `SECURITY.md` | 安全与漏洞处理 | 信任边界、密钥或隐私变化 |
| Skill 文档 | 数据接口和指标口径 | AKShare 接口、字段或公式变化 |

## 事实来源

文档描述设计和约束，但不是运行时金融事实来源。

生产回答的事实优先级为：

```text
已审计 AKShare Tool
  > 带版本与页码的官方文档 Evidence
  > 非数值 Web 背景
  > 模型常识禁止作为金融事实
```

若文档与代码实现不一致：

- 运行行为以经过测试的代码和 Schema 为准。
- 金融安全边界取更严格的一侧。
- 修复代码或文档后，应在同一变更中恢复一致。

## 状态标记

设计文档中的能力使用以下状态：

- `已实现`：代码和测试已存在。
- `部分实现`：主链路存在，但仍有明确缺口。
- `待实现`：仅有设计，不应在 README 中声明为可用能力。
