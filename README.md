# DTA Institutional Opening Pipeline v2

This project builds provision-level institutional-opening classifications and
agreement / country-pair-year raw trade and investment scores from DTA 2.0.

The v2 pipeline separates LLM coding into two strictly ordered stages.

## Setup

Place the source workbook at:

```text
data/raw/DTA 2.0 - Vertical Content (v2).xlsx
```

Install dependencies and configure `.env` from `.env.example`:

```bash
pip install -r requirements.txt
```

Default LLM routing:

- Model A: `deepseek` provider, `deepseek-v4-pro`, official DeepSeek API.
- Model B: `dashscope` provider, `qwen3.7-plus`, DashScope compatible API.
- Arbitration: `dashscope` provider, `glm-5`, DashScope compatible API.

Thinking mode is explicitly disabled for models A, B, and arbitration.
Arbitration sends `enable_thinking=false` through the DashScope
OpenAI-compatible API.

## Workflow

Stage 1 classifies every provision for:

- `is_institutional_opening`: `0` or `1`
- `dominant_dimension`: `rules`, `regulation`, `management`, `standards`, or `none`

If model A and model B differ on either Stage 1 field, the provision enters
Stage 1 arbitration. Stage 1 does not classify trade-investment type and does
not assign weights.

Stage 2 starts only after the whole Stage 1 sample is finalized and
`data/processed/STAGE1_SUCCESS` plus `manifests/stage1_manifest.json` are valid.
Stage 2 only processes provisions whose final Stage 1 result is institutional
opening.

Stage 2 classifies:

- `mp`: only institutional trade opening
- `tr`: only institutional cross-border investment opening
- `both`: both institutional trade and cross-border investment opening
- `none`: institutional opening, but no direct trade or investment impact

`tr` means cross-border investment opening; it does not mean trade.

`none` and `not_applicable` are different:

- `none`: entered Stage 2, but has no direct trade/investment impact.
- `not_applicable`: did not enter Stage 2 because Stage 1 final result was
  non-institutional opening.

Stage 2 arbitration only compares `impact_type`. If both models return `both`,
weight differences never trigger arbitration; the final weights are the
arithmetic mean of the two model weights.

Fixed type weights are enforced in code:

```text
mp   -> 1.0, 0.0
tr   -> 0.0, 1.0
none -> 0.0, 0.0
```

## Commands

Run the full workflow:

```bash
python run_pipeline.py all
```

Run an API-free structural workflow:

```bash
python run_pipeline.py all --llm-provider heuristic --force
```

The heuristic provider is for software validation only and must not be used as
a research result.

Individual commands:

```bash
python run_pipeline.py load
python run_pipeline.py stage1
python run_pipeline.py stage1 --model-role A
python run_pipeline.py stage1 --model-role B
python run_pipeline.py stage1-arbitrate
python run_pipeline.py stage1-finalize
python run_pipeline.py stage2
python run_pipeline.py stage2 --model-role A
python run_pipeline.py stage2 --model-role B
python run_pipeline.py stage2-arbitrate
python run_pipeline.py finalize
python run_pipeline.py indices
python run_pipeline.py dummy
python run_pipeline.py diagnostics
```

The `all` command runs load, Stage 1 model A, Stage 1 model B, Stage 1 compare,
Stage 1 arbitration, Stage 1 finalization, Stage 1 gate check, Stage 2 model A,
Stage 2 model B, Stage 2 compare, Stage 2 arbitration, final weights, agreement
indices, country-pair indices, trade agreement dummy, and diagnostics.

## Human Review Priority

Final decision priority is:

```text
completed human review
> valid arbitration model result
> dual-model consensus
```

Unresolved provisions are blocking. The production setting is:

```python
ALLOW_UNRESOLVED = False
```

There is no model-A fallback for unresolved conflicts.

Human review queues:

```text
data/interim/stage1/stage1_manual_review_queue.csv
data/interim/stage2/stage2_manual_review_queue.csv
```

## Core Outputs

```text
data/interim/stage1/stage1_model_a_results.csv
data/interim/stage1/stage1_model_b_results.csv
data/interim/stage1/stage1_dual_model_comparison.csv
data/interim/stage1/stage1_conflict_queue.csv
data/interim/stage1/stage1_arbitration_results.csv
data/processed/stage1_final_classification.csv
data/processed/STAGE1_SUCCESS
manifests/stage1_manifest.json

data/interim/stage2/stage2_model_a_results.csv
data/interim/stage2/stage2_model_b_results.csv
data/interim/stage2/stage2_dual_model_comparison.csv
data/interim/stage2/stage2_type_conflict_queue.csv
data/interim/stage2/stage2_arbitration_results.csv
data/processed/final_provision_weights.csv

data/processed/agreement_level_indices.csv
data/processed/country_pair_year_indices.csv
data/processed/dta_active_agreement_dummy_all_dta_pair_year.csv
data/processed/trade_agreement_dummy_icio_economies_all_years_pair_year.csv
data/processed/trade_agreement_dummy_icio2019_pair_year.csv
data/processed/trade_agreement_dummy_expanded_union_pair_year.csv
data/processed/trade_agreement_dummy_diagnostics.csv
data/processed/trade_agreement_dummy_code_mismatch_report.csv
data/processed/diagnostics_summary.csv
```

Agreement and country-pair-year scripts continue to use:

```text
effective_trade_weight
effective_investment_weight
```

The old six-category weight types are not valid v2 inputs:

```text
trade_only
trade_dominant_dual
balanced_dual
investment_dominant_dual
investment_only
irrelevant
```

If these values are detected in v2 inputs, the pipeline raises an explicit
"detected old workflow result" error instead of silently reusing them.

## Trade Agreement Dummy

Place `icio2019.dta` at:

```text
data/need_dummy/icio2019.dta
```

Then run:

```bash
python run_pipeline.py dummy
```

The dummy construction keeps the previous undirected country-pair logic. Active
pair-years receive raw scores from the active agreement set; pair-years without
an active agreement and domestic observations receive zero scores.

## Tests

Run:

```bash
python -m pytest -q
```

The test suite uses mock CSVs and does not call remote models.
