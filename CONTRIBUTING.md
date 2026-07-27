# 贡献指南

本项目优先保证金融事实忠实度，其次才是回答覆盖率和语言表现。

## 开发环境

推荐只使用 Docker Desktop：

```bash
cp config/config.example.yaml config/config.local.yaml
docker compose -f deploy/compose/compose.yaml up -d --build
```

本机访问：

- Web：`http://127.0.0.1:8000/`
- OpenAPI：`http://127.0.0.1:8000/docs`

真实密钥只能放在 `config/config.local.yaml` 或环境变量中。

## 修改流程

1. 阅读 [AGENTS.md](AGENTS.md) 和相关设计文档。
2. 明确改动属于 Skill、MCP、编排、Evidence、RAG、API 还是前端。
3. 先修改最小职责模块，再补相应测试。
4. 涉及 Prompt、错误码、接口或配置时同步文档。
5. 在 Docker 中运行完整检查。

## 金融数据要求

- 市场数值只能来自通过审计的 AKShare 工具结果。
- 新增接口必须记录参数、字段、行数和 `frame_sha256`。
- 不得用 Mock、模型记忆或搜索摘要替代真实市场数据。
- 测试可以使用固定夹具，但测试数据不得进入生产结果。
- 数据源失败必须保留失败语义，不能解释成零值、停牌或实体不存在。

## Prompt 修改

生产 Prompt 位于 `src/financial_agent/prompts/`。

每次修改必须：

- 更新 Prompt 版本。
- 保持 Pydantic 输出契约。
- 增加或更新 `tests/test_prompts.py`。
- 确认模型越界时仍会回退确定性结果。
- 更新 [Prompt 设计](docs/PROMPT_DESIGN.md)。

## 测试

运行 Ruff 和全部 Pytest：

```bash
docker compose -f deploy/compose/compose.yaml \
  --profile test run --rm --build test
```

服务启动后运行工具路由评测：

```bash
docker compose -f deploy/compose/compose.yaml \
  exec agent-api python evals/runners/run_tool_routing.py
```

涉及真实接口时，应额外验证代表性输入，并检查：

- `ok`
- `data_policy.ai_may_generate_market_data`
- `data_audit.validation`
- `data_audit.frame_sha256`
- `data_warnings`
- 数据日期和时效

## 提交前检查

- 没有提交密钥、个人持仓或私有文档。
- 没有新增未经 Evidence 授权的数字。
- 不存在、歧义、不支持和上游失败没有混用。
- 新对话不会读取旧对话上下文。
- README 和设计文档与代码一致。
- Docker 测试通过。

