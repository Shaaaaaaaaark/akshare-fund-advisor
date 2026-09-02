# 数据源交叉校验审计

最近审计日期：`2026-09-01`

本审计只评估校验源覆盖、口径、稳定性和许可风险。AKShare 仍是生产主源；校验源只产生
`data_audit` 和 `data_warnings`，不投票、平均、覆盖或修复主源数值。

## 1. 版本与许可

| 数据源 | 审计版本 | 包元数据 | 接入结论 |
| --- | --- | --- | --- |
| Baostock | `0.9.3` | BSD License | 默认安装；独立 Skill 默认关闭，仓库 Compose 对 A 股和 ETF 启用 |
| efinance | `0.5.9` | PyPI/GitHub 标记 MIT；官方文档同时声明不得商用 | 仅保留审计 Provider，不进入默认依赖或默认生产路径 |

Baostock 无需 API Key。官方资料声明日 K 在交易日收盘后更新，但生产判断仍以每次返回的
`as_of` 和时效检查为准，不依赖固定更新时间承诺。

efinance 依赖东方财富公开网页接口，没有可依赖的 SLA。本次许可声明存在冲突，且行情
接口稳定性未通过代表性审计；明确许可和稳定性问题解决前不得升级为默认依赖。

## 2. 已审计接口

### Baostock

接口：

```text
baostock.query_history_k_data_plus(
  code,
  fields,
  start_date,
  end_date,
  frequency="d",
  adjustflag="3"
)
```

当前只规范化以下字段：

```text
date, code, close, volume, amount, adjustment, trade_status
```

`adjustflag="3"` 对应不复权。指数必须传显式市场前缀，已审计映射为：

```text
沪深300  -> sh.000300
中证500  -> sh.000905
创业板50 -> sz.399673
```

### efinance

已审计：

```text
efinance.stock.get_quote_history(
  stock_codes,
  beg,
  end,
  klt=101,
  fqt=0,
  use_id_cache=False
)

efinance.fund.get_quote_history(
  fund_code,
  pz
)
```

股票/ETF 规范化为不复权日线；基金只读取 `日期`、`单位净值`、`累计净值`。单位净值与
累计净值不得混比，估算净值也不得替代已确认净值。

### 东方财富与同花顺 ETF 单位净值

`etf_dashboard` 同时按精确基金代码读取：

```text
fund_etf_fund_daily_em()  -> 东方财富动态日期单位净值列
fund_etf_spot_ths(date="") -> 同花顺最新交易日、最新单位净值
```

只在日期一致时比较单位净值；相对容忍度和绝对容忍度均为 `0.0001`。该校验独立于
Baostock，即使价格校验源暂时不可用，也能保留第二条多上游证据链。

## 3. 真实调用结果

Baostock 最近审计窗口：`2026-08-02` 至 `2026-09-01`，最新有效交易日为
`2026-08-31`。efinance 结果沿用 `2026-08-17` 的一次性审计，未作为当前生产健康证明。

| 数据源 | 类别 | 代表标的 | 结果 |
| --- | --- | --- | --- |
| Baostock | A 股 | `600519`、`000001`、`300750` | `3/3` 通过，最新 `2026-08-31` |
| Baostock | ETF | `510300`、`159915` | `2/2` 通过，最新 `2026-08-31` |
| Baostock | 指数 | 沪深 300、中证 500、创业板 50 | `3/3` 通过，最新 `2026-08-31` |
| efinance | A 股 | `600519`、`000001`、`300750` | `0/3`，上游主动断开连接 |
| efinance | ETF | `510300`、`159915` | `0/2`，上游主动断开连接 |
| efinance | 场外基金 | `000001`、`110022` | `2/2` 通过 |

代表性内容指纹：

| 标的 | `frame_sha256` |
| --- | --- |
| Baostock `600519` | `7a542864f2e3dd835ca8f39fdb7262a423bfed6396b6fb14531f51f8d9ad42b0` |
| Baostock ETF `510300` | `703323c2e90a2a7550e5c16a59c31957bd4aff55810f666d9f8ad74bad1ba925` |
| Baostock 沪深 300 | `e4c04e107d482572e97ef4fe27e26981e7094e4348ed73c3ba70b71d9de31e27` |
| efinance 基金 `000001` | `0b1c0c61e3f8d090aa0d227548656ae1a18535c5ac58e6915d7625a253bde4eb` |

这些结果只代表本次运行。上游失败记录为 `SOURCE_UNAVAILABLE`，不能解释为标的不存在、
停牌、无行情或净值为零。

## 4. 生产接入

`stock_valuation` 的 A 股收盘价和 `etf_dashboard` 的 ETF 收盘价使用相同的只读价格
校验策略；ETF 另有东方财富与同花顺单位净值校验：

1. 主图继续使用 AKShare `stock_zh_a_daily(adjust="qfq")` 前复权价格。
2. ETF 主图继续使用东方财富前复权日线；失败时才回退新浪未复权日线。
3. 交叉校验另取 AKShare 新浪未复权日线与 Baostock/efinance 的不复权日线。
4. 日期按内连接比较，不插值、不前向填充。
5. 相对容忍度为 `0.001`，绝对容忍度为 `0.01`；任一容忍范围内均视为一致。
6. 超阈值差异只产生 `SOURCE_DISAGREE`，主图和主源事实保持不变。
7. ETF 单位净值按精确代码和同一日期比较，结果不参与价格、收益或回撤计算。

审计角色固定为：

```text
cross_validation_primary
cross_validation_source
cross_validation_comparison
```

校验 Provider 在独立 `spawn` 子进程中运行。校验总等待预算默认不超过 10 秒，并且不超过
工具超时的三分之一；多个 Provider 平分该预算。超时进程会被终止，只产生
`SOURCE_UNAVAILABLE` warning。

启用方式：

```bash
export AKSHARE_FUND_SOURCE_VALIDATION=baostock
export AKSHARE_FUND_SOURCE_VALIDATION_TIMEOUT=10
```

独立 Skill 默认不设置 `AKSHARE_FUND_SOURCE_VALIDATION`，因此不会增加外部校验调用。
仓库 Compose 的 Data API 和 Fund MCP 默认显式启用 `baostock`，可通过同名环境变量覆盖。

## 5. 暂不接入

- efinance 股票和 ETF 行情本次全部失败，且许可声明冲突，不进入默认生产路径。
- efinance 基金净值虽通过审计，但尚未接入生产 Comparator。
- Baostock 指数仅完成接口与代码映射审计，尚未接入生产 Comparator。
- PE/PB 未完成跨源口径等价审计，不输出跨源数值差异。
- 收益、波动、回撤、历史分位和参考线继续只由 Skill 基于一条已审计主序列确定性计算。

## 6. 复现

默认依赖环境：

```bash
python scripts/audit_source_providers.py \
  --providers baostock \
  --days 30 \
  --timeout-seconds 10
```

efinance 需在一次性审计环境中显式安装 `efinance==0.5.9` 后运行：

```bash
python scripts/audit_source_providers.py \
  --providers efinance \
  --days 30 \
  --timeout-seconds 10
```

每次审计都重新记录版本、参数、列、起止日期、行数和 `frame_sha256`。历史指纹不得替代
当前请求的实时审计。
