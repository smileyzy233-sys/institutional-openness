from utils import validate_stage1b_arbitration_output, validate_stage1b_output


def test_stage1b_accepts_four_dimensions():
    for dimension in ["rules", "regulation", "management", "standards"]:
        record, status, message = validate_stage1b_output(
            {
                "provision_id": "P1",
                "dominant_dimension": dimension,
                "dimension_reason": "reason",
                "confidence": 0.8,
            }
        )
        assert status == "ok", message
        assert record["dominant_dimension"] == dimension


def test_stage1b_rejects_none_unknown_and_empty_reason():
    for dimension in ["none", "unknown"]:
        _record, status, message = validate_stage1b_output(
            {
                "provision_id": "P1",
                "dominant_dimension": dimension,
                "dimension_reason": "reason",
                "confidence": 0.8,
            }
        )
        assert status == "invalid"
        assert "dominant_dimension" in message

    _record, status, message = validate_stage1b_output(
        {
            "provision_id": "P1",
            "dominant_dimension": "rules",
            "dimension_reason": "",
            "confidence": 0.8,
        }
    )
    assert status == "invalid"
    assert "dimension_reason" in message


def test_stage1b_arbitration_forces_low_confidence_to_human_review():
    record, status, message = validate_stage1b_arbitration_output(
        {
            "provision_id": "P1",
            "final_dominant_dimension": "rules",
            "arbitration_reason": "reason",
            "confidence": 0.5,
            "need_human_review": False,
        }
    )
    assert status == "ok", message
    assert record["need_human_review"] is True
