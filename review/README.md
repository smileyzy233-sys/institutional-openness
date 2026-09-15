# 编码后 DTA 2.0 至实证起点数据：复核指南

本次交付修正此前使用编码前 DTA 2.0 进行聚合的问题。当前测算入口明确读取
`data/raw/DTA 2.0 - Vertical Content (v2)_code.xlsx`，保留编码后的部分覆盖值。
本指南对应 2026-09-15 的代码和只读核验；数据文件保留其实际生成时间。

本次重新比较两份工作簿：1,071 条条款 × 400 个协定中，旧“原始数值等于 1 才计 1”
规则与编码后覆盖矩阵有 **4,097 个单元格不同**；编码后有 **1,970 个部分覆盖值**，
**39,284 个空白值**按已确认口径计 0。详见
[覆盖差异摘要](evidence/coverage_correction.json)。这是对覆盖值的只读比较，
没有据此重新生成旧版数据或估计回归。

## 1. 本次修正和已确认口径

- 协定—条款覆盖值属于 `[0,1]`，部分覆盖值直接参与计算，不能再按“等于 1”压成二元覆盖。
- 空白覆盖值按 0 计入，是研究者与老师商定的口径。该规则不适用于控制变量缺失。
- 复用既有制度型开放识别、四维度分类与 Trade/MP 权重；本次发布没有重新调用 LLM。
- 协定得分为覆盖值乘有效权重后求和；多个生效协定逐条款取最大覆盖程度，再加权求和。
  四维度分类不另加等权或层级权重。
- 2019 年 Trade 在 CSV 转 DTA 环节有已接受的微小浮点保存差异，零值/正值分类不变。
  不把“已接受”表述为原始 Y 逐位完全相同，亦未据此重新评估回归系数。

具体公式见 [DTA测算方法.docx](../docs/DTA测算方法.docx)，口径确认见
[测算决策记录](../docs/measurement_decisions_20260915.md)，最新图示见
[流程图.pptx](../docs/流程图.pptx)。仓库历史 PDF 和旧提交用于追溯，不代表当前方法版本。

## 2. 顺着文件核对整个链路

以下路径以 DTA 项目根目录为起点；Stata 路径以并列的 Stata 项目根目录为起点。

|环节|直接输入 → 输出|主要实现与核对点|
|---|---|---|
|编码覆盖|编码后工作簿 → `data/interim/agreement_matrix.csv`、条款主表、协定主表、生效面板|`src/measure_x_01_load_dta.py`；条款 ID 对齐、部分覆盖、空白计 0|
|分类与权重|条款主表、既有分类 → `data/processed/final_provision_weights.csv`|`prompts/`、`measure_x_02` 至 `measure_x_14`；本次只核验复用，没有重新分类|
|协定得分|覆盖矩阵、有效权重 → `agreement_level_indices.csv`|`src/measure_x_15_compute_agreement_scores.py`；逐项加权|
|国家对—年份|生效协定、覆盖矩阵、有效权重 → `country_pair_year_indices.csv`|`src/measure_x_16_compute_country_pair_year_scores.py`；多协定按条款取最大值|
|辅助变量|国家对得分、生效协定、ICIO 国家覆盖、政治距离源表 → `trade_dummy_icio_2000_2023.csv`|`src/14_build_trade_agreement_dummy.py`；这是匹配步骤直接读取的 X 和辅助变量来源|
|Y–X|`Explained_variable/icio{year}.dta` / `amne{year}.dta`，上述国家对表 → `outputs/matched_data/match_y_x/`|`src/match_y_x_01_…` 至 `06_…`；Y 为左表，国家对—年份匹配|
|控制变量|Y–X、关税和 Gravity → `outputs/matched_data/match_y_x_cons/`|`src/match_y_x_cons_01_…` 至 `07_…`；键唯一，匹配前后行数一致，缺失不填 0|
|Stata 起点|四份匹配 DTA → Stata `data/raw/io/gravity_resolved_fractional_20260914/` 独立快照 → `data/derived/` 两份 OLS 宽表及两份 PPML 两期长表|[两份构建脚本](stata_build/README.md)；快照 SHA256 一致，排除 ROW 和本国对，Trade 部门 1—19、MP 部门 1—20|

