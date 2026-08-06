# akshare-fund-advisor

基于 AKShare 的中国公募基金参考咨询工具（Skill）。它把自然语言问题映射为少量稳定命令，查询真实公开接口后，输出**可核验**的基金分析、指数历史 PE/PB 估值分位，以及条件式的买入、卖出与定投参考。

> 本工具只提供金融信息分析与风险提示，**不执行交易、不承诺收益**，也不会给出“必买、必卖、满仓、抄底”等确定性指令。所有数值均来自真实接口，AI 不生成任何市场数据。

## 特性

- **多入口意图映射**：`search` / `status` / `analyze` / `valuation` / `compare` / `profile` / `rating` / `audit` 八个稳定命令。
- **可核验数据**：每次接口调用都经过 Schema、空值与时效校验，并记录内容指纹（`frame_sha256`）与审计信息。
- **专业指数估值**：PE TTM / PB 历史双图，含 3/5/10/20 年独立分位、均值、中位数、标准差参考线与极值。
- **单一可信数据源**：指数估值只调用 AKShare `stock_index_pe_lg` 和 `stock_index_pb_lg`，并保留上游来源与审计记录。
- **条件式策略**：基础定投、减量、等待、暂停追价等规则输出，标记为 `rule_based_policy_not_market_data`，不输出机械金额倍数。
- **确定性指标**：收益、波动、最大回撤、修复时间、历史分位、ETF 溢价等按固定公式计算。
- **稳定分析契约**：产品、表现、估值、交易和数据质量分组均带口径、源日期、审计引用和 warning。
- **受控比较**：合并可用评级与资产配置，只在类型、份额、口径和基准一致时生成排序视图。

## 环境要求

- macOS 或 Linux
- Python 3.9 ~ 3.12
- 可访问 AKShare 对应公开上游

依赖版本已锁定（见 [requirements.txt](requirements.txt)）：

```text
akshare==1.18.64
pandas==2.3.3
numpy==2.0.2
requests==2.32.5
curl_cffi==0.13.0
```

## 安装

```bash
git clone git@github.com:Shaaaaaaaaark/akshare-fund-advisor.git
cd akshare-fund-advisor

export SKILL_DIR="$PWD/skills/akshare-fund-advisor"
bash "$SKILL_DIR/scripts/setup.sh"
```

默认虚拟环境位于 `$SKILL_DIR/.venv`。如需自定义位置：

```bash
export AKSHARE_FUND_VENV="/absolute/path/to/venv"
bash "$SKILL_DIR/scripts/setup.sh"
```

验证入口：

```bash
bash "$SKILL_DIR/scripts/run.sh" --help
```

## 命令总览

| 命令 | 输入 | 主要输出 |
| --- | --- | --- |
| `search` | 模糊名称、代码或拼音 | 候选基金，不自动选择份额 |
| `status` | 唯一基金名称或代码 | 申赎状态或标准交易时段信息 |
| `analyze` | 唯一基金名称或代码 | 产品、历史指标、估值、溢价和策略规则 |
| `valuation` | 精确指数名称、别名或代码 | PE/PB 历史统计和图表点 |
| `compare` | 2 到 5 只基金 | 各基金独立分析及可比性提示 |
| `profile` | 唯一基金名称或代码 | 类型、经理、费用、规模和资产配置 |
| `rating` | 唯一基金名称或代码 | 第三方评级和基金分类 |
| `audit` | 代表性基金和指数 | 真实接口 Schema 与数据指纹审计 |

所有命令输出 JSON。成功退出码为 `0`，业务或数据错误为 `1`，Shell 环境缺失时 `run.sh` 返回非零。

## 快速上手

搜索基金：

```bash
bash "$SKILL_DIR/scripts/run.sh" search --query "纳斯达克" --limit 10
```

分析单只基金（默认观察 3 年，`--years` 支持 `1`/`3`/`5`）：

```bash
bash "$SKILL_DIR/scripts/run.sh" analyze --fund "513500" --years 3
```

生成指数历史 PE/PB 图表数据（默认 10 年）：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "沪深300" \
  --years 10 \
  --max-points 600
