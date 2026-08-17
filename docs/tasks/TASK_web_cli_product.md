# TASK：Web 与 CLI 双产品入口

> 状态：`已完成：实现、容器与浏览器闭环均通过`
>
> 后续方向：产品已收敛为 Web 优先；本任务中已实现的 CLI 保留兼容和调试，不继续扩展。

## 1. 目标

在不扩大金融能力范围的前提下提供两种产品形式：

- React 对话页，参考 GPT、Claude 的网页交互形式；
- 交互式 CLI，参考 Claude Code 的连续对话形式；
- 两端共用同一个 Agent API、LangGraph 和金融门禁。

## 2. 非目标

- 不做登录、账号、数据库或持久化历史；
- 不做代码编辑、Shell、插件或模型市场；
- 不改变工具白名单、错误语义或市场事实来源；
- 不引入 LangGraph checkpointer、长期记忆或多 Agent。

## 3. 实现清单

- [x] FastAPI Agent API 和健康检查；
- [x] `session/status/result/error/done` SSE 契约；
- [x] 有 TTL、数量和消息上限的进程内临时会话；
- [x] 临时会话内复用上一轮实体和意图；
- [x] `fund-advisor chat` 和 `fund-advisor ask`；
- [x] React + Vite 对话页、研究进度和 Markdown 渲染；
- [x] Node 构建阶段和 FastAPI 静态文件托管；
- [x] Compose `agent-api` 服务及两个 MCP 网络接线；
- [x] API、会话、SSE 和终端客户端测试。

## 4. 验收

- [x] Python 定向 Ruff/Pytest；
- [x] TypeScript 和 Vite 生产构建；
- [x] npm 依赖审计；
- [x] Python 全量 Ruff/Pytest；
- [x] Compose test 镜像；
- [x] 三个运行服务健康检查；
- [x] Fund/Web MCP HTTP 9+3 工具发现；
- [x] 产品 CLI 通过容器 Agent API 完成真实指数估值；
- [x] 浏览器完成页面加载、单次提交和门禁回答闭环。

## 5. 会话边界

会话只保存在 Agent API 进程内，用于保存最近消息以及上一轮实体和意图。页面刷新、
CLI 退出、会话过期或服务重启后可以清空。历史消息不能被当作金融事实，市场数值仍只能
来自通过审计的 Fund MCP。
