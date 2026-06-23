from __future__ import annotations

import pandas as pd

import config
import utils
from conftest import load_script


def test_default_model_thinking_modes() -> None:
    assert config.MODEL_A["thinking_mode"] == "disabled"
    assert config.MODEL_B["thinking_mode"] == "disabled"
    assert config.ARBITRATION_MODEL["name"] == "glm-5"
    assert config.ARBITRATION_MODEL["thinking_mode"] == "disabled"


def test_role_thinking_modes_are_sent_to_providers(monkeypatch) -> None:
    requests = []

    def fake_call_openai_compatible(prompt, **kwargs):
        requests.append({"prompt": prompt, **kwargs})
        return "{}", "stop"

    monkeypatch.setattr(utils, "call_openai_compatible", fake_call_openai_compatible)

    for role in ("A", "B", "arbitration"):
        settings = utils.model_settings_for_role(role)
        utils.call_provider(
            "test prompt",
            provider=settings["provider"],
            model_name=settings["name"],
            base_url=settings["base_url"],
            model_role=role,
        )

    assert requests[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert requests[1]["extra_body"] == {"enable_thinking": False}
    assert requests[2]["extra_body"] == {"enable_thinking": False}


def test_stage1a_reuses_results_with_legacy_input_hashes() -> None:
    stage1a = load_script("03_stage1a_llm_code_institutional.py")
    provisions = pd.DataFrame(
        [{"provision_id": "P1", "provision_text": "Market access commitments."}]
    )
    prompt_sha256 = "prompt-sha"
    legacy_hash = stage1a.legacy_input_hashes(provisions, prompt_sha256)["P1"]
    existing = pd.DataFrame(
        [
            {
                "provision_id": "P1",
                "parse_status": "ok",
                "validation_status": "ok",
                "model_role": "B",
                "model_provider": "dashscope",
                "model_name": "qwen3.7-plus",
                "prompt_version": config.STAGE1A_PROMPT_VERSION,
                "prompt_sha256": prompt_sha256,
                "pipeline_schema_version": config.PIPELINE_SCHEMA_VERSION,
                "input_hash": legacy_hash,
            }
        ]
    )

    reused = stage1a.filter_current_rows(
        existing,
        model_role="B",
        provider="dashscope",
        model_name="qwen3.7-plus",
        prompt_sha256=prompt_sha256,
        expected_hashes=stage1a.current_input_hashes(provisions, prompt_sha256, "B"),
        legacy_expected_hashes=stage1a.legacy_input_hashes(provisions, prompt_sha256),
    )

    assert reused["provision_id"].tolist() == ["P1"]
