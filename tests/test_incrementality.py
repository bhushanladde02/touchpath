import pytest

from touchpath.generate import generate_holdout
from touchpath.incrementality import (
    compare_to_attribution,
    holdout_test,
    required_sample_size,
)


def test_lift_and_incremental_conversions():
    result = holdout_test(100_000, 2_300, 100_000, 2_000)
    assert abs(result.treatment_rate - 0.023) < 1e-9
    assert abs(result.relative_lift - 0.15) < 1e-9
    assert abs(result.incremental_conversions - 300) < 1e-6
    assert result.significant


def test_no_difference_is_not_significant():
    result = holdout_test(50_000, 1_000, 50_000, 1_000)
    assert result.absolute_lift == 0.0
    assert not result.significant
    assert result.ci_low < 0 < result.ci_high


def test_small_samples_cannot_conclude():
    result = holdout_test(100, 3, 100, 2)
    assert not result.significant


def test_recovers_a_known_simulated_lift():
    data = generate_holdout(users_per_group=200_000, control_rate=0.02, true_lift=0.15, seed=9)
    result = holdout_test(
        data["treatment_users"],
        data["treatment_conversions"],
        data["control_users"],
        data["control_conversions"],
    )
    assert abs(result.relative_lift - 0.15) < 0.05
    assert result.significant


def test_sample_size_grows_as_the_effect_shrinks():
    assert required_sample_size(0.02, 0.20) < required_sample_size(0.02, 0.05)
    assert required_sample_size(0.02, 0.10) > 10_000


def test_bad_inputs_are_rejected():
    with pytest.raises(ValueError):
        holdout_test(0, 0, 100, 5)
    with pytest.raises(ValueError):
        required_sample_size(1.5, 0.1)


def test_attribution_can_be_compared_against_incrementality():
    result = holdout_test(100_000, 2_300, 100_000, 2_000)
    verdict = compare_to_attribution(result, attributed_conversions=1_000)
    assert verdict["incremental_conversions"] == 300.0
    assert verdict["incrementality_ratio"] == 0.3
    assert verdict["overstated_by"] == 700.0
