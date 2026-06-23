from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

PIPELINE_SCHEMA_VERSION = "3.0"
COVERAGE_MATRIX_SCHEMA_VERSION = "fractional_coverage_v1"

RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "DTA 2.0 - Vertical Content (v2)_code.xlsx"

INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
STAGE1_INTERIM_DIR = INTERIM_DIR / "stage1"
STAGE1A_INTERIM_DIR = STAGE1_INTERIM_DIR / "stage1a"
STAGE1B_INTERIM_DIR = STAGE1_INTERIM_DIR / "stage1b"
STAGE2_INTERIM_DIR = INTERIM_DIR / "stage2"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
NEED_DUMMY_DIR = PROJECT_ROOT / "data" / "need_dummy"
PROMPT_DIR = PROJECT_ROOT / "prompts"
LOG_DIR = PROJECT_ROOT / "logs"
STAGE1_LOG_DIR = LOG_DIR / "stage1"
STAGE1A_LOG_DIR = LOG_DIR / "stage1a"
STAGE1B_LOG_DIR = LOG_DIR / "stage1b"
STAGE2_LOG_DIR = LOG_DIR / "stage2"
LLM_LOG_DIR = LOG_DIR / "llm_calls"
MANIFEST_DIR = PROJECT_ROOT / "manifests"

PROVISIONS_MASTER_PATH = INTERIM_DIR / "provisions_master.csv"
AGREEMENT_MATRIX_PATH = INTERIM_DIR / "agreement_matrix.csv"
AGREEMENT_PROVISION_LONG_PATH = INTERIM_DIR / "agreement_provision_long.csv"
AGREEMENTS_MASTER_PATH = INTERIM_DIR / "agreements_master.csv"
BILATERAL_PANEL_PATH = INTERIM_DIR / "bilateral_panel.csv"

STAGE1A_MODEL_A_RESULTS_PATH = STAGE1A_INTERIM_DIR / "stage1a_model_a_results.csv"
STAGE1A_MODEL_B_RESULTS_PATH = STAGE1A_INTERIM_DIR / "stage1a_model_b_results.csv"
STAGE1A_TECHNICAL_ERROR_QUEUE_PATH = (
    STAGE1A_INTERIM_DIR / "stage1a_technical_error_queue.csv"
)
STAGE1A_COMPARISON_PATH = STAGE1A_INTERIM_DIR / "stage1a_dual_model_comparison.csv"
STAGE1A_CONFLICT_QUEUE_PATH = STAGE1A_INTERIM_DIR / "stage1a_conflict_queue.csv"
STAGE1A_ARBITRATION_RESULTS_PATH = (
    STAGE1A_INTERIM_DIR / "stage1a_arbitration_results.csv"
)
STAGE1A_MANUAL_REVIEW_QUEUE_PATH = (
    STAGE1A_INTERIM_DIR / "stage1a_manual_review_queue.csv"
)
STAGE1A_FINAL_CLASSIFICATION_PATH = PROCESSED_DIR / "stage1a_final_classification.csv"
STAGE1A_SUCCESS_PATH = PROCESSED_DIR / "STAGE1A_SUCCESS"
STAGE1A_MANIFEST_PATH = MANIFEST_DIR / "stage1a_manifest.json"

STAGE1B_MODEL_A_RESULTS_PATH = STAGE1B_INTERIM_DIR / "stage1b_model_a_results.csv"
STAGE1B_MODEL_B_RESULTS_PATH = STAGE1B_INTERIM_DIR / "stage1b_model_b_results.csv"
STAGE1B_TECHNICAL_ERROR_QUEUE_PATH = (
    STAGE1B_INTERIM_DIR / "stage1b_technical_error_queue.csv"
)
STAGE1B_COMPARISON_PATH = STAGE1B_INTERIM_DIR / "stage1b_dual_model_comparison.csv"
STAGE1B_CONFLICT_QUEUE_PATH = STAGE1B_INTERIM_DIR / "stage1b_conflict_queue.csv"
STAGE1B_ARBITRATION_RESULTS_PATH = (
    STAGE1B_INTERIM_DIR / "stage1b_arbitration_results.csv"
)
STAGE1B_MANUAL_REVIEW_QUEUE_PATH = (
    STAGE1B_INTERIM_DIR / "stage1b_manual_review_queue.csv"
)
STAGE1B_FINAL_CLASSIFICATION_PATH = PROCESSED_DIR / "stage1b_final_classification.csv"
STAGE1B_SUCCESS_PATH = PROCESSED_DIR / "STAGE1B_SUCCESS"
STAGE1B_MANIFEST_PATH = MANIFEST_DIR / "stage1b_manifest.json"