2000 年原始 Y 只有 `iso_o`、`iso_d`、`sector_amne`、`value`，身份字段由
`Explained_variable/iso_o.dta` 后备映射；2019 年原始文件自带身份字段。
原始 ISO 保留，`ROM→ROU` 仅用于匹配桥接。Trade 的 49 个 Gravity 字段是候选池，
当前 Stata 起点构建将其全部排除，不能理解为已选入回归。详细字段与键见
[匹配流程](../docs/匹配流程.md)和[数据契约](../docs/流水线命名与数据契约.md)。

## 3. 现存数据与新代码状态须分开

|对象|实际状态|
|---|---|
|现存 fractional 匹配数据和 Stata 快照|已使用修正后的覆盖值；匹配层 `drop_row=true, keep_domestic=true`|
|现存 Stata 派生数据|已排除 ROW 与本国对；属于既有构建，不能描述为本次发布重新生成|
|2026-09-15 新默认配置|`drop_row=true, keep_domestic=false`；尚未按新默认规则重建真实数据|
|历史 Stage 1 manifest 与权重来源记录|保留原文；兼容性另由 `measurement_compatibility_20260915.json` 记录，不冒充重新运行|
|本次发布操作|代码、文档、合成测试、只读数值核验及打包；没有运行 LLM、生成真实指标/匹配数据或运行 OLS/PPML|

所以，新默认配置对现存 Y–X 运行控制变量预检时会拒绝复用，这属于预期保护。
不要通过改写旧 manifest 或 `--force` 消除差异。需要新样本版本时，按
[后续重建步骤](../docs/sample_policy_change_20260915.md)生成独立目录。

## 4. 公开仓库和配套数据包

公开仓库提供完整测算/匹配代码、配置、编码提示词、方法文档、合成测试、
Stata 起点构建脚本副本、只读核验工具，以及不含逐条观测的审计摘要和文件哈希。
公开证据位于 [evidence/](evidence/)；`data_inventory.json` 是配套数据的精确文件清单。

完整工作簿、人工分类与权重、上游 Y/控制变量、中间表、匹配结果、Stata 快照和派生
数据通过本地配套 ZIP 单独交付。仓库不公开这些数据，也不包含 `.env`、API 密钥、
模型原始请求日志或无关历史归档。**仅下载 GitHub 代码可以检查方法及运行合成测试，
逐值核验还需要配套数据包。** 本地包不是 GitHub Release 附件，须由研究者单独提供。

## 5. 老师可执行的只读复核

将数据包解压到一个新目录。包内 DTA 和 Stata 两项目目录并列。
在 DTA 根目录执行（Python 3.10 或以上）：

```powershell
python -m pip install -r requirements-dev.txt
python -B -m pytest -q
python -B scripts/verify_review_bundle.py --data-root . --stata-root ../stata_institutional_opening
```

最后一条只读取现有文件、计算对照量并向终端输出 JSON；不调用模型、不覆盖数据、
不启动 Stata 或回归。若需要另存结果，加 `--report <尚不存在的新文件.json>`。
与 [本次只读核验](evidence/audit_20260915.json) 对照；时间戳可不同，关键哈希及检查结论应一致。

核验覆盖编码值—矩阵、权重对齐、协定得分、已记录协定集合上的国家对得分、匹配 X、
manifest 输入哈希、Stata 快照与派生变量。它不独立判定人工编码/分类的研究合理性，
不代替生效协定范围的法律文本复核，不逐值重建全部 Gravity 控制，也不验证回归识别。
数据清单用于查验版本，不能把文件存在或哈希一致等同于所有研究判断均正确。

需要追溯某次历史运行时，使用 [历史路径映射](../configs/historical_path_mappings.json)。
本次配套包只含当前复核所需材料，不包含整个历史归档；历史路径可能因此无法打开。
