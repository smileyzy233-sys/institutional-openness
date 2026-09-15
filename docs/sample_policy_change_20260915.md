# DTA—Stata 样本规则变更（2026-09-15）

## 状态和范围

本次只修改代码、配置、测试和文档。没有调用 LLM、重新计算指标、生成真实匹配数据、
更新 Stata 快照、构建真实派生数据、运行回归或提交 Git。

**`outputs/matched_data` 仍是 `drop_row: true, keep_domestic: true` 的旧匹配产品。**
Stata 仍直接读取自身 `data/raw/io/gravity_resolved_fractional_20260914/` 下的四份
独立 DTA 快照，不会自动读取 DTA 项目新输出。其已有派生数据、日志和结果也未刷新。
旧 Stata 构建本来就排除 ROW 和本国对；本次补充规范化、日志和断言，不改变估计规格。
不得把现有文件描述为新默认配置的一次运行成果。

## 改动与依据

|位置|改动|
|---|---|
|`configs/matching_specs.json`|复用 `keep_domestic`，默认改为 `false`；`drop_row` 仍为 `true`。将旧行数门槛明确命名为 `*_rows_excluding_row`，基准数值不变。|
|`src/match_y_x_common.py`|集中解析两项布尔开关、构造规范化比较掩码、按并集筛选并生成审计。|
|`src/match_y_x_02_prepare_y.py`|在现有 Y 准备位置筛选，保持原始 ISO、数值和身份字段；核对源行数与排除 ROW 后的基准行数。|
|`src/match_y_x_06_validate_export.py`|合并后行数必须等于已筛选 Y；新诊断和 manifest 保存实际筛选记录，`input_rows` 记录筛选前源行数。|
|`src/match_y_x_cons_common.py`、`src/match_y_x_cons_07_validate_export.py`|读取和 dry-run 预检核对 Y-X manifest 的样本规则、年份、ISO 别名和 CSV SHA256。冲突或证据缺失就提示重新构建，`--force` 不绕过；真实读取进一步检查实际行数和残留观测。新控制变量 manifest 引用并记录 Y-X manifest 哈希。|
|Stata Trade、MP 的 `01_build_*_long_difference_data.do`|在生成 OLS/PPML 数据之前检查 ROW/本国对，规范化只作用于临时字段；记录交集和实际删除总数，无命中时记录“检查通过，无需删除”；筛选后断言两类均为零。|
|两项目 README、AGENTS 与匹配契约|同步默认值、显式保留方法、Stata 兜底职责以及旧输出状态。|
|合成测试|验证开关、空白/大小写、缺失 ISO、重叠计数、重复筛选、行数约束和旧数据拒绝复用。|

筛选前的 ROW 数与本国对数可能重叠，例如 `ROW → ROW`。实际删除总数按满足
当前开关的并集计算，不能把两类原始计数直接相加。空值/缺失值不判成本国对；
这不取消其他阶段原有的身份字段、主键或 X 完整性校验。

只有 DTA 匹配产品需要保留本国对时，将配置改成：

```json
"row_policy": {"drop_row": true, "keep_domestic": true}
```

保留本国对不会改变 Stata 国际实证样本：Stata 仍会检查并删除本国对和 ROW。
切换配置后，应使用独立输出版本；不能通过修改旧 manifest 来“修复”配置冲突。
历史 `legacy_2019_v1` 的重构比较依赖原样本，应显式恢复原有样本配置并使用单独目录，
不能把新国际样本当作旧基准进行逐行比较。

## 后续重建步骤（本次没有执行）

以下只重建匹配与实证数据，不调用 LLM、不重算已有 X，也不运行回归。
新目录示例在本次检查时均不存在；以后执行前仍须确认未被占用。

### 1. 从现有 X 重建 Y-X 和控制变量

确认 `configs/matching_specs.json` 中 `drop_row: true, keep_domestic: false`。
在 PowerShell 执行：

```powershell
Set-Location -LiteralPath 'A:\桌面\制度性开放\dta_institutional_opening'
python -B run_pipeline.py match-y-x --years 2000 2019 --output-root outputs/matched_data_international_v1 --dry-run
python -B run_pipeline.py match-y-x --years 2000 2019 --output-root outputs/matched_data_international_v1
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec trade_candidate_pool_v1 --output-root outputs/matched_data_international_v1 --dry-run
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec trade_candidate_pool_v1 --output-root outputs/matched_data_international_v1
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec mp_controls_v1 --output-root outputs/matched_data_international_v1 --dry-run
python -B run_pipeline.py match-y-x-cons --years 2000 2019 --control-spec mp_controls_v1 --output-root outputs/matched_data_international_v1
```

按顺序执行：新目录在 Y-X 构建前没有基表，不能提前通过控制变量 dry-run。
不添加 `--force`；已有目标说明该版本名已经使用，应另取新版本名。
验收两年 Y-X manifest 的 `row_policy_audit`：实际配置正确、前后行数相符、
筛选后 ROW/本国对均为零、CSV/DTA 核心字段一致；控制变量诊断每个 left join
前后行数相同。核对现有 X 和权重哈希未变。

### 2. 新建 Stata 原始输入快照并核对

将以下四个文件复制到新的独立目录，保留文件名：

