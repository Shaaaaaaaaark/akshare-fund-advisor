# Java 后端简历项目经历

## 推荐定位

- **项目名称**：Fund Advisor 可信基金研究与智能问答平台
- **项目角色**：Java 后端开发（个人项目可写“独立设计并实现”）
- **项目类型**：金融数据服务 / 数据分析平台 / 智能问答
- **技术栈**：Java 21、Spring Boot、Spring MVC、MyBatis、MySQL、Redis、Docker、
  Python FastAPI、React、TypeScript、ECharts

## 一页简历推荐版

**项目描述：** 面向基金、ETF、指数和 A 股研究场景，构建以 Java 为统一服务入口的
可信数据工作台。Java 侧负责接口聚合、并发与流量治理、产品数据持久化、静态资源托管及
智能分析结果转发；Python 数据服务负责金融数据采集、计算与审计，前端只消费结构化结果，
避免在多语言链路中重复计算或改写金融事实。

**核心工作：**

- 设计并实现 `React -> Java 服务 -> Python 数据/分析服务` 的多服务边界，由
  Spring Boot 统一承接数据查询、MySQL 产品数据、Redis 限流和 SSE 流式接口，
  隔离前端与内部 Python/MCP 服务，避免业务入口和数据计算职责混杂。
- 针对金融接口阻塞且响应时间不稳定的特点，使用 Java 21 虚拟线程与
  `CompletableFuture` 并行聚合指数、ETF、基金和股票数据，并按配置并发度分批提交；
  数据客户端通过并发上限和超时设置避免请求堆积和上游过载。
- 设计跨语言数据响应协议，保留来源、查询时间、数据警告、错误码及快照指纹；Java 只读
  提取展示元数据并原样返回金融数据，避免重复计算或改变数值精度。
- 建立 `available / partial / stale / unavailable / not_implemented` 状态聚合和
  `NOT_FOUND / AMBIGUOUS / UNSUPPORTED / UPSTREAM_ERROR / STALE_DATA` 错误语义，
  支持部分数据失败时保留可用结果，同时向前端暴露原始审计信息和失败原因。
- 基于 Redis Lua 实现 `INCR + EXPIRE` 原子固定窗口限流，覆盖数据查询和匿名互动
  接口；Redis 故障时采用 fail-open 并记录告警，将“保护上游”和“保持查询可用”作为明确
  取舍，同时由数据服务并发上限继续提供容量保护。
- 使用 MyBatis 和 MySQL 实现匿名投票及按钮反馈；通过事务、联合唯一索引
  及 `update -> insert -> 冲突后 update` 流程保证同一客户端对同一主题只保留一个选择，
  并用 JUnit 5、MockMvc、MockWebServer 和 Playwright 覆盖接口、并发、降级与多视口契约。

## 精简版（版面不足时使用）

**Fund Advisor 可信基金研究平台｜Java 后端开发**

Java 21 / Spring Boot / Spring MVC / MyBatis / MySQL / Redis /
Docker / Python FastAPI / React / TypeScript

- 构建 Java 统一后端服务，聚合 Python 金融数据服务并代理 SSE 流式接口，统一承接
  REST、持久化、限流、静态资源和跨域配置。
- 基于虚拟线程、`CompletableFuture` 和并发上限实现有界并行聚合；通过分批提交、
  连接/读取超时和部分结果状态，避免慢上游导致无限排队或整页不可用。
- 设计统一数据响应协议，Java 仅提取元数据并原样返回金融事实，保留来源、错误语义及
  数据快照指纹。
- 使用 Redis Lua 实现原子固定窗口限流；使用 MyBatis、MySQL 和联合唯一索引
  实现匿名互动的事务化、幂等写入。
- 完成 Docker Compose 七服务编排及 Java/Python/UI 多层测试。

## 30 秒口述版

这是一个基金研究数据平台，Java Spring Boot 是统一服务入口，后面连接 Python 数据和
智能分析服务。Java 负责接口聚合、数据持久化和稳定性控制：用虚拟线程和
CompletableFuture 并行查询多个数据模块，设置并发上限和超时，通过统一响应格式原样
返回数据及审计信息，再用 Redis Lua 做入口限流、MySQL 唯一索引保证互动幂等。智能分析
结果通过 SSE 流式返回，但市场数字必须先通过数据校验。

## 面试时优先讲的三个点

1. **为什么 Java 不计算金融数据**：跨语言职责边界、单一事实来源、原始 JSON 透传。
2. **如何处理慢上游并发**：虚拟线程、批次聚合、并发上限、超时与部分结果。
3. **如何保证写入和流量安全**：MySQL 唯一约束与冲突重试、Redis Lua 原子限流及
   fail-open 取舍。

## 不要写

- “支撑千万级并发”“性能提升 xx%”：仓库没有压测或线上流量证据。
- “微服务治理平台”：没有注册中心、配置中心、服务网格或完整治理平台。
- “分布式事务/分布式存储”：项目没有对应实现。
- “完整 RAG / 多智能体平台”：当前是固定 LangGraph + MCP Tool，不含向量检索和多 Agent。
- “模型推理优化”：只涉及外部模型 API 和应用层门禁，没有 GPU、量化、算子或推理框架代码。
