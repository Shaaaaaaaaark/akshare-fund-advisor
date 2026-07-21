# 指数历史估值图表

本功能参考 Wind 手机端“深度资料 → 指数估值 → 历史 PE/PB”的信息组织方式，但不复制其专有界面、品牌元素或受限数据。目标是还原决策所需信息：

- PE TTM 和 PB LF 历史曲线。
- 当前值、历史分位、均值、中位数、最高和最低。
- 3/5/10/20 年可用窗口的独立分位和中位数。
- 均值 ±1 标准差、20% 和 80% 分位参考线。
- 3/5/10/20 年观察区间。
- 实际数据来源、样本区间和最新日期。

## 命令

默认优先使用本机可用且已授权的 WindPy，否则回退 AKShare：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "沪深300" \
  --years 10 \
  --source auto
```

强制 Wind：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "000300.SH" \
  --years 10 \
  --source wind
```

强制 AKShare：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "沪深300" \
  --years 10 \
  --source akshare
```

默认每张图最多返回 600 个显示点。统计量始终使用完整日频数据。需要高密度导出时可设置：

```bash
--max-points 3000
```

## Wind Client API

WindPy 调用模板：

```python
from WindPy import w

w.start()
data = w.wsd(
    "000300.SH",
    "PE_TTM,PB_LF",
    "2016-01-01",
    "2026-01-01",
    "Period=D;Days=Trading",
)
```

字段：

| Wind 字段 | 含义 | 兼容字段 |
| --- | --- | --- |
| `PE_TTM` | 滚动市盈率 | AKShare `滚动市盈率` |
| `PB_LF` | 最新报告期市净率 | AKShare `市净率` |

WindPy 需要本机安装 Wind 终端、Python 插件、有效账号及对应数据权限。不得绕过授权、缓存后转发 Wind 受限数据或将 AKShare 数据标成 Wind。

判断来源：

- `actual_source.provider == "Wind"`：数据来自 Wind Client API。
- `actual_source.provider == "AKShare"`：只按 Wind 字段语义提供兼容视图。
- Wind 与 AKShare 对亏损成分、权重、异常值和历史回溯的处理可能不同，数值不保证逐点一致。
- 禁止使用 `Fill=Previous`、插值或模型补点；缺失值只能剔除并计入 `data_quality`。

专业解释顺序：

1. PE TTM 与 PB 分开解释，禁止计算综合分位。
2. 优先看 10 年或可用最长区间，再对照 3 年和 5 年，防止选择性取样。
3. 历史分位、中位数和 20%/80% 分位优先。
4. 均值和均值 ±1 标准差只作辅助，因为 PE/PB 分布通常不满足正态假设。
5. 金融、重资产和周期指数应提高 PB 的解释权重；成长指数不能只看 PB。

## 输出结构

```text
action: valuation
index
actual_source
lookback
summary
charts
  pe_ttm
    current / percentile / mean / median / standard_deviation
    minimum / maximum / quantiles / reference_lines
    window_statistics
    chart_series
  pb_lf
    ...
chart_spec
wind_api_reference
limitations
```

`chart_series` 每项为：

```json
["2026-07-16", 13.56]
```

`source_observations` 是完整日频统计样本数，`displayed_points` 是压缩后的图表点数。采样必须保留首点、末点、最高点和最低点。

`chart_spec.available_metrics` 和 `chart_spec.available_windows` 是本次响应实际可渲染的指标与窗口。UI 不得仅根据请求周期假设 3/5/10/20 年窗口都存在。

## 渲染规则

用户要求“图表、可视化、像 Wind 那样展示”时：

1. 执行 `valuation`。
2. 使用 `TRAE-dynamic-ui` 的 `PureShowWidget`，选择 `panel` 模式。
3. 图表只使用脚本返回的数字，不能补造中间点或修改分位。
4. 正文解释放在对话中，Widget 只放视觉内容。

Panel 布局：

```text
指数名称 + 区间 + 来源 + 最新日期
当前 PE | PE 分位 | 当前 PB | PB 分位
PE TTM 历史图
PB LF 历史图
统计表与口径说明
```

图表要求：

- PE 使用 sky 色，PB 使用 indigo 色。
- 当前点使用实心圆和数值标签。
- 均值/中位数用灰色虚线。
- `均值 +1σ`、80% 分位用 amber/coral；`均值 -1σ`、20% 分位用 mint。
- 两张图共享横轴区间，支持 tooltip、十字准星和 dataZoom。
- tooltip 至少显示日期、估值、历史分位口径说明。
- 不使用渐变背景，不使用 Wind 商标或声称是 Wind 原版界面。
- 末尾显示：数据源、日频样本数、实际起止日期和“历史分位不预测未来”。

渲染前必须分别判断 `charts.pe_ttm` 和 `charts.pb_lf` 是否为 `null`。若数据只有 PE 或 PB，只展示非空指标并明确缺失项，不访问缺失侧的 `chart_series`，也不用零值代替。
