# Trade / MP 命名契约

本契约自 `impact_label_schema_version=trade_mp_v1` 起生效，适用于 Stage 2
模型输出、双模型比较、仲裁、最终权重及其所有下游指数和诊断产物。
全局 `pipeline_schema_version` 继续保持 `3.0`，以免使既有 Stage 1
manifest 与门控失效。

## 1. 渠道标签

| 标签 | 含义 | 固定权重 `(trade, mp)` |
|---|---|---:|
| `trade` | 贸易渠道 | `(1.0, 0.0)` |
| `mp` | 跨国生产/投资渠道（multinational production / investment） | `(0.0, 1.0)` |
| `both` | 两个渠道均存在 | 两项严格大于 0 且合计为 1 |
| `none` | 两个渠道均不存在 | `(0.0, 0.0)` |

`trade_agreement_dummy` 保留原名，因为它表示贸易协定是否生效，不是
Stage 2 渠道分类。`raw_trade_score` 同样保留原名。回归数据中的
`equation="trade"` 表示 ICIO 贸易成本方程，`equation="mp"` 表示 AMNE
跨国生产成本方程。

## 2. 旧标签的一次性映射

旧版 Stage 2 标签必须同时映射，不得连续执行字符串替换：

```text
{"mp": "trade", "tr": "mp"}
```

映射仅用于已识别的类别字段或结构化 JSON 中的类别值，不适用于普通政策
术语、协定原文或自由文本。自由文本中的独立 `mp` / `tr` 标记进入人工复核
清单；只有明确的标签上下文可以自动改写。

## 3. 字段命名

主要字段按以下规则统一：

```text
*_investment_weight                   -> *_mp_weight
raw_investment_score                  -> raw_mp_score
effective_investment_weight           -> effective_mp_weight
human_final_investment_weight         -> human_final_mp_weight
both_investment_weight_abs_diff       -> both_mp_weight_abs_diff
*_investment_related_provisions_*     -> *_mp_related_provisions_*
investment_related_provision_coverage -> mp_related_provision_coverage
```

诊断字段必须一次性映射，避免名称碰撞：

```text
final_impact_type_mp_count -> final_impact_type_trade_count
final_impact_type_tr_count -> final_impact_type_mp_count
quality_mp_fixed_1_0       -> quality_trade_fixed_1_0
quality_tr_fixed_0_1       -> quality_mp_fixed_0_1
```

Stage 2 主模型 JSON 使用 `raw_trade_weight` 与 `raw_mp_weight`；规范化字段
使用 `normalized_trade_weight` 与 `normalized_mp_weight`；最终字段使用
`final_trade_weight` 与 `final_mp_weight`。

## 4. 版本与来源

- 新的 Stage 2 主提示词版本：`v4_zh_stage2_trade_mp`
- 新的 Stage 2 仲裁提示词版本：`v4_zh_stage2_type_trade_mp`
- 新生成记录必须保存 `prompt_sha256`。
- 新生成和迁移后的 Stage 2 及下游记录必须保存
  `impact_label_schema_version=trade_mp_v1`。
- 旧版模型记录保留原始 `prompt_version`，并另存
  `source_prompt_version` 与 `normalization_version=trade_mp_v1`；语义等价
  迁移不得将旧记录伪装成 v4 原生输出。

## 5. 验收不变量

- `trade` 行严格为 `(1.0, 0.0)`。
- `mp` 行严格为 `(0.0, 1.0)`。
- `both` 行两项均大于 0 且合计为 1。
- `none` 行严格为 `(0.0, 0.0)`。
- CSV 迁移保持主键、行数、行顺序和所有非命名字段值不变。
- `raw_mp_score` 与迁移前 `raw_investment_score` 逐行数值相等。
- `raw_trade_score` 不变。
