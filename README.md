# AKShare Financial Research Agent

面向中国基金、指数和 A 股研究的个人数据分析工具，也是用于面试展示可信 Agent
工程能力的项目。

项目当前优先做好两件事：

1. 用 AKShare 获取并审计基金、指数、ETF 和 A 股数据，进行确定性分析。
2. 用 LangGraph 固定状态图调用这些工具，关联已审计事实字段并解释其含义，但不生成
   市场事实、不预测涨跌、不替用户决策。

## 产品定位

它不是荐股机器人，也不是量化交易平台。目标是回答：

- 一只基金的产品类型、费用、评级、历史收益、波动和回撤如何？
- ETF 的场内价格、IOPV 和溢价风险如何？
- 指数或个股当前 PE/PB 位于历史什么位置？
- 多只基金是否同口径、能否直接比较？
- 基金产品、跟踪指数估值、历史风险和交易状态之间存在什么关联？

Agent 的职责是组织工具调用和说明关联，不能把相关性写成因果，也不能补齐工具没有
返回的数据。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| AKShare Skill CLI | 已实现 | `search`、`status`、`analyze`、`profile`、`rating`、`valuation`、`compare`、`audit` |
| Fund Advisor MCP | 已实现 | 九个强类型市场事实工具，stdio 工具发现已验证 |
| Web Research MCP | 已实现 | 三个非数值背景工具，stdio 工具发现已验证 |
| LangGraph Agent | 已实现 | 固定状态图、FactRef、事实字段关联、输出门禁和单轮 CLI |
| FastAPI / Web UI / 持久化平台 | 当前不做 | 不作为本阶段面试和个人使用的必要依赖 |
| 组合分析 / 回测 / 自动提醒 | 后续扩展 | 等单标的数据分析稳定后再评估 |

> MCP 包、依赖、配置、入口和测试接线已完成。Compose runtime/test 镜像、容器内测试、
> 两个 MCP 服务健康检查、HTTP 9+3 工具发现和 Agent 容器闭环均已通过。
> A 股 `stock_valuation` 由 MCP 和 LangGraph Agent 暴露，Skill CLI 仍不增加重复子命令。

## 核心工程设计

```text
用户问题
  -> LangGraph Agent
       - 固定 StateGraph
       - 规则优先识别问题
       - 代码白名单选择工具
       - 关联已审计工具结果
       - 校验事实、关联和限制
  -> MCP
       - 强类型参数
       - 超时、缓存和错误语义
       - 原样透传审计字段
  -> AKShare Skill
       - 实体解析
       - Schema / 时效校验
       - frame_sha256 审计
       - 确定性指标计算
```

市场事实只能来自通过审计的 Skill/MCP 结果。Web 内容固定
`numeric_allowed=false`，不能覆盖净值、价格、PE、PB、收益率、回撤、交易状态或
实体存在性。

## 已实现的数据分析

- 基金：历史收益、年化波动、下行波动、最大回撤、修复日期、最长水下期、月度收益统计。
- 产品：基金类型、经理、费用、规模、资产配置、评级、可用时的持仓集中度。
- ETF/LOF：历史价格或净值、实时价格、IOPV、统一方向的溢价率。
- 指数：PE TTM、PB、历史分位和估值图表数据。
- A 股：PE TTM、PB 与前复权价格历史，三者独立展示。
- 比较：两到五只基金的同口径比较和不可比提示。
- Web 背景：单标分析同步检索公开研究文章、财经媒体和博主/社区链接，来源分类不作身份认证。
- 审计：接口、参数、字段、行数、数据日期、内容指纹和失败语义。

## LangGraph Agent 的关联说明

LangGraph Agent 只在已审计结果之间做可验证的关联说明，例如：

