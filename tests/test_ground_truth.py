"""The answer key has to measure what the models measure.

This file exists because it once did not. The generator summed each channel's
influence over *every* journey, converting or not, while a model reports its
share of revenue over *converting* paths only. Two different quantities over
two different populations, subtracted from each other and called a score. Every
model looked wrong by roughly the same amount and in the same direction, the
ranking between them was close to arbitrary, and nothing in the suite noticed —
the tests checked that the key summed to 1.0 and that the published file
matched what was built, both of which stayed true throughout.

The test that catches it is the oracle below: a model given the generator's own
influence weights must score near zero. If the key is measuring something else,
perfect knowledge still scores badly, and that is the signal.
"""

from __future__ import annotations

import pytest

from touchpath.datasets import build, catalogue
from touchpath.generate import DEFAULT_CHANNELS, generate_events
from touchpath.ingest import ingest_records
from touchpath.paths import build_paths
from touchpath.web.app import ALL_MODELS, analyse


def oracle_share(paths, weights) -> dict[str, float]:
    """What a model that already knows the influence weights would report.

    Splits each converting path's revenue across the channels on it, in
    proportion to their true influence — the rule the generator itself used.
    Runs on the *observed* paths, after corruption and the lookback window, so
    whatever it fails to recover is measurement loss rather than model error.
    """
    credited = {channel: 0.0 for channel in weights}
    for path in paths:
        touched = {channel for channel in path.channels if channel in weights}
        total = sum(weights[channel][1] for channel in touched)
        if total <= 0:
            continue
        for channel in touched:
            credited[channel] += path.revenue * weights[channel][1] / total

    grand_total = sum(credited.values()) or 1.0
    return {channel: value / grand_total * 100 for channel, value in credited.items()}


def mae(shares: list[float], truth: list[float]) -> float:
    return sum(abs(a - b) for a, b in zip(shares, truth)) / len(truth)


def test_an_oracle_recovers_the_answer_key():
    """Perfect knowledge of the weights must score near zero.

    This is the whole contract. If it fails, the key and the models are
    measuring different things and every score in the project is meaningless,
    however plausible the ranking looks.
    """
    records, truth = generate_events(users=20_000, corruption_rate=0.03, seed=11)
    events, _ = ingest_records(records)
    paths = build_paths(events, lookback_days=30)

    payload = analyse(records, 30, ALL_MODELS, truth)
    channels, key = payload["channels"], payload["ground_truth"]

    oracle = oracle_share(paths, DEFAULT_CHANNELS)
    error = mae([oracle.get(channel, 0.0) for channel in channels], key)

    assert error < 0.5, (
        f"an oracle scored {error:.2f} share points against the answer key; "
        "the key is not measuring revenue share over converting journeys"
    )


def test_the_oracle_beats_every_real_model():
    """Sanity on the scale: knowing the answer should help.

    A benchmark where perfect knowledge scores no better than a heuristic is
    not measuring anything, whatever its numbers look like.
    """
    records, truth = generate_events(users=20_000, corruption_rate=0.03, seed=11)
    events, _ = ingest_records(records)
    paths = build_paths(events, lookback_days=30)

    payload = analyse(records, 30, ALL_MODELS, truth)
    channels, key = payload["channels"], payload["ground_truth"]

    oracle = oracle_share(paths, DEFAULT_CHANNELS)
    oracle_error = mae([oracle.get(channel, 0.0) for channel in channels], key)
    best_model_error = min(mae(entry["share"], key) for entry in payload["series"])

    assert oracle_error < best_model_error


def test_the_key_is_derived_from_conversions_not_exposure():
    """Change how often journeys convert and the key must move.

    This is the sharpest statement of the bug this file guards against. The old
    definition summed influence over every journey and never looked at whether
    one converted, so it returned the same answer whatever the conversion rate
    — here, a fixed 75/25 split of frequency times influence. A key built from
    credited revenue cannot do that: raise the base rate and weak-but-common
    channels start converting on their own, which is a real change in who
    earned the money.
    """
    channels = {"wide_weak": (0.8, 0.05), "narrow_strong": (0.2, 0.60)}

    _, rare = generate_events(
        users=40_000, channels=channels, base_conversion_rate=0.005, seed=9
    )
    _, common = generate_events(
        users=40_000, channels=channels, base_conversion_rate=0.30, seed=9
    )

    assert rare != common, "the key ignored the conversion rate entirely"
    assert common["wide_weak"] > rare["wide_weak"] + 0.05

    # And neither is the exposure ratio the old definition would have produced.
    exposure_ratio = (0.2 * 0.60) / (0.2 * 0.60 + 0.8 * 0.05)
    assert abs(rare["narrow_strong"] - exposure_ratio) > 0.2


def test_the_key_sums_to_one_for_every_sample():
    for entry in catalogue():
        _, truth, _ = build(entry["slug"])
        assert sum(truth.values()) == pytest.approx(1.0, abs=0.01), entry["slug"]
        assert all(value >= 0 for value in truth.values()), entry["slug"]


def test_zero_influence_channels_still_divide_their_conversions():
    """A sale with no causal channel still has to be credited somewhere.

    Nothing caused it, so no division is correct and an even split is the
    least-wrong one. What matters is that the revenue is not silently dropped,
    which would leave the key summing to less than the models divide.
    """
    # Zero influence means the base conversion rate only, so conversions are
    # scarce and the split is noisy. Enough users to see past that.
    _, truth = generate_events(users=50_000, channels={"a": (0.6, 0.0), "b": (0.6, 0.0)}, seed=3)
    assert sum(truth.values()) == pytest.approx(1.0, abs=0.01)
    assert truth["a"] == pytest.approx(truth["b"], abs=0.05)
