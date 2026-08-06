# 贡献指南

本项目优先保证金融事实忠实度，其次才是功能覆盖和语言表现。

## 当前开发顺序

1. 按 discovery audit 结果实现基金与股票候选筛选；
2. 完善基金、指数和个股数据分析；
3. 保持 MCP、LangGraph Agent、Ark 模型和门禁稳定；
4. 保持 Docker 镜像、Compose 服务和 HTTP MCP 验证稳定；
5. 组合、回测、UI 和持久化留作后续。

## 修改流程

1. 阅读 [AGENTS.md](AGENTS.md) 和相关设计文档。
2. 明确改动属于 Skill、Fund MCP、Web MCP 或 LangGraph Agent。
3. 先修改最小职责模块。
4. 补充单元测试和必要的真实接口审计。
5. 同步接口、指标、错误和任务文档。

## 金融数据要求

- 市场数值只能来自审计通过的 AKShare 结果。
- 新增接口必须记录参数、字段、行数、日期和 `frame_sha256`。
- 不得用 Mock、模型记忆或网页摘要替代生产数据。
- 时间序列不得插值、前向填充或跨标的补点。
- 数据源失败不得解释为零值、停牌或实体不存在。
- 净值历史位置不得写成估值分位。
- PE 与 PB 不合成综合估值分。

## Agent 要求

新增 Agent 功能时：

- 只使用 LangGraph `StateGraph`、显式节点和条件边；
- 不使用 LangChain AgentExecutor、开放式 ReAct、动态工具名或长期 Memory；
- 只能调用注册工具白名单；
- 关联说明必须引用工具字段；
- 必须区分事实、关联和限制；
- 相关性不得表述为因果；
- Web 数字不得进入市场事实；
- 回答中的市场数值必须能在工具信封中逐项找到；
- 不输出确定性买卖指令。

## 测试

Skill 稳定入口：

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
"$SKILL_DIR/.venv/bin/python" -m unittest discover -s "$SKILL_DIR/tests" -v
sh -n "$SKILL_DIR/scripts/run.sh"
sh -n "$SKILL_DIR/scripts/setup.sh"
```

接口或字段变化后执行真实审计：

```bash
bash "$SKILL_DIR/scripts/run.sh" audit
```

根目录 Ruff/Pytest 必须通过。LangGraph 变更还必须覆盖节点、条件边、完整图路径和响应
门禁；Docker 相关改动必须在 daemon 可用时运行 Compose 测试。

## 提交前检查

- 没有提交密钥、持仓或私有文档；
- 文档没有把待实现能力写成已实现；
- 不存在、歧义、不支持、过期和上游失败没有混用；
- 指标口径、接口契约和测试同步；
- Agent 说明未新增数字或无证据因果关系。
