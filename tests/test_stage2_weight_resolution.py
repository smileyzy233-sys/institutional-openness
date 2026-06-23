from utils import average_both_weights, normalize_stage2_weights, stage2_needs_arbitration


def test_both_weight_average_does_not_trigger_arbitration():
    assert not stage2_needs_arbitration("both", "both")
    trade, investment = average_both_weights(0.7, 0.3, 0.5, 0.5)
    assert trade == 0.6
    assert investment == 0.4


def test_both_large_difference_still_averages():
    trade, investment = average_both_weights(0.9, 0.1, 0.1, 0.9)
    assert trade == 0.5
    assert investment == 0.5


def test_fixed_type_mapping():
    assert normalize_stage2_weights("mp", 0.8, 0.2) == (1.0, 0.0)
    assert normalize_stage2_weights("tr", 0.8, 0.2) == (0.0, 1.0)
    assert normalize_stage2_weights("none", 0.8, 0.2) == (0.0, 0.0)
