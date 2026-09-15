# Stata 实证起点构建代码

本目录两份 `.do` 是 2026-09-15 从并列 Stata 项目复制的原文副本，供公开审阅。
精确来源与 SHA256 见 `../evidence/stata_sources.json`。

- Trade：`explorations/io_trade_longdiff_data/dofiles/01_build_trade_long_difference_data.do`
- MP：`explorations/io_mp_longdiff_data/dofiles/01_build_mp_long_difference_data.do`

它们在 Stata 项目根目录使用相对路径，读取四份 fractional 快照，生成 OLS 宽表和
PPML 两期长表。脚本包含 `save, replace` 和日志覆盖，因此只读复核请使用
`../../scripts/verify_review_bundle.py`，不要在现存工作目录直接运行 `.do`。
本次发布未执行这些脚本；最新筛选保护代码不能当作现存派生数据的一次新运行证据。

已有回归从派生数据读取：
`explorations/new_d_ln_ols_longdiff/dofiles/01_estimate_longdiff_ols.do` 和
`explorations/new_ppml/dofiles/01_estimate_ppml.do`。
本仓库公开范围止于实证起点构建，不在此提供新的回归结果或显著性结论。
