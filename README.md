# akshare-fund-advisor

基于 AKShare / WindPy 的中国公募基金参考咨询工具（Skill）。它把自然语言问题映射为少量稳定命令，查询真实公开接口后，输出**可核验**的基金分析、指数历史 PE/PB 估值分位，以及条件式的买入、卖出与定投参考。

> 本工具只提供金融信息分析与风险提示，**不执行交易、不承诺收益**，也不会给出“必买、必卖、满仓、抄底”等确定性指令。所有数值均来自真实接口，AI 不生成任何市场数据。

## 特性

- **多入口意图映射**：`search` / `status` / `analyze` / `valuation` / `compare` / `audit` 六个稳定命令。
- **可核验数据**：每次接口调用都经过 Schema、空值与时效校验，并记录内容指纹（`frame_sha256`）与审计信息。
- **Wind 风格指数估值**：PE TTM / PB LF 历史双图，含 3/5/10/20 年独立分位、均值、中位数、标准差参考线与极值。
- **多源降级**：`valuation --source auto` 优先本机 WindPy，不可用时回退 AKShare，且严格标注真实来源，绝不混用。
- **条件式策略**：基础定投、减量、等待、暂停追价等规则输出，标记为 `rule_based_policy_not_market_data`，不输出机械金额倍数。
- **确定性指标**：收益、波动、最大回撤、修复时间、历史分位、ETF 溢价等按固定公式计算。

## 环境要求

- macOS 或 Linux
- Python 3.9 ~ 3.12
- 可访问 AKShare 对应公开上游
- 可选：已安装并登录 Wind 终端，且本机 Python 可导入 `WindPy`

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

export SKILL_DIR="$PWD"
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

WindPy 由用户自己的 Wind 安装提供，**不在** `requirements.txt` 中。

## 命令总览

| 命令 | 输入 | 主要输出 |
| --- | --- | --- |
| `search` | 模糊名称、代码或拼音 | 候选基金，不自动选择份额 |
| `status` | 唯一基金名称或代码 | 申赎状态或标准交易时段信息 |
| `analyze` | 唯一基金名称或代码 | 产品、历史指标、估值、溢价和策略规则 |
| `valuation` | 精确指数名称、别名或代码 | PE/PB 历史统计和图表点 |
| `compare` | 2 到 5 只基金 | 各基金独立分析及可比性提示 |
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
  --source auto \
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

## 项目结构

```text
akshare-fund-advisor/
├── SKILL.md                 # 模型调用顺序、回答格式和禁止事项
├── DESIGN.md                # 系统设计、数据源、指标与策略
├── USAGE.md                 # 独立安装、命令和排错说明
├── requirements.txt         # 锁定的运行依赖
├── scripts/
│   ├── fund_advisor.py      # CLI、数据访问、校验、指标与策略规则
│   ├── run.sh               # 选择虚拟环境并启动 CLI
│   └── setup.sh             # 创建虚拟环境并安装锁定依赖
├── tests/
│   └── test_fund_advisor.py # 指标、降级、审计与错误输出回归测试
└── references/
    ├── akshare_api.md       # 接口、字段与公式契约
    ├── professional_metrics.md  # 专业指标解释
    ├── valuation_chart.md   # 指数估值图数据与渲染契约
    └── interface_audit.md   # 真实接口审计方法与历史记录
```

## 开发验证

```bash
"$SKILL_DIR/.venv/bin/python" -m py_compile "$SKILL_DIR/scripts/fund_advisor.py"
"$SKILL_DIR/.venv/bin/python" -m unittest discover -s "$SKILL_DIR/tests" -v
sh -n "$SKILL_DIR/scripts/run.sh"
sh -n "$SKILL_DIR/scripts/setup.sh"
```

单元测试不访问真实网络。接口或字段变化时，更新代码与文档后必须重新运行真实 `audit`，不得用 Mock 结果替代真实接口验证。

## 文档

- 使用说明：[USAGE.md](USAGE.md)
- 系统设计：[DESIGN.md](DESIGN.md)
- Skill 调用规范：[SKILL.md](SKILL.md)
- 接口契约：[references/akshare_api.md](references/akshare_api.md)
- 指标解释：[references/professional_metrics.md](references/professional_metrics.md)
- 估值图契约：[references/valuation_chart.md](references/valuation_chart.md)
- 接口审计：[references/interface_audit.md](references/interface_audit.md)

## 免责声明

本工具仅用于金融信息分析与研究，不构成投资建议。数据来自 AKShare / Wind 对应的公开上游，可能受网络、反爬与上游状态影响。接口失败会明确提示“当前无法确认”，不会被解释为停牌、暂停申购或休市。投资有风险，决策需谨慎。
