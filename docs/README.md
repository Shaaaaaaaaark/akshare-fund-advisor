# 文档

仓库文档只保留三个入口：

| 文档 | 内容 |
| --- | --- |
| [项目 README](../README.md) | 项目简介、运行和验证 |
| [整体架构](ARCHITECTURE.md) | 当前/目标架构、组件边界、Harness、协议、错误和安全 |
| [Roadmap](ROADMAP.md) | 当前状态、优先级和完成标准 |

Skill 需要可独立复制，因此接口、指标和数据源审计继续保留在
[`skills/akshare-fund-advisor/`](../skills/akshare-fund-advisor/)。

维护规则：

- 架构、契约、错误和安全边界只改 `ARCHITECTURE.md`；
- 状态和实施顺序只改 `ROADMAP.md`；
- 字段级事实以 Pydantic/Java Schema 和测试为准；
- 已完成工作的过程记录使用 Git，不新增总结文档。