|DTA 项目内的新源文件|Stata 项目内的新目标|
|---|---|
|`outputs/matched_data_international_v1/match_y_x_cons/trade_candidate_pool_v1/2000/trade_y_x_cons_2000.dta`|`data/raw/io/gravity_resolved_international_v1/trade_y_x_cons_2000.dta`|
|`outputs/matched_data_international_v1/match_y_x_cons/trade_candidate_pool_v1/2019/trade_y_x_cons_2019.dta`|`data/raw/io/gravity_resolved_international_v1/trade_y_x_cons_2019.dta`|
|`outputs/matched_data_international_v1/match_y_x_cons/mp_controls_v1/2000/mp_y_x_cons_2000.dta`|`data/raw/io/gravity_resolved_international_v1/mp_y_x_cons_2000.dta`|
|`outputs/matched_data_international_v1/match_y_x_cons/mp_controls_v1/2019/mp_y_x_cons_2019.dta`|`data/raw/io/gravity_resolved_international_v1/mp_y_x_cons_2019.dta`|

每份复制完成后用 `Get-FileHash -Algorithm SHA256 -LiteralPath '<精确文件路径>'`
比较源、目标，核对四个文件的数量和大小。不要移动或覆盖旧
`gravity_resolved_fractional_20260914` 快照，也不要建立跨项目软链接代替独立输入。
新快照另建来源清单，记录四组源→目标、SHA256、当前配置，并按
`provenance/<control_spec>/<year>/` 保存对应新构建 manifest 与诊断，避免同名覆盖；
来源清单同时引用该次 Y-X 审计。不改写复制过来的原 manifest。

### 3. 指向新快照，保存旧派生运行，再构建 Stata 数据

仅在四份新快照验收通过后，更新以下两份脚本的 `Inputs` 注释、`use` 和
`append using` 中的目录，由 `gravity_resolved_fractional_20260914` 改成
`gravity_resolved_international_v1`，同步对应 README：

- `explorations/io_trade_longdiff_data/dofiles/01_build_trade_long_difference_data.do`
- `explorations/io_mp_longdiff_data/dofiles/01_build_mp_long_difference_data.do`

这两份脚本有 `save, replace`、日志及表格覆盖操作。执行前，将各自完整探索目录
（代码、日志、output）、`data/derived/io_trade_longdiff_data/`、
`data/derived/io_mp_longdiff_data/` 及旧来源说明复制到
`A:\桌面\制度性开放\project_archive\stata_institutional_opening\historical_runs\<新版本前的备份版本>\`，
逐文件核对数量、大小和 SHA256，保留原路径映射。正式回归结果保持原状，但标注
它们对应旧派生输入；此时不得将它们当作新输入已重新估计的结果。

在 Stata 命令窗口从项目根目录依次执行：

```stata
cd "A:/桌面/制度性开放/stata_institutional_opening"
do "explorations/io_trade_longdiff_data/dofiles/01_build_trade_long_difference_data.do"
do "explorations/io_mp_longdiff_data/dofiles/01_build_mp_long_difference_data.do"
```

验收日志：读取来源与新快照一致，ROW/本国对前计数与实际删除总数明确；
若新 DTA 输入已经排除它们，应显示无需删除，实际删除为零；筛选后断言和主键检查通过。
保留新日志和派生文件哈希。新版本验收后可将 DTA `output_root` 配置更新到
`outputs/matched_data_international_v1`，再同步项目入口文档；旧输出继续保留或成组归档。

### 4. 下游实证读取链路（仅说明，本次不运行）

|实证入口|直接读取的派生文件|
|---|---|
|`explorations/new_d_ln_ols_longdiff/dofiles/01_estimate_longdiff_ols.do`|`data/derived/io_trade_longdiff_data/trade_longdiff_ols.dta` 与 `data/derived/io_mp_longdiff_data/mp_longdiff_ols.dta`|
|`explorations/new_ppml/dofiles/01_estimate_ppml.do`|`data/derived/io_trade_longdiff_data/trade_twoperiod_ppml.dta` 与 `data/derived/io_mp_longdiff_data/mp_twoperiod_ppml.dta`|

上述 OLS/PPML 入口不直接读取 DTA 项目 `outputs`。本次未修改其估计规格。

## 验证、完整清单与恢复

本次验收结果：

- Python 编译检查通过；DTA 测试 **146 passed、3 skipped**。跳过的是缺少旧版制品的历史集成测试。
- 合成测试覆盖默认删除、显式保留、ROW 独立开关、大小写/空白、双端缺失、交集去重、幂等、配置缺省/非法值、基准行数门槛以及 left join 的未匹配行保留和重复右键拒绝。
- DTA Y-X 默认及新版本目录的 dry-run 通过；两个控制变量规格对旧配置基表的 dry-run 均按预期拒绝，包含 `--force` 情形。明确恢复旧开关的只读检查仍能读取四份旧 Y-X 基表。
- 验证驱动禁止网络、子进程和项目写入；合成数据仅写到归档内测试临时区，dry-run 阶段禁止任何文件写入。
- Stata 两份实际脚本静态检查通过，质量评分均 **100/100**；关联实际筛选代码的 Python 合成语义测试通过。当前环境未找到可用 Stata 程序，**未执行 Stata 语法运行、真实构建或回归**。
- 修改前清单的 **1,164 个文件（4,609,612,752 字节）**均已核对；17 个授权代码/配置/文档修改、2 个新增测试/文档，其余 **1,147 个文件 SHA256 未变**。没有意外改动或丢失文件；现有数据、权重、结果、日志和 manifest 内容未变。

验证结果及完整文件变更清单集中保存于
`../../project_archive/organization_records/20260915_sample_policy/`。
`inventory_before.json` 保存两项目修改前清单与 SHA256，`originals/<project>/`
保存本次修改前代码/配置/文档副本，保留此前已有的修改与未跟踪内容。
恢复时依据 `changes.json` 仅恢复本次改动文件；先备份之后的新改动，再从
`originals/<project>/<原相对路径>` 复制回原位置并核对基线哈希。
本次新增文件若需撤回，可移入该次归档的待清理区；不使用 Git reset/clean。
本次没有移动、重命名、删除或去重数据文件，释放空间为 0。