STAGE1_FINAL_CLASSIFICATION_PATH = PROCESSED_DIR / "stage1_final_classification.csv"
STAGE1_SUCCESS_PATH = PROCESSED_DIR / "STAGE1_SUCCESS"
STAGE1_MANIFEST_PATH = MANIFEST_DIR / "stage1_manifest.json"

STAGE2_MODEL_A_RESULTS_PATH = STAGE2_INTERIM_DIR / "stage2_model_a_results.csv"
STAGE2_MODEL_B_RESULTS_PATH = STAGE2_INTERIM_DIR / "stage2_model_b_results.csv"
STAGE2_TECHNICAL_ERROR_QUEUE_PATH = (
    STAGE2_INTERIM_DIR / "stage2_technical_error_queue.csv"
)
STAGE2_COMPARISON_PATH = STAGE2_INTERIM_DIR / "stage2_dual_model_comparison.csv"
STAGE2_TYPE_CONFLICT_QUEUE_PATH = (
    STAGE2_INTERIM_DIR / "stage2_type_conflict_queue.csv"
)
STAGE2_ARBITRATION_RESULTS_PATH = (
    STAGE2_INTERIM_DIR / "stage2_arbitration_results.csv"
)
STAGE2_MANUAL_REVIEW_QUEUE_PATH = (
    STAGE2_INTERIM_DIR / "stage2_manual_review_queue.csv"
)

FINAL_PROVISION_WEIGHTS_PATH = PROCESSED_DIR / "final_provision_weights.csv"
AGREEMENT_LEVEL_INDICES_PATH = PROCESSED_DIR / "agreement_level_indices.csv"
COUNTRY_PAIR_YEAR_INDICES_PATH = PROCESSED_DIR / "country_pair_year_indices.csv"
DIAGNOSTICS_SUMMARY_PATH = PROCESSED_DIR / "diagnostics_summary.csv"

ICIO2019_PATH = NEED_DUMMY_DIR / "icio2019.dta"
DTA_ACTIVE_AGREEMENT_DUMMY_PATH = (
    PROCESSED_DIR / "dta_active_agreement_dummy_all_dta_pair_year.csv"
)
ICIO_PAIR_YEAR_DUMMY_PATH = PROCESSED_DIR / "trade_agreement_dummy_icio2019_pair_year.csv"
ICIO_ECONOMIES_ALL_YEARS_DUMMY_PATH = (
    PROCESSED_DIR / "trade_agreement_dummy_icio_economies_all_years_pair_year.csv"
)
EXPANDED_UNION_PAIR_YEAR_DUMMY_PATH = (
    PROCESSED_DIR / "trade_agreement_dummy_expanded_union_pair_year.csv"
)
TRADE_AGREEMENT_DUMMY_DIAGNOSTICS_PATH = (
    PROCESSED_DIR / "trade_agreement_dummy_diagnostics.csv"
)
TRADE_AGREEMENT_DUMMY_CODE_REPORT_PATH = (
    PROCESSED_DIR / "trade_agreement_dummy_code_mismatch_report.csv"
)
COUNTRY_CODE_CROSSWALK_PATH = NEED_DUMMY_DIR / "country_code_crosswalk.csv"