```

查询申赎与交易时段状态：

```bash
bash "$SKILL_DIR/scripts/run.sh" status --fund "510300"
```

比较 2~5 只基金：

```bash
bash "$SKILL_DIR/scripts/run.sh" compare --funds "000001" "110022" --years 3
```

真实接口审计：

```bash
bash "$SKILL_DIR/scripts/run.sh" audit
```

## 数据完整性

每次 AKShare 调用都经过统一校验：校验返回类型、拒绝重复列名与非法空表、检查必需字段、记录内容指纹并区分必需/可选接口的失败语义。时间序列不插值、不前向填充、不由模型补点；PE/PB 与基金历史最新日期最多滞后 10 天，ETF 即时行情最多滞后 3 天。

引用任何数值前应确认：

1. `data_policy.ai_may_generate_market_data == false`
2. 对应接口 `data_audit.validation == "passed"`
3. 指标自身日期与 `latest_age_days` 合格
4. `data_warnings` 未声明该数据不可用于结论

## Agent 集成边界

本 Skill 是金融 Agent 的事实与确定性计算层；仓库内同时提供最小 LangGraph Agent：

- **Skill 内**：基金/指数解析、AKShare 查询、Schema 与时效校验、`frame_sha256` 审计、确定性指标和有限规则输出。
- **MCP 层**：九个市场事实工具、三个 Web 背景工具，以及 Schema、超时、进程内缓存、调用日志和进程隔离。
- **Web MCP**：搜索公开研究、财经媒体和博主/社区链接，按需读取网页和用户给定文档，只提供 `numeric_allowed=false` 的背景。
- **LangGraph Agent 层**：固定状态图、工具白名单、FactRef、单标文章/博主双查询、事实字段关联说明和输出校验。

LangGraph Agent 可以关联解释基金产品、历史风险、指数估值和交易状态，但不得把相关性
写成因果，也不得用训练记忆、网页摘要或外部文档覆盖 Skill 返回的数值、日期、来源和
警告。

启用 Web Research 时，基金和股票单标分析固定追加两次可选搜索。输出中的来源类别只按
域名和标题规则生成，不代表博主身份或内容真实性已经核验；搜索失败时保留已审计的市场
分析并标记部分结果。

Agent 单轮入口：

```bash
fund-advisor-agent ask \
  --question "沪深300指数估值" \
  --output text
```

默认使用规则关联；只有显式配置 OpenAI-compatible 模型并启用开关时才调用结构化模型。

## 项目结构

```text
skills/akshare-fund-advisor/   # 纯数据层，可独立拷贝
├── SKILL.md                 # 模型调用顺序、回答格式和禁止事项
├── DESIGN.md                # 系统设计、数据源、指标与策略
├── USAGE.md                 # 独立安装、命令和排错说明
├── requirements.txt         # 锁定的运行依赖
├── scripts/
│   ├── fund_advisor.py      # CLI、数据访问、校验、指标与策略规则
│   ├── audit_quality_interfaces.py # 候选筛选接口 discovery audit
│   ├── run.sh               # 选择虚拟环境并启动 CLI
│   └── setup.sh             # 创建虚拟环境并安装锁定依赖
├── tests/
│   └── test_fund_advisor.py # 指标、降级、审计与错误输出回归测试
└── references/
    ├── akshare_api.md       # 接口、字段与公式契约
    ├── professional_metrics.md  # 专业指标解释
    ├── valuation_chart.md   # 指数估值图数据与渲染契约
    ├── interface_audit.md   # 生产接口审计方法与历史记录
    └── quality_interface_audit.md # 财务、行业和基金质量候选接口审计
```

MCP 与 LangGraph Agent 源码位于仓库级源码根（不随 skill 拷贝）：

```text
src/
├── fund_advisor_mcp/        # config、fund/ 市场事实 MCP、web/ 背景 MCP
└── fund_advisor_agent/      # LangGraph 固定状态图、FactRef、门禁与 CLI
```

## 开发验证

```bash
"$SKILL_DIR/.venv/bin/python" -m py_compile "$SKILL_DIR/scripts/fund_advisor.py"
"$SKILL_DIR/.venv/bin/python" -m unittest discover -s "$SKILL_DIR/tests" -v
sh -n "$SKILL_DIR/scripts/run.sh"
sh -n "$SKILL_DIR/scripts/setup.sh"
```

单元测试不访问真实网络。接口或字段变化时，更新代码与文档后必须重新运行真实 `audit`，不得用 Mock 结果替代真实接口验证。

根目录安装 Agent 依赖后，还需运行：

```bash
.venv-agent/bin/python -m ruff check --no-cache .
.venv-agent/bin/python -m pytest -q -p no:cacheprovider
```

当前本地和容器测试、stdio/HTTP 工具发现、Docker 服务健康检查及 Agent 容器闭环均已
通过；Ark thinking 模型的 Pydantic 结构化关联输出与门禁闭环也已验证。

## 文档

- 使用说明：[USAGE.md](USAGE.md)
- 系统设计：[DESIGN.md](DESIGN.md)
- 金融 Agent 高层设计：[../../docs/HLD.md](../../docs/HLD.md)
- Skill 调用规范：[SKILL.md](SKILL.md)
- 接口契约：[references/akshare_api.md](references/akshare_api.md)
- 指标解释：[references/professional_metrics.md](references/professional_metrics.md)
- 估值图契约：[references/valuation_chart.md](references/valuation_chart.md)
- 接口审计：[references/interface_audit.md](references/interface_audit.md)
- 候选接口审计：[references/quality_interface_audit.md](references/quality_interface_audit.md)

## 免责声明

本工具仅用于金融信息分析与研究，不构成投资建议。数据来自 AKShare 对应的公开上游，可能受网络、反爬与上游状态影响。接口失败会明确提示“当前无法确认”，不会被解释为停牌、暂停申购或休市。投资有风险，决策需谨慎。
