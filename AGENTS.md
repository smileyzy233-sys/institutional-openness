# DTA 项目代码与匹配流程约束

本文件是项目级长期记忆，作用范围为整个仓库。后续新增、重命名、拆分或调用代码时，必须遵守以下规则。

## 1. 三段式主流程

项目代码必须明确归入以下三条主流程之一：

1. `measure_x`：测量解释变量 `raw_trade_score` 和 `raw_mp_score`。
2. `match_y_x`：将 ICIO/AMNE 被解释变量 Y 与 raw X 匹配。
3. `match_y_x_cons`：在已经完成的 Y-X 数据上匹配控制变量。

不得重新把数据读取、X 匹配、控制变量匹配、样本筛选、诊断和说明全部混入单一脚本。

## 2. 可执行步骤脚本命名

所有主流程中可直接执行的步骤脚本必须使用：

```text
<流程前缀>_<两位步骤号>_<动词_对象>.py
```

例如：

```text
measure_x_01_load_dta.py
match_y_x_03_prepare_x.py
match_y_x_cons_04_merge_trade_controls.py
```

具体要求：

- 流程前缀只能使用 `measure_x`、`match_y_x` 或 `match_y_x_cons`。
- 步骤号从 `01` 开始连续编号，只表示执行顺序。
- 文件名全部使用小写 `snake_case`。
- 文件名必须清楚表达单一职责，优先使用动词加对象。
- 不得在文件名中写死年份，例如不得使用 `*_2019.py`。
- 不得恢复 `tr`、`investment_score` 等含义不清或已弃用命名。
- `trade` 始终表示贸易方程或贸易渠道。
- `mp` 始终表示跨国生产/跨境投资方程或渠道。
- `raw_trade_score` 和 `raw_mp_score` 是稳定字段名，不得擅自改名。

## 3. 共享模块和其他文件

共享模块不编号，但必须保留所属流程前缀，例如：

```text
match_y_x_common.py
match_y_x_cons_common.py
```

测试文件使用：

```text
test_<模块或行为>.py
```

配置文件、审计工具、迁移工具和文档可以不使用步骤编号，但名称必须是清晰的小写 `snake_case`，不得冒充主流程步骤。

现有历史或辅助脚本不得未经明确决定擅自纳入编号主流程。

## 4. 年份和路径配置

- 主匹配代码中不得出现 `YEAR = 2019` 等硬编码年份。
- 年份必须通过命令行参数或 `configs/matching_specs.json` 传入。
- 新增年份原则上只增加年度数据文件和年份配置，不修改主匹配函数。
- 数据路径必须相对项目根目录配置，不得写入个人绝对路径。
- `--dry-run` 不得写文件。
- 未指定 `--force` 时不得覆盖已有输出。
- `result/regression_2019` 是只读 legacy 基准，不得覆盖。
- 所有重构结果写入新的 `result/model_inputs` 或明确指定的新目录。

## 5. 控制变量配置

- 控制变量集合必须由 `configs/matching_specs.json` 管理。
- 不得在主匹配函数中硬编码最终控制变量组合。
- 增加、删除或替换候选控制变量时，原则上只修改配置。
- `trade_candidate_pool_v1` 只代表已匹配候选变量，不代表最终变量选择。
- 以下变量在研究者明确决定前只能标记为候选：

```text
entry_cost_o / entry_cost_d
entry_proc_o / entry_proc_d
entry_time_o / entry_time_d
entry_tp_o / entry_tp_d
comlang_off
comrelig
cultural_distance_religion
```

- 不得把候选变量描述为已经进入最终回归。
- 不得生成暗含最终变量选择的 `sample_trade_main` 或 `sample_mp_main`。

## 6. Y-X 与控制变量边界

`match_y_x` 输出只能包含 Y、对应的 raw X、必要身份字段和诊断字段。

`match_y_x` 输出禁止包含：

```text
tariff
trade_agreement_dummy
idealpoint_abs_distance
entry_*
comlang_off
comrelig
cultural_distance_religion
sample_trade_main
sample_mp_main
```

`match_y_x_cons` 必须以 Y-X 输出为唯一基表，使用 left join，并验证每次合并前后行数完全一致。

MP 方程只自动匹配：

```text
trade_agreement_dummy
idealpoint_abs_distance
```

不得把关税或 Gravity 贸易候选字段自动加入 MP 方程。

## 7. 主键、ISO、ROW 和缺失值

标准 Y 主键：

```text
year + iso_o + iso_d + sector_amne
```

X、国家对控制变量和 Gravity 匹配键：

```text
year + iso_o_match + iso_d_match
```

关税匹配键：

```text
year + iso_o1 + iso_d1 + sector_amne
```

必须遵守：

- 原始 `iso_o`、`iso_d` 保持不变。
- `ROM -> ROU` 只能作用于 `iso_o_match`、`iso_d_match`。
- 按配置删除涉及 `ROW` 的观测。
- 国内流量必须保留，除非配置明确改变。
- 国内 `raw_trade_score`、`raw_mp_score` 和 `trade_agreement_dummy` 为结构性 0。
- 关税、政治距离、Gravity 字段和候选控制变量的缺失值不得填 0。
- ICIO 部门 20 的关税必须保持缺失。
- 不得因 X 或控制变量缺失自动删除 Y 行。

## 8. Gravity 读取规则

Gravity 大文件必须：

- 使用 `usecols`。
- 使用分块读取。
- 先筛选目标年份。
- 筛选 `country_exists_o == 1` 和 `country_exists_d == 1`。
- 只保留目标国家。
- 验证国家对—年份主键唯一。
- 不得一次读入全部字段。
- 不得对 `entry_*` 的来源国和目的国字段求平均。
- 不得插补缺失值。

`cultural_distance_religion = 1 - comrelig` 只能标记为派生候选变量。

## 9. 重命名和变更同步

重命名或移动脚本时，必须同步更新：

- 根目录 `run_pipeline.py` 的动态加载引用。
- `tests/conftest.py` 和所有测试中的 `load_script()`。
- README 和流程文档中的命令、路径及脚本名。
- 迁移脚本中的源文件白名单。
- 审计脚本中的旧路径引用。
- 其他明确出现旧脚本名的代码或文档。

不得修改 `migration_backups` 中的历史快照。

## 10. 验证要求

每次相关改动至少检查：

- 主键唯一性。
- Y-X 和控制变量合并不改变左表行数。
- raw scores 不被重新计算或修改。
- 国内 raw scores 和协议虚拟变量仍为 0。
- ROW 删除和国内流量保留符合配置。
- Y-X 输出不含控制变量。
- MP 输出不含贸易方程专属控制变量。
- 缺失值没有被错误填 0。
- CSV 与 DTA 行数和核心字段一致。
- 所有 Stata 字段名不超过 32 个字符。
- 新增年份和候选控制变量不要求修改主匹配代码。

完成代码修改后运行：

```bash
python -m compileall -q src tests
python -m pytest -q
```

## 11. 文档入口

详细流程和数据契约见：

```text
docs/pipeline_naming_and_data_contract.md
docs/matching_workflow.md
docs/trade_mp_naming_contract.md
```
