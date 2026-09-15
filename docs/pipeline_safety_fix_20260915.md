# 流程入口保护修复记录

## 结论与范围

修复只涉及执行保护和输入对应检查。三段研究流程、模型提示词、条款规则、得分公式、匹配配置及现有数据均未改变。没有调用 LLM、重算研究数据、运行回归、提交或发布 Git。

## 四项修复

|原问题|修复后的行为|
|---|---|
|部分命令忽略 `--dry-run`|根入口所有命令及 19 个测算/辅助步骤支持检查模式；在调用模型、计算、目录创建和写入前返回。|
|已有成果可能被直接覆盖|共享预检先检查整条命令的目标文件，存在旧文件且未指定 `--force` 时停止；直接调用步骤也受保护。|
|导入包装器会自动启动流程|只有显式执行 `main()` 或作为脚本运行时才转发；普通导入不启动流程。|
|未充分检查输入和权重对应关系|核对主表与分类清单、分类与权重、协定指标与其输入/配置；不匹配时停止。|

`--force` 只允许覆盖；默认仍复用有效缓存。重新调用模型需要明确选择 `--no-resume`，它本身不授权覆盖。六个模型/仲裁步骤不再提前删除旧结果文件。Stage 2 发现过期输入时只报错，不再改写该输入文件添加标记。

主要实现：根 `run_pipeline.py`、`src/pipeline_safety.py`、`src/run_pipeline.py`、`src/utils.py`；各测算脚本只接入共享入口保护，测算第 15/16 步另加入版本检查与独立来源记录。使用方法见 [README](../README.md)，长期规则已补入项目 [AGENTS.md](../AGENTS.md)。

## 当前历史文件的精确兼容

旧主表的换行差异继续使用原有 `manifests/measurement_compatibility_20260915.json`，原记录未修改。

加强检查发现：权重 CSV 内嵌的旧分类哈希与当前分类文件哈希不同。按 `provision_id` 逐列核验 1,071 行、26 个保留的分类字段；仅将条款文本 CRLF 规范为 LF 后比较，差异为 0。没有修改 CSV 中的旧哈希。新增：

- [final_provision_weights.provenance.json](../data/processed/final_provision_weights.provenance.json)：精确绑定当前权重、主表、分类和清单，保留内嵌旧哈希及逐列核验结果。
- [agreement_level_indices.provenance.json](../data/processed/agreement_level_indices.provenance.json)：冻结本次核验的现有协定指标和输入组合。

上述两份记录明确标注为只读基线，`pipeline_executed=false`；不能当作重新生成数据的证据。更换文件后不会自动沿用旧兼容。未来正常计算的来源记录会标注实际生成，并重新记录输入/输出哈希。

## 验证

- `compileall` 通过；编译缓存写入独立测试目录。
- 全套测试：**125 passed，3 skipped**。跳过项是缺少 `legacy_2019_v1` 输出的原有历史比较测试，未为此重建数据。
- 8 组根入口检查命令、19 个直接步骤的 `--dry-run` 均通过。模拟测试另覆盖所有测算命令的提前返回。
- 当前 `all`、`measure-x`、`indices`、`dummy` 不带 `--force` 时，均在实际执行前拒绝覆盖。
- 三个当前 Stage 1 检查、最终权重对应检查、协定指标来源检查均通过。
- **133 个原有受保护文件、3,639,114,482 字节全部保持原哈希**，包括原始输入、分类、权重、得分、匹配输出、提示词、日志和历史清单。
- 测试只在独立临时目录使用合成数据。验证进程禁止联网、子进程调用及向研究目录写入；没有执行真实数据流水线。

完整记录：[validation.json](../../project_archive/dta_institutional_opening/code_backups/20260915_pipeline_safety/validation.json)、[测试日志](../../project_archive/dta_institutional_opening/code_backups/20260915_pipeline_safety/test_results.log)。

## 修改清单、备份与恢复

本次记录目录为：

```text
../project_archive/dta_institutional_opening/code_backups/20260915_pipeline_safety/
```

- `inventory_before.json`：修改前文件大小与 SHA256。
- `originals/`：修改前代码、配置、测试和入口文档，包含当时已有的用户修改。
- `change_manifest.json`：本次修改/新增文件及前后哈希。
- `git_status_before.txt`：修改前 Git 状态；未还原既有改动和未跟踪文件。
- `validate_repair.py`：可重复的离线验证脚本，须从 DTA 项目根运行。
- `cache_archive.json`：本次生成缓存的原路径、归档位置和哈希。

恢复时，先根据 `change_manifest.json` 核对当前文件是否又有后续编辑，再从 `originals/<相对路径>` 逐个恢复本次修改文件。新增文件可移回记录目录保留。不要整体覆盖项目、运行 Git 重置或改动研究 CSV/DTA。

自动审批拒绝了测试缓存删除，仅返回“blocked by policy”。已改为可恢复归档：10 个本次生成的缓存文件经大小/SHA256 核验后移出项目；核验副本与移动后的源文件均保留在 `task_generated_cache/`。合成测试材料集中保留在记录目录 `test_work/`。没有永久删除研究文件。

## 验证边界

这些检查证明入口保护、合成测试及当前文件完整性；不证明重新调用 LLM 后会产生相同判断。`all` 仍保持原有范围（测算与 dummy），Y–X 和控制变量匹配仍分别运行，未擅自改变调度范围。

子代理 `step_entry_guards` 负责直接脚本和包装器保护；`input_provenance_fix` 负责输入对应检查与合成测试；主代理完成全局预检、整合、当前文件核验和全套测试。
