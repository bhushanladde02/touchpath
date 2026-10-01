"""Model tests check against hand-computed values, not just 'it ran'."""

from datetime import datetime, timedelta

import pytest

from touchpath.models import heuristic, markov, shapley
from touchpath.paths import Path, build_paths
from touchpath.schema import Event

BASE = datetime(2026, 9, 1)


def path(channels, revenue=100.0, user="u1", day=10):
    return Path(user_id=user, converted_at=BASE + timedelta(days=day), revenue=revenue, channels=tuple(channels))


THREE_TOUCH = [path(["display", "paid_search", "email"], revenue=300.0)]


def test_last_touch_gives_everything_to_the_final_channel():
    result = heuristic.attribute(THREE_TOUCH, "last")
    assert result.revenue == {"email": 300.0}


def test_first_touch_gives_everything_to_the_opening_channel():
    assert heuristic.attribute(THREE_TOUCH, "first").revenue == {"display": 300.0}


def test_linear_splits_evenly():
    result = heuristic.attribute(THREE_TOUCH, "linear").rounded()
    assert result.revenue == {"display": 100.0, "paid_search": 100.0, "email": 100.0}


def test_position_based_is_forty_twenty_forty():
    result = heuristic.attribute(THREE_TOUCH, "position").rounded()
    assert result.revenue == {"display": 120.0, "email": 120.0, "paid_search": 60.0}


def test_position_based_with_two_touches_splits_evenly():
    result = heuristic.attribute([path(["a", "b"], revenue=100.0)], "position").rounded()
    assert result.revenue == {"a": 50.0, "b": 50.0}


def test_time_decay_favours_recent_touches():
    result = heuristic.attribute(THREE_TOUCH, "time_decay", half_life_days=1.0)
    assert result.revenue["email"] > result.revenue["paid_search"] > result.revenue["display"]


@pytest.mark.parametrize("model", ["first", "last", "linear", "position", "time_decay"])
def test_every_heuristic_conserves_revenue(model):
    paths = [path(["a", "b"], 100.0), path(["b", "c", "a"], 250.0), path([], 75.0)]
    result = heuristic.attribute(paths, model)
    assert abs(result.total_revenue - 425.0) < 1e-6


def test_direct_conversions_are_labelled_not_dropped():
    result = heuristic.attribute([path([], revenue=40.0)], "last")
    assert result.revenue == {"direct": 40.0}


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError):
        heuristic.attribute(THREE_TOUCH, "telepathy")


def test_markov_conserves_revenue_and_ranks_the_useful_channel_first():
    # email appears in every converting journey; display appears in dead ends
    paths = [path(["email"], 100.0, user=f"u{i}", day=i) for i in range(20)]
    paths += [path(["display", "email"], 100.0, user=f"v{i}", day=i) for i in range(5)]
    non_converting = [("display",)] * 60

    result = markov.attribute(paths, non_converting=non_converting)
    assert abs(result.total_revenue - 2500.0) < 1e-6
    assert result.revenue["email"] > result.revenue["display"]
    assert 0.0 <= result.meta["removal_effects"]["display"] <= 1.0


def test_markov_removal_effect_is_total_for_a_single_channel():
    journeys = [(("email",), True)] * 10 + [(("email",), False)] * 10
    effects = markov.removal_effects(journeys)
    assert abs(effects["email"] - 1.0) < 1e-6


def test_markov_handles_only_direct_conversions():
    result = markov.attribute([path([], 50.0)])
    assert result.revenue == {"direct": 50.0}


def test_shapley_splits_a_symmetric_pair_equally():
    # two channels that always appear together must receive identical credit
    paths = [path(["a", "b"], 100.0, user=f"u{i}", day=i) for i in range(10)]
    result = shapley.attribute(paths).rounded()
    assert result.revenue["a"] == result.revenue["b"] == 500.0


def test_shapley_gives_nothing_to_a_null_player():
    # 'c' never adds value: every journey containing it also converts without it
    paths = [path(["a"], 100.0, user=f"u{i}", day=i) for i in range(10)]
    result = shapley.attribute(paths)
    assert "c" not in result.revenue


def test_shapley_conserves_revenue():
    paths = [
        path(["a", "b"], 100.0, user="u1", day=1),
        path(["b"], 200.0, user="u2", day=2),
        path(["a", "c"], 300.0, user="u3", day=3),
        path([], 50.0, user="u4", day=4),
    ]
    result = shapley.attribute(paths)
    assert abs(result.total_revenue - 650.0) < 1e-6


def test_shapley_sampling_approximates_the_exact_answer():
    paths = [
        path(["a", "b"], 100.0, user="u1", day=1),
        path(["b", "c"], 200.0, user="u2", day=2),
        path(["a", "c"], 300.0, user="u3", day=3),
    ]
    exact = shapley.attribute(paths, exact_limit=12)
    sampled = shapley.attribute(paths, exact_limit=0, samples=20_000, seed=3)
    for channel in exact.revenue:
        assert abs(exact.revenue[channel] - sampled.revenue[channel]) < 5.0


def test_models_agree_on_a_single_channel_world():
    paths = [path(["email"], 100.0, user=f"u{i}", day=i) for i in range(5)]
    for result in (
        heuristic.attribute(paths, "linear"),
        markov.attribute(paths),
        shapley.attribute(paths),
    ):
        assert abs(result.revenue["email"] - 500.0) < 1e-6


def test_result_helpers():
    result = heuristic.attribute(THREE_TOUCH, "linear")
    assert abs(sum(result.share().values()) - 1.0) < 1e-9
    assert result.ranked()[0][0] in {"display", "paid_search", "email"}
    assert "linear" in result.table()


def test_compare_runs_every_heuristic():
    results = heuristic.compare([path(["a", "b"], 100.0)])
    assert set(results) == {"first", "last", "linear", "position", "time_decay"}
