from utils import validate_stage2_output


def test_stage2_fixed_type_overrides_raw_weights():
    record, status, message = validate_stage2_output(
        {
            "provision_id": "P1",
            "impact_type": "mp",
            "trade_weight": 0.8,
            "investment_weight": 0.2,
            "confidence": 0.8,
        }
    )
    assert status == "ok", message
    assert record["raw_trade_weight"] == 0.8
    assert record["normalized_trade_weight"] == 1.0
    assert record["normalized_investment_weight"] == 0.0


def test_stage2_both_requires_weights_sum_to_one():
    _record, status, message = validate_stage2_output(
        {
            "provision_id": "P2",
            "impact_type": "both",
            "trade_weight": 0.8,
            "investment_weight": 0.3,
        }
    )
    assert status == "invalid"
    assert "sum to 1" in message


def test_stage2_tr_fixed_weight():
    record, status, message = validate_stage2_output(
        {
            "provision_id": "P3",
            "impact_type": "tr",
            "trade_weight": 1.0,
            "investment_weight": 0.0,
        }
    )
    assert status == "ok", message
    assert record["normalized_trade_weight"] == 0.0
    assert record["normalized_investment_weight"] == 1.0
