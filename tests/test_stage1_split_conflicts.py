from utils import stage1a_conflict_reason, stage1b_conflict_reason


def test_stage1a_conflict_reason_only_compares_binary_value():
    assert stage1a_conflict_reason(1, 1) == (True, False, "")
    assert stage1a_conflict_reason(1, 0) == (False, True, "institutional_mismatch")


def test_stage1b_conflict_reason_only_compares_dimension():
    assert stage1b_conflict_reason("rules", "rules") == (True, False, "")
    assert stage1b_conflict_reason("rules", "regulation") == (
        False,
        True,
        "dimension_mismatch",
    )
