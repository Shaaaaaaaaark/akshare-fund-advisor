# 指数历史估值图表

本功能使用 AKShare 指数估值接口组织专业的历史 PE/PB 信息：

- PE TTM 和 PB 历史曲线。
- 当前值、历史分位、均值、中位数、最高和最低。
- 3/5/10/20 年可用窗口的独立分位和中位数。
- 均值 ±1 标准差、20% 和 80% 分位参考线。
- 3/5/10/20 年观察区间。
- 实际数据来源、样本区间和最新日期。

## 命令

估值只使用 AKShare：

```bash
bash "$SKILL_DIR/scripts/run.sh" valuation \
  --index "沪深300" \
  --years 10
```

默认每张图最多返回 600 个显示点。统计量始终使用完整日频数据。需要高密度导出时可设置：

```bash
--max-points 3000
```

## AKShare 数据口径

调用：

```python
pe = ak.stock_index_pe_lg(symbol="沪深300")
pb = ak.stock_index_pb_lg(symbol="沪深300")
```

字段：

| 输出指标 | AKShare 字段 | 不采用的字段 |
| --- | --- | --- |
| `PE_TTM` | `滚动市盈率` | `静态市盈率`、`等权滚动市盈率` |
| `PB` | `市净率` | `等权市净率`、`市净率中位数` |

`actual_source.provider` 固定为 `AKShare`，并在 `interfaces` 和 `upstream` 中保留具体接口与上游。禁止前向填充、插值或模型补点；缺失值只能剔除并计入 `data_quality`。

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
  pb
    ...
chart_spec
limitations
```

`chart_series` 每项为：

```json
["2026-07-16", 13.56]
```

`source_observations` 是完整日频统计样本数，`displayed_points` 是压缩后的图表点数。采样必须保留首点、末点、最高点和最低点。

`chart_spec.available_metrics` 和 `chart_spec.available_windows` 是本次响应实际可渲染的指标与窗口。UI 不得仅根据请求周期假设 3/5/10/20 年窗口都存在。

## 渲染规则

用户要求“图表、可视化、专业终端式展示”时：

1. 执行 `valuation`。
2. 使用 `TRAE-dynamic-ui` 的 `PureShowWidget`，选择 `panel` 模式。
3. 图表只使用脚本返回的数字，不能补造中间点或修改分位。
4. 正文解释放在对话中，Widget 只放视觉内容。

Panel 布局：

```text
指数名称 + 区间 + 来源 + 最新日期
当前 PE | PE 分位 | 当前 PB | PB 分位
PE TTM 历史图
PB 历史图
统计表与口径说明
```

图表要求：

- PE 使用 sky 色，PB 使用 indigo 色。
- 当前点使用实心圆和数值标签。
- 均值/中位数用灰色虚线。
- `均值 +1σ`、80% 分位用 amber/coral；`均值 -1σ`、20% 分位用 mint。
- 两张图共享横轴区间，支持 tooltip、十字准星和 dataZoom。
- tooltip 至少显示日期、估值、历史分位口径说明。
- 不使用渐变背景，避免品牌化装饰干扰金融信息。
- 末尾显示：数据源、日频样本数、实际起止日期和“历史分位不预测未来”。

渲染前必须分别判断 `charts.pe_ttm` 和 `charts.pb` 是否为 `null`。若数据只有 PE 或 PB，只展示非空指标并明确缺失项，不访问缺失侧的 `chart_series`，也不用零值代替。
