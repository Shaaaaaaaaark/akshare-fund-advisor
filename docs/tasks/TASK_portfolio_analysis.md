# TASK：组合分析（portfolio_analyze）

> 状态：`后续扩展，当前暂缓`
> 关联设计：当前仅保留本任务草案，实施前重新评审 HLD/LLD
> 当前优先级：低于 [基金与个股数据分析处理](TASK_fund_stock_data_analysis.md) 和
> [最小 LangGraph Agent](TASK_langgraph_agent.md)

## 1. 背景与目标

现有能力全部是**单标的**分析（估值、分位、定投信号），但真实投资决策发生在**组合层**。
本任务作为后续扩展，用于把研究扩展到组合层，回答两个单标的视角看不到的问题：

- **是否假分散**：手里的基金/ETF 是不是同涨同跌（高相关）。
- **组合真实可承受回撤**：能承受的是组合的波动/回撤，而非单只的加总。

产出一个确定性工具 `portfolio_analyze`，先做**相关性矩阵 + 组合层波动/最大回撤**两件，
数据最稳、零红线风险、对个人决策价值最高。

## 2. 范围

### 做（第一阶段）
- 相关性矩阵（成分日收益率，共同交易日区间，皮尔逊相关）。
- 组合层年化波动 + 历史最大回撤（按用户权重合成组合净值曲线）。

### 后续增量（不在本任务）
- 资产类别暴露（加权股/债/现金，复用 `fund_profile` 的 `asset_allocation`）。
- 前十大重仓重叠 / 集中度（`fund_portfolio_hold_em`，接口不稳，失败即标 `UNSUPPORTED`）。

### 明确不做（守红线）
- 行业/风格暴露、因子归因（无稳定分类数据）。
- alpha 信号、收益预测、择时模型。
- 最优权重求解（马科维茨类）——本质是代客决策，且对输入协方差极敏感，撞红线。

## 3. 数据可行性（已盘点，基于真实代码）

| 能力 | 可行性 | 依赖接口（均已在用） |
| --- | --- | --- |
| 相关性矩阵 | ✅ 最稳 | `fund_open_fund_info_em` / `fund_etf_hist_em` / `fund_lof_hist_em` + `tool_trade_date_hist_sina` 对齐 |
| 组合波动/回撤 | ✅ | 同上 + 用户权重，回撤复用 `calculate_holding_experience` |
| 资产暴露（增量） | ✅ | `fund_individual_detail_hold_xq`（`asset_allocation` 已实现） |
| 重仓重叠（增量） | ⚠️ | `fund_portfolio_hold_em`（只前十大、接口不稳） |
| 行业/风格 | ❌ | 无稳定分类接口，不做 |

## 4. 分阶段任务

### 阶段 A：Skill 确定性动作 `portfolio`
- [ ] 在 `skills/akshare-fund-advisor/scripts/fund_advisor.py` 新增 `portfolio` 动作。
- [ ] 输入 `[{code, weight}]`，`Decimal` 权重，2–20 个成分，权重和容差校验（否则 `PORTFOLIO_WEIGHTS_INVALID`）。
- [ ] 复用现有行情管线取各成分序列；用 `tool_trade_date_hist_sina` 对齐交易日，只取共同区间。
- [ ] 共同样本天数 < 阈值 → `PORTFOLIO_SAMPLE_TOO_SHORT`；某成分行情缺失 → `PORTFOLIO_COMPONENT_UNAVAILABLE`，保留已取成分。
- [ ] 计算相关性矩阵、组合年化波动、最大回撤（回撤复用 `calculate_holding_experience`）。
- [ ] 输出带 `data_audit`、共同区间起止、样本天数、缺失标注、`data_policy`。
- [ ] `run.sh` / argparse 增加 `portfolio` 子命令。
- [ ] 更新 `references/professional_metrics.md`：相关性与组合回撤的口径、样本要求、局限。

### 阶段 B：MCP 工具 `portfolio_analyze`
- [ ] `fund/schemas.py`：`ToolName` 加 `PORTFOLIO_ANALYZE`，新增输入/输出 Schema。
- [ ] `fund/adapter.py`：加 `portfolio_analyze` 适配，规范化为 `ToolEnvelope`（不改写数值）。
- [ ] `fund/server.py`：注册 `@mcp.tool() portfolio_analyze`。
- [ ] 更新工具发现数量断言 **9 → 10**（healthcheck / 测试里所有硬编码 9 的地方）。
- [ ] 缓存 TTL：按行情类工具口径设置。

### 阶段 C：LangGraph Agent 编排与意图
- [ ] 意图枚举加 `PORTFOLIO_REVIEW`。
- [ ] 意图识别：命中「我的组合 / 持仓相关性 / 组合风险 / 分散」等 → `PORTFOLIO_REVIEW`。
- [ ] `PLAN_REGISTERED_TOOLS` 白名单：`PORTFOLIO_REVIEW → portfolio_analyze`。
- [ ] `VALIDATE_TOOL_ENVELOPES` 只从成功的组合工具结果构造 `FactRef`。
- [ ] 报告渲染：相关性/回撤结论 + 强制附「过去不代表未来」，权重回显来自用户输入。
- [ ] 注：第一版用**无状态传参** `[{code, weight}]`，不引入持仓数据库。

## 5. 红线约束（每阶段都必须守）
- 相关性、波动、回撤都是**历史统计**，不得预测收益、不得给确定性买卖指令。
- 权重来自**用户输入**，`Decimal` 校验；模型不得生成、补齐或改写权重与相关系数。
- 任一成分缺失或共同样本过短 → 按错误语义拒绝完整组合结论，不用模型补数。
- 币种不一致且没有审计汇率工具时不合并金额。

## 6. 验收标准
- [ ] `docker compose -f deploy/compose/compose.yaml --profile test run --rm --build test` 全绿（ruff + pytest）。
- [ ] 新增 skill 测试（`skills/akshare-fund-advisor/tests/test_fund_advisor.py`）：
  - 相关性对齐：错位交易日 / 部分成分停牌，只在共同区间计算且披露样本天数。
  - 权重校验：和≠1、负权重、单一成分被拒（`PORTFOLIO_WEIGHTS_INVALID`）。
  - 缺失降级：某成分不可用 → `PORTFOLIO_COMPONENT_UNAVAILABLE`，不产出完整 `portfolio_risk`。
  - Decimal 权重与舍入、相关系数/回撤的确定性快照。
- [ ] 真实 AKShare 冒烟：一个多成分组合返回相关性矩阵 + 组合回撤，`data_audit` 完整。
- [ ] 工具发现数量断言更新为 10 且通过。

## 7. 文档同步（完成编码后）
- [ ] 重新评审并更新 HLD/LLD。
- [ ] ERROR_HANDLING：增加实际实现的错误码。
- [ ] README「当前能力」：工具数量与能力描述更新为含组合分析。
- [ ] SKILL.md：新增 `portfolio` 动作的输入/输出/口径与红线说明。

## 8. 待确认（编码前可选决策）
- 相关性/回撤第一版是否与资产暴露体检合并成一次调用（默认：先只做相关性+回撤）。
- 持仓输入方式（默认：无状态传参；是否后续接 `portfolio` 持仓存储另开任务）。
- 共同样本天数阈值待实施前确认；年化因子沿用现有 Skill 的 `250` 个交易日口径。
