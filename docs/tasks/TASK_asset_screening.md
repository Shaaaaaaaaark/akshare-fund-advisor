# TASK：可审计基金与股票候选筛选

> 状态：`接口审计已完成，排队中`
>
> 启动条件：已满足（投研工作台 M1 指数页面稳定）；当前仍排在主动基金详情之后。
>
> 审计依据：
> [quality_interface_audit.md](../../skills/akshare-fund-advisor/references/quality_interface_audit.md)

## 1. 目标

实现两个确定性工具：

- `stock_screen`：从沪深 A 股财务横截面中按显式规则筛选候选；
- `fund_screen`：在同基金类型和同份额口径内筛选候选。

输出不是排名结论，而是逐候选规则证据：

```text
passed_rules
failed_rules
unknown_rules
metric_basis
as_of
audit_ref
```

## 2. 非目标

- 不预测收益、目标价或买卖时点；
- 不做机器学习、因子挖掘、alpha 或黑箱评分；
- 不合成 PE/PB、评级、收益和风险总分；
- 不跨基金类型、份额类别和数据日期比较；
- 不用 Web 或模型补充市场数字；
- 不实现组合优化和回测。

## 3. 当前基线

已完成：

- 盘点并真实调用 24 个财务、行业和基金质量候选接口；
- 记录 Schema、日期覆盖、缺失、唯一性和 `frame_sha256`；
- 区分可接入、需降级和当前拒绝的接口；
- 提供可复现审计脚本。

尚未实现：

- `stock_screen`、`fund_screen` Skill 动作；
- MCP Schema、Adapter 和 Server 工具；
- Agent Intent、白名单和 FactRef；
- Go Dashboard API 和 Web 候选页面。

## 4. 实施顺序

### S1：规则与输出契约

主要文件：

```text
skills/akshare-fund-advisor/scripts/
skills/akshare-fund-advisor/references/
skills/akshare-fund-advisor/tests/
```

- [ ] 定义版本化筛选输入和输出 Schema。
- [ ] 每条规则声明字段、单位、比较方向、缺失语义、日期和审计引用。
- [ ] 阈值只能来自代码配置或用户输入。
- [ ] 缺失字段进入 `unknown_rules`，不按失败或零值处理。
- [ ] 只允许同口径候选做确定性排序视图。

### S2：股票候选池

- [ ] 使用 `stock_yjbb_em` 构建沪深 `0/3/6` 财务横截面。
- [ ] 输入包含报告期、显式启用规则和最大候选数量。
- [ ] 拒绝未来公告日期、无效代码、非沪深代码和重复冲突记录。
- [ ] ROE、毛利率、收入增长或现金流缺失时不填充。
- [ ] 行业缺失进入未知规则。
- [ ] 深度核验按需读取财务指标、三张表和主营构成。
- [ ] 同一指标绑定同一报告期和公告日期。
- [ ] 行业比较只使用同一分类标准、行业编码和日期。
- [ ] 不读取盈利预测作为当前事实。

允许的确定性派生项：

```text
资产负债率
经营现金流 / 净利润
多期 ROE、收入和利润稳定性
商誉 / 总资产
主营收入集中度
```

### S3：基金候选池

- [ ] 按基金类型分别调用 `fund_open_fund_rank_em`。
- [ ] 用基金目录确认代码、类型和份额类别。
- [ ] 校验日期、历史长度、缺失和唯一性。
- [ ] 用本地净值序列重算收益、波动、回撤和持有体验。
- [ ] 评级保持独立维度，不合成总分。
- [ ] 多位经理按基金代码聚合。
- [ ] 行业配置明确报告期，不表述为实时仓位。

### S4：MCP 与 Agent

主要文件：

```text
src/fund_advisor_mcp/fund/schemas.py
src/fund_advisor_mcp/fund/adapter.py
src/fund_advisor_mcp/fund/server.py
src/fund_advisor_agent/state.py
src/fund_advisor_agent/policies.py
tests/
```

- [ ] 新增 `STOCK_SCREEN`、`FUND_SCREEN` ToolName 和输入 Schema。
- [ ] Adapter 只封装 Skill 输出，不重算数值。
- [ ] Fund MCP 工具数从 10 调整为 12，并同步工具发现测试。
- [ ] 新增两个 Agent Intent 和代码白名单。
- [ ] 复用现有固定图，不增加动态规划或 ReAct。
- [ ] FactRef 精确绑定规则字段、日期和审计哈希。
- [ ] 模型不能增加、删除或重排候选。

### S5：Dashboard 接入

在 Skill、MCP 和 Agent 验收完成后才接入：

- [ ] Go BFF 新增候选 API，只聚合和透传结果。
- [ ] 未实现或上游失败不返回空候选。
- [ ] Web 展示通过、失败、未知三态和口径。
- [ ] 候选可进入单标详情和页面上下文 Agent。
- [ ] 不显示综合分、收益预测或买卖标签。

## 5. 当前拒绝的接口

以下接口未通过当前审计，不得接入主路径：

| 接口 | 原因 |
| --- | --- |
| `stock_individual_info_em` | 列契约和上游可用性不稳定 |
| `stock_board_industry_name_em` / `stock_board_industry_cons_em` | 连续上游断连 |
| `fund_individual_analysis_xq` | `*_rank` 字段语义未确认 |
| `fund_scale_change_em` / `fund_hold_structure_em` | 市场整体数据，不是单基金 |
| `fund_portfolio_change_em` | 当前解码失败 |
| `fund_etf_fund_info_em` | 返回列数不匹配 |

状态变化前必须重新审计，不能仅根据函数存在就恢复使用。

## 6. Definition of Done

- [ ] 股票候选只含沪深 A 股规范代码。
- [ ] 基金候选不跨类型、份额和指标口径。
- [ ] 所有市场数字可反查接口、字段、日期和 `frame_sha256`。
- [ ] 缺失字段进入 `unknown_rules`。
- [ ] 上游失败不会表达为“没有优秀资产”。
- [ ] 不存在综合 AI 分数、收益预测或确定性交易指令。
- [ ] Skill 单元测试、MCP/Agent 测试和工具数量断言通过。
- [ ] 真实接口冒烟和 Docker 黑盒通过。
- [ ] 接入工作台后更新主任务 M6 状态，不新增重复 TASK。
