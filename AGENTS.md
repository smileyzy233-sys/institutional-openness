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
docs/流水线命名与数据契约.md
docs/匹配流程.md
docs/贸易与跨国生产命名契约.md
```

## 12. 当前回归变量的真实来源与匹配方法

本节是供后续新窗口 agent 使用的项目级“当前事实清单”，最后核验日期为
`2026-07-29`。本节记录的是当前代码、配置和已生成诊断共同反映的真实流程，
不是早期设想或聊天记录。

必须区分两种“来源”：

1. **匹配阶段直接来源**：`match_y_x` 或 `match_y_x_cons` 实际读取的文件和字段。
2. **上游原始来源**：直接来源中的字段更早由哪些原始文件和脚本生成。

不得因为某字段的上游原始数据位于其他目录，就错误地声称回归匹配阶段绕过
中间文件、直接读取了该原始目录。

### 12.1 当前启用年份和有效研究规格

当前匹配配置启用：

```text
2000
2019
```

当前有效研究规格为：

```text
trade_candidate_pool_v1
mp_controls_v1
```

`legacy_2019_v1` 仅用于旧版 2019 结果的重构比较，不代表当前研究规格，
不得把其中的变量选择描述为当前最终选择。

当前代码只构造回归输入，不运行回归。

### 12.2 被解释变量 Y

贸易方程：

```text
直接文件：Explained_variable/icio{year}.dta
字段：value
当前年份：icio2000.dta、icio2019.dta
```

跨国生产（MP）方程：

```text
直接文件：Explained_variable/amne{year}.dta
字段：value
当前年份：amne2000.dta、amne2019.dta
```

Y 的标准粒度和主键为：

```text
year + iso_o + iso_d + sector_amne
```

`iso_o`、`iso_d`、`sector_amne` 和 `value` 来自相应的 ICIO/AMNE 文件。
当前 2000、2019 文件都已经包含 `country_o`、`country_d`、`iso_o1`、
`iso_d1`。如果未来年度缺少这些身份字段，代码才使用
`Explained_variable/iso_o.dta` 作为后备映射表补充；该后备映射不改变
`value`。

ROW 按配置删除，国内流量保留。不得因为 X 或控制变量缺失删除 Y 行。

### 12.3 核心解释变量 X

贸易方程核心解释变量：

```text
字段：raw_trade_score
匹配阶段直接文件：data/processed/trade_dummy_icio_2000_2023.csv
```

MP 方程核心解释变量：

```text
字段：raw_mp_score
匹配阶段直接文件：data/processed/trade_dummy_icio_2000_2023.csv
```

两者的匹配键均为：

```text
year + iso_o_match + iso_d_match
```

上游生成链路为：

```text
DTA 条款识别和权重
-> data/processed/agreement_level_indices.csv
-> src/measure_x_16_compute_country_pair_year_scores.py
-> data/processed/country_pair_year_indices.csv
-> src/14_build_trade_agreement_dummy.py
-> data/processed/trade_dummy_icio_2000_2023.csv
```

因此，回归匹配阶段直接读取的是
`trade_dummy_icio_2000_2023.csv`，而不是重新计算条款得分。

国内 `raw_trade_score` 和 `raw_mp_score` 是结构性 0。当前 2000、2019
均为 76×76＝5,776 个有向国家对，X 匹配率为 100%。

### 12.4 国家对控制变量

#### 协定虚拟变量

```text
变量：trade_agreement_dummy
匹配阶段直接文件：data/processed/trade_dummy_icio_2000_2023.csv
直接字段：trade_agreement_dummy
匹配键：year + iso_o_match + iso_d_match
```

上游由 `src/14_build_trade_agreement_dummy.py` 根据
`data/interim/bilateral_panel.csv` 中当年生效的 DTA 构造。存在生效协定为
1，无生效协定为 0，国内国家对为结构性 0。

#### 双边政治关系

```text
变量：idealpoint_abs_distance
匹配阶段直接文件：data/processed/trade_dummy_icio_2000_2023.csv
直接字段：idealpoint_abs_distance
匹配键：year + iso_o_match + iso_d_match
```

它的上游原始来源是：

```text
ideapoint/IdealpointestimatesAll_Jun2024.csv
ideapoint/AgreementScoresAll_Jun2024.csv
```

`src/14_build_trade_agreement_dummy.py` 先用第二个文件建立 UNGA
session—year 映射，再从第一个文件读取各国 `IdealPointAll`，计算：

```text
idealpoint_abs_distance = abs(idealpoint_o - idealpoint_d)
```

国内政治距离为结构性 0。国际国家对缺少任一国理想点时保持缺失，不得填 0。

必须准确描述为：

> 政治距离在匹配阶段来自 `trade_dummy_icio_2000_2023.csv`；
> 该 CSV 中的政治距离上游由 `ideapoint` 原始文件计算。

不得描述为 `match_y_x_cons` 直接去 `ideapoint` 目录重新匹配。

### 12.5 贸易方程控制变量

当前 `trade_candidate_pool_v1` 中已经确认的基础控制变量只有：

```text
tariff
trade_agreement_dummy
idealpoint_abs_distance
```

#### 关税

直接来源按年份配置：

```text
2000：control__variable/tariff2000.dta
2019：control__variable/tariff_2019.csv
字段：tariff
```

匹配键为：

```text
year + iso_o1 + iso_d1 + sector_amne
```

2000 源文件的国家字段是 ISO3 字符串，代码通过
`Explained_variable/iso_o.dta` 转为与 Y 一致的数字国家代码；
2019 文件已经使用数字国家代码。两年关税均覆盖部门 1–19，部门 20
结构性缺失，因此贸易数据中关税缺失率为 5%。不得把部门 20 关税填 0。

#### Gravity 贸易便利化和文化候选变量

直接来源：

```text
control__variable/Gravity_V202211.csv
```

匹配键：

```text
year + iso_o_match + iso_d_match
```

读取和筛选规则：

```text
先筛选目标年份
country_exists_o == 1
country_exists_d == 1
只保留目标 76 个经济体
验证每年 76×76 有向国家对唯一
```

当前匹配但尚未最终选择的候选变量为：

```text
entry_cost_o / entry_cost_d
entry_proc_o / entry_proc_d
entry_time_o / entry_time_d
entry_tp_o / entry_tp_d
comlang_off
comrelig
cultural_distance_religion = 1 - comrelig
```

这些字段虽然出现在 `trade_y_x_cons_{year}` 中，但不等于已经进入最终回归。
特别是，当前尚未选定一个最终的“贸易便利化”主控制变量。

不得对来源国和目的国的 `entry_*` 求平均，不得插补缺失值。

### 12.6 MP 方程控制变量

当前 `mp_controls_v1` 只匹配并选择：

```text
trade_agreement_dummy
idealpoint_abs_distance
```

两者的直接来源和上游来源见 12.4，匹配键为：

```text
year + iso_o_match + iso_d_match
```

MP 方程不自动加入：

```text
tariff
任何 entry_*
comlang_off
comrelig
cultural_distance_religion
```

### 12.7 ISO、方向、合并和输出

原始 `iso_o`、`iso_d` 始终保留。`ROM -> ROU` 只作用于：

```text
iso_o_match
iso_d_match
```

所有匹配均以 Y 或 Y-X 为左表，使用 left join 和 many-to-one 验证；
每次合并前后行数必须完全一致。国家对字段保持有向匹配，不得擅自交换
来源国和目的国。

控制变量自由的 Y-X 输出：

```text
result/model_inputs/match_y_x/{year}/
```

贸易控制变量输出：

```text
result/model_inputs/match_y_x_cons/trade_candidate_pool_v1/{year}/
```

MP 控制变量输出：

```text
result/model_inputs/match_y_x_cons/mp_controls_v1/{year}/
```

声明某个现有输出与当前输入一致前，必须比较 `build_manifest.json` 中的
输入 SHA256 与当前源文件。若源文件后更新但相关字段经逐列核验没有变化，
应说明“统计字段一致但构建清单已过期”，不得笼统称为完全可复现。

### 12.8 当前已知的年度覆盖和缺失

以下是原始数据覆盖造成的已知缺失，不是合并主键失败：

```text
2000 idealpoint_abs_distance：
  缺少 CHE、HKG、TWN 的理想点；
  444 个国家对缺失；
  贸易和 MP 各 8,880 个部门行缺失，缺失率约 7.69%。

