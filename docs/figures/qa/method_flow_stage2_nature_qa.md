# Nature-style DTA method flowcharts QA notes

Core conclusion: 同一 Stage 1 样本构建下，Stage 2 可以呈现为双模型仲裁方案或单模型 B 方案，二者共享制度型开放识别、质量控制和可追溯输出逻辑。

Evidence chain:
- Data preparation standardizes the provision grain and agreement-provision matrix.
- Stage 1 identifies institutional opening and institutional dimensions through dual-model coding plus arbitration.
- Stage 2 diverges into either dual-model independent coding with conflict arbitration, or single-model B coding with rule validation and human spot review.
- Final outputs aggregate provision-level trade/investment weights into agreement-level and country-pair-year measures.

Archetype: schematic-led composite.

Journal/export contract:
- Backend: Python/matplotlib only.
- Width: 7.20 in before tight bounding, suitable for a double-column manuscript figure.
- Exports: editable SVG, editable-font PDF, 600 dpi PNG, 600 dpi TIFF.
- Text: Microsoft YaHei for Chinese labels; SVG/PDF fonttype settings keep text editable when supported by the viewer.
- Color: neutral greys with restrained blue-green method family and pale review accent; no rainbow palette.

Visual QA:
- method_flow_stage2_dual_model_nature.png: 3468x2037 px, non-white sample share=0.1692, mean RGB=[243.51, 243.91, 244.08].
- method_flow_stage2_single_model_nature.png: 3468x2037 px, non-white sample share=0.15325, mean RGB=[244.14, 244.43, 244.62].

No existing method_flow_stage2_dual_model.pdf or method_flow_stage2_single_model.pdf files were overwritten; new files use the `_nature` suffix.