STAGE1A_PROMPT_PATH = PROMPT_DIR / "stage1a_institutional.txt"
STAGE1A_ARBITRATION_PROMPT_PATH = PROMPT_DIR / "stage1a_arbitration.txt"
STAGE1B_PROMPT_PATH = PROMPT_DIR / "stage1b_dimension.txt"
STAGE1B_ARBITRATION_PROMPT_PATH = PROMPT_DIR / "stage1b_arbitration.txt"
STAGE2_PROMPT_PATH = PROMPT_DIR / "stage2_trade_investment.txt"
STAGE2_ARBITRATION_PROMPT_PATH = PROMPT_DIR / "stage2_type_arbitration.txt"
STAGE1A_PROMPT_VERSION = "v1_zh_stage1a_institutional_split"
STAGE1A_ARBITRATION_PROMPT_VERSION = "v1_zh_stage1a_arbitration_split"
STAGE1B_PROMPT_VERSION = "v1_zh_stage1b_dimension_split"
STAGE1B_ARBITRATION_PROMPT_VERSION = "v1_zh_stage1b_arbitration_split"
STAGE2_PROMPT_VERSION = "v3_zh_stage2_trade_invest"
STAGE2_ARBITRATION_PROMPT_VERSION = "v3_zh_stage2_type_arbitration"

MODEL_A_PROVIDER = "deepseek"
MODEL_A_NAME = "deepseek-v4-pro"
MODEL_A_BASE_URL = None
MODEL_A_THINKING_MODE = "disabled"
DEEPSEEK_REASONING_EFFORT = "high"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_B_PROVIDER = "dashscope"
MODEL_B_NAME = "qwen3.7-plus"
MODEL_B_BASE_URL = DASHSCOPE_BASE_URL
MODEL_B_THINKING_MODE = "disabled"
ARBITRATION_MODEL_PROVIDER = "dashscope"
ARBITRATION_MODEL_NAME = "glm-5"
ARBITRATION_MODEL_BASE_URL = DASHSCOPE_BASE_URL
ARBITRATION_THINKING_MODE = "disabled"

# Compatibility alias retained for existing DeepSeek-specific integrations.
DEEPSEEK_THINKING_MODE = MODEL_A_THINKING_MODE

MODEL_A = {
    "role": "A",
    "provider": MODEL_A_PROVIDER,
    "name": MODEL_A_NAME,
    "base_url": MODEL_A_BASE_URL,
    "thinking_mode": MODEL_A_THINKING_MODE,
}
MODEL_B = {
    "role": "B",
    "provider": MODEL_B_PROVIDER,
    "name": MODEL_B_NAME,
    "base_url": MODEL_B_BASE_URL,
    "thinking_mode": MODEL_B_THINKING_MODE,
}
ARBITRATION_MODEL = {
    "role": "arbitration",
    "provider": ARBITRATION_MODEL_PROVIDER,
    "name": ARBITRATION_MODEL_NAME,
    "base_url": ARBITRATION_MODEL_BASE_URL,
    "thinking_mode": ARBITRATION_THINKING_MODE,
}

# Compatibility aliases for older command wrappers and environments.
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
MODEL_C_PROVIDER = ARBITRATION_MODEL_PROVIDER
MODEL_C_NAME = ARBITRATION_MODEL_NAME
MODEL_C_BASE_URL = ARBITRATION_MODEL_BASE_URL

TEMPERATURE = 0
TOP_P = 1
MAX_TOKENS = 800
ARBITRATION_MAX_TOKENS = 1000
MODEL_C_MAX_TOKENS = ARBITRATION_MAX_TOKENS

DIMENSION_VALUES = {
    "rules",
    "regulation",
    "management",
    "standards",
    "none",
}
INSTITUTIONAL_DIMENSION_VALUES = DIMENSION_VALUES - {"none"}

IMPACT_TYPE_VALUES = {
    "mp",
    "tr",
    "both",
    "none",
}
FIXED_TYPE_WEIGHTS = {
    "mp": (1.0, 0.0),
    "tr": (0.0, 1.0),
    "none": (0.0, 0.0),
}
OLD_SIX_CLASSIFICATION_VALUES = {
    "trade_only",
    "trade_dominant_dual",
    "balanced_dual",
    "investment_dominant_dual",
    "investment_only",
    "irrelevant",
}

WEIGHT_SUM_TOLERANCE = 1e-6
MAX_LLM_RETRIES = 3
OUTPUT_FLOAT_DECIMALS = 6
ALLOW_UNRESOLVED = False
STAGE1_ARBITRATION_HUMAN_REVIEW_THRESHOLD = 0.75
STAGE1_ARBITRATION_RATE_TARGET = 0.20

MULTI_AGREEMENT_METHOD = "union"
CSV_ENCODING = "utf-8-sig"