2019 idealpoint_abs_distance：
  缺少 HKG、TWN 的理想点；
  298 个国家对缺失；
  贸易 5,960 行、MP 12,218 行缺失，缺失率约 5.16%。

2000 entry_*：
  全部缺失；Gravity 中这些字段的目标样本覆盖从 2003 年开始。
  若 entry_* 只是候选变量，可以保留缺失；
  若未来决定把它作为正式贸易便利化控制变量，2000 年不能继续按当前规格估计，
  必须更换指标、调整年份或取得新的数据来源，且必须同步更新本节。

2019 entry_*：
  每个来源国字段在 TWN 为来源国时缺失；
  每个目的国字段在 TWN 为目的国时缺失；
  单列缺失 1,520 个贸易部门行，约 1.32%。

2000 和 2019 comrelig / cultural_distance_religion：
  涉及 LTU 的 151 个国家对缺失；
  对应 3,020 个贸易部门行，约 2.61%。

2000 和 2019 comlang_off：
  当前目标样本无缺失。

2000 和 2019 tariff：
  部门 20 的 5,776 行结构性缺失，缺失率 5%。
```

这些缺失不得填 0。使用完整案例回归时必须说明由此排除的国家、国家对或部门。

### 12.9 零流量与估计口径

`value == 0` 是真实零流量，不是匹配错误：

```text
2000 贸易：11,487 / 115,520，约 9.94%
2000 MP：72,014 / 115,520，约 62.34%
2019 贸易：6,175 / 115,520，约 5.35%
2019 MP：145,474 / 236,816，约 61.43%
```

不得为了取对数而在匹配阶段删除这些行。直接使用 `ln(value)` 会系统性丢失
零流量，尤其会删除六成以上 MP 观察。当前建议以原始 `value` 使用 PPML；
只保留正值的对数 OLS 只能作为另行说明的稳健性检验。

## 13. 变量变更时强制同步 AGENTS.md

本节是后续 agent 的强制维护规则。只要任务涉及下列任一变化，执行修改的
agent 必须在同一任务中同步更新本文件第 12 节，不能只修改代码、配置、
README、数据或输出：

```text
增加、删除或重命名被解释变量、核心解释变量或控制变量
把变量从 candidate 改为 selected，或从 selected 改为 candidate
改变变量的直接来源文件、字段名或上游原始来源
改变计算公式、变换、单位、方向性或缺失值处理
改变匹配键、ISO 映射、ROW/国内流量政策
改变年份范围或某年份使用的源文件
新增、删除或改变 sample / available / match 标志
改变贸易方程和 MP 方程各自允许的变量集合
```

每次相关变更至少同步检查和更新：

```text
configs/matching_specs.json
对应的 src/match_y_x_* 或 src/match_y_x_cons_* 代码
相关 tests
docs/匹配流程.md 等流程文档
AGENTS.md 第 12 节的当前事实清单和最后核验日期
新输出的 build_manifest.json、matching_diagnostics 和变量字典
```

如果用户只授权改代码而未授权覆盖现有输出，仍必须更新代码、配置和
`AGENTS.md`，并明确指出哪些已有 manifest/diagnostics 已因源文件或规则变化
而过期。

后续 agent 开始变量匹配或回归数据任务时，应先读取本文件、当前
`configs/matching_specs.json`、相关代码和最新构建清单。若四者不一致：

1. 不得让用户重新完整解释历史流程作为默认解决办法。
2. 先根据当前代码、配置、源文件和输出哈希查明实际执行路径。
3. 向用户指出冲突及其影响。
4. 按用户确认或可客观判定的当前事实修正代码/配置/文档。
5. 在结束任务前更新本文件，使更后面的窗口获得新的真实流程。

不得把聊天记忆、旧版 `result/regression_2019`、候选变量名称或过期 README
当作高于当前可执行代码和配置的事实来源。研究者尚未作出的最终变量选择必须
明确标记为“候选/待决定”，不得由 agent 擅自替用户决定。