- 基金历史回撤较大，同时股票仓位较高：说明两项事实同时存在，不宣称后者必然导致前者。
- ETF 价格上涨且溢价扩大：提示场内追价风险，不等于基金本身高估。
- 指数 PE 分位较高但 PB 分位中性：分别解释盈利估值与净资产估值，禁止合成总分。
- 个股价格接近区间高位且 PE 分位较高：描述历史位置，不预测后续涨跌。
- 两只基金收益差异明显但产品类型或基准不同：先提示不可直接归因于管理能力。

每条说明必须绑定输入工具、字段、数据日期和限制条件。

启用 Web Research 后，基金和股票单标分析会在市场工具之外追加两次可选搜索，分别覆盖
研究/媒体文章和博主/社区观点。搜索结果只展示标题、链接、域名和来源类别；网页摘要中的
数字不能成为市场事实，Web 失败也不能改变 Fund MCP 的错误语义。

## 稳定运行入口

```bash
export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
bash "$SKILL_DIR/scripts/setup.sh"

bash "$SKILL_DIR/scripts/run.sh" search --query "沪深300"
bash "$SKILL_DIR/scripts/run.sh" analyze --fund "510300" --years 3
bash "$SKILL_DIR/scripts/run.sh" valuation --index "沪深300" --years 10
bash "$SKILL_DIR/scripts/run.sh" compare --funds "000001" "110022" --years 3
bash "$SKILL_DIR/scripts/run.sh" audit
```

完整命令见 [Skill 使用说明](skills/akshare-fund-advisor/USAGE.md)。

LangGraph Agent：

```bash
python3.11 -m venv .venv-agent
.venv-agent/bin/python -m pip install -r requirements.txt
.venv-agent/bin/python -m pip install --no-deps -e .

.venv-agent/bin/fund-advisor-agent ask \
  --question "沪深300指数估值" \
  --output text
```

## 目录结构

```text
.
├── docs/                              # 架构、错误语义和任务文档
├── src/                               # 仓库级源码根（顺依赖方向）
│   ├── fund_advisor_agent/            # LangGraph 固定状态图与响应门禁
│   └── fund_advisor_mcp/
│       ├── fund/                      # 市场事实 MCP
│       └── web/                       # 外部背景 MCP
├── skills/akshare-fund-advisor/       # 纯数据层：可独立拷贝
│   ├── scripts/fund_advisor.py        # 数据访问、校验、指标和规则
│   ├── references/                    # 接口和指标口径
│   └── tests/                         # Skill 回归测试
├── tests/                             # MCP、Web 与 LangGraph 图级测试
└── deploy/                            # 两个 MCP 服务的 Docker Compose
```

## 当前优先任务

1. [基金与股票候选筛选](docs/tasks/TASK_asset_screening.md) 已完成 AKShare 接口审计，生产接入待实施。
2. [基金与个股数据分析处理](docs/tasks/TASK_fund_stock_data_analysis.md) 已完成当前任务清单。
3. [LangGraph Agent](docs/tasks/TASK_langgraph_agent.md) 已完成核心实现与 Docker 验证。
4. 保持 Ark 结构化模型和金融门禁回归稳定。
5. [组合分析](docs/tasks/TASK_portfolio_analysis.md) 保留为后续扩展。

## 文档

- [文档索引](docs/README.md)
- [高层设计](docs/HLD.md)
- [低层设计](docs/LLD.md)
- [错误处理](docs/ERROR_HANDLING.md)
- [Web Research MCP](docs/WEB_RESEARCH_MCP.md)
- [候选筛选任务](docs/tasks/TASK_asset_screening.md)
- [LangGraph Agent 任务](docs/tasks/TASK_langgraph_agent.md)
- [Skill 入口](skills/akshare-fund-advisor/SKILL.md)
- [Skill 内部设计](skills/akshare-fund-advisor/DESIGN.md)

## 边界

本项目仅用于金融信息分析和个人研究参考，不构成投资建议，不执行交易，不承诺收益。
历史统计和关联说明不代表因果关系，也不代表未来表现。
