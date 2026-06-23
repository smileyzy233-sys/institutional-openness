from utils import validate_stage1a_arbitration_output, validate_stage1a_output


def test_stage1a_accepts_binary_values():
    for value in [0, 1]:
        record, status, message = validate_stage1a_output(
            {
                "provision_id": "P1",
                "is_institutional_opening": value,
                "institutional_reason": "reason",
                "confidence": 0.8,
            }
        )
        assert status == "ok", message
        assert record["is_institutional_opening"] == value


def test_stage1a_rejects_invalid_binary_value():
    _record, status, message = validate_stage1a_output(
        {
            "provision_id": "P1",
            "is_institutional_opening": 2,
            "institutional_reason": "reason",
            "confidence": 0.8,
        }
    )
    assert status == "invalid"
    assert "0 or 1" in message


def test_stage1a_rejects_empty_reason_and_bad_confidence():
    _record, status, message = validate_stage1a_output(
        {
            "provision_id": "P1",
            "is_institutional_opening": 1,
            "institutional_reason": "",
            "confidence": 0.8,
        }
    )
    assert status == "invalid"
    assert "institutional_reason" in message

    for confidence in [-0.1, 1.1]:
        _record, status, message = validate_stage1a_output(
            {
                "provision_id": "P1",
                "is_institutional_opening": 1,
                "institutional_reason": "reason",
                "confidence": confidence,
            }
        )
        assert status == "invalid"
        assert "between 0 and 1" in message


def test_stage1a_arbitration_forces_low_confidence_to_human_review():
    record, status, message = validate_stage1a_arbitration_output(
        {
            "provision_id": "P1",
            "final_is_institutional_opening": 1,
            "arbitration_reason": "reason",
            "confidence": 0.5,
            "need_human_review": False,
        }
    )
    assert status == "ok", message
    assert record["need_human_review"] is True
