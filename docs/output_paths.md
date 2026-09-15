# 匹配数据输出与历史版本

## 当前数据链路

```text
DTA 原始数据、分类及权重
→ data/processed/ 中的得分与国家对数据
→ outputs/matched_data/match_y_x/                         Y–X 匹配
→ outputs/matched_data/match_y_x_cons/                    加入控制变量
→ Stata data/raw/io/gravity_resolved_fractional_20260914/  独立输入快照
→ Stata data/derived/io_trade_longdiff_data/ 和 io_mp_longdiff_data/
→ Stata OLS / PPML 估计与所属 exploration 的 output/
```

`outputs` 表示本项目的输出；`matched_data` 明确表示匹配数据，尚未等同于最终估计样本。国内流量、缺失值、候选控制变量等仍按既有匹配契约处理，由 Stata 的构建步骤形成估计样本。实际 CSV/DTA 文件名不变。

当前默认输出由 [matching_specs.json](../configs/matching_specs.json) 的 `output_root` 管理。新位置承接原 `result/model_inputs_fractional_20260914` 的全部内容；移动不会把历史输出变成一次新构建。已有 manifest 中的旧输入路径必须结合 [历史路径映射](../configs/historical_path_mappings.json) 读取，不能直接改写原始记录。

## 历史材料

原 `result/model_inputs`、`result/refactor_baseline` 和 `result/regression_2019` 已整组移至集中归档。它们保留版本比较与旧审计用途，未永久删除或去重。

[本次清单、验证及恢复](../../project_archive/organization_records/20260915_output_paths/report.md)

`docs/2000和2019匹配数据问题v1.md` 等历史审计说明中的 `result/model_inputs` 指向归档中的旧版本，不能据此读取当前数据或替换其原证据。

## 使用

从 DTA 项目根目录执行只读检查：

```powershell
python -B run_pipeline.py measure-x --dry-run
python -B run_pipeline.py match-y-x --years 2000 2019 --dry-run
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec trade_candidate_pool_v1 --dry-run
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec mp_controls_v1 --dry-run
```

仅在另行授权构建时移除 `--dry-run`；已有输出仍受不带 `--force` 不覆盖的规则保护。新实验版本可用 `--output-root outputs/<版本名>`，应成组保存数据、代码版本、日志及 manifest，不覆盖归档。
