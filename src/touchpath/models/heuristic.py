"""Rule-based attribution: first, last, linear, time-decay, position-based.

These are the models every marketing team starts with. They are cheap,
explainable and wrong in known ways - last touch flatters the bottom of the
funnel, first touch flatters the top. touchpath implements them so they can
be compared directly against Markov and Shapley on the same paths.

Every model splits each conversion's credit into shares that sum to 1, so
total attributed revenue always equals total actual revenue.
"""

from __future__ import annotations

import math

from ..schema import DIRECT
from .base import AttributionResult, credit


def _shares_first(channels):
    return [(channels[0], 1.0)]


def _shares_last(channels):
    return [(channels[-1], 1.0)]


def _shares_linear(channels):
    weight = 1.0 / len(channels)
    return [(channel, weight) for channel in channels]


def _shares_position(channels, first_weight: float, last_weight: float):
    """40/20/40 by default: first and last touch carry most of the credit,
    the middle shares the rest."""
    if len(channels) == 1:
        return [(channels[0], 1.0)]
    if len(channels) == 2:
        total = first_weight + last_weight
        return [(channels[0], first_weight / total), (channels[1], last_weight / total)]

    middle = channels[1:-1]
    middle_weight = (1.0 - first_weight - last_weight) / len(middle)
    shares = [(channels[0], first_weight), (channels[-1], last_weight)]
    shares.extend((channel, middle_weight) for channel in middle)
    return shares


def _shares_time_decay(path, half_life_days: float):
    """Exponential decay on time to conversion: a touch one half-life before
    the conversion gets half the weight of a touch at conversion time.

    Needs timestamps, so it reconstructs them from the path's touch order when
    exact times are not carried. With only channel order available, position in
    the path is used as the decay axis.
    """
    channels = path.channels
    n = len(channels)
    weights = [math.pow(0.5, (n - 1 - i) / max(half_life_days, 1e-9)) for i in range(n)]
    total = sum(weights)
    return [(channel, weight / total) for channel, weight in zip(channels, weights)]


def attribute(paths, model: str = "last", **kwargs) -> AttributionResult:
    """Run one heuristic model over paths.

    model: first | last | linear | position | time_decay
    kwargs: first_weight / last_weight (position), half_life_days (time_decay)
    """
    model = model.lower().replace("-", "_")
    result = AttributionResult(model=model)

    for path in paths:
        if path.is_direct:
            credit(result, DIRECT, 1.0, path.revenue)
            continue

        channels = list(path.channels)
        if model == "first":
            shares = _shares_first(channels)
        elif model == "last":
            shares = _shares_last(channels)
        elif model == "linear":
            shares = _shares_linear(channels)
        elif model == "position":
            shares = _shares_position(
                channels,
                kwargs.get("first_weight", 0.4),
                kwargs.get("last_weight", 0.4),
            )
        elif model == "time_decay":
            shares = _shares_time_decay(path, kwargs.get("half_life_days", 7.0))
        else:
            raise ValueError(
                f"unknown model '{model}' - expected first, last, linear, position or time_decay"
            )

        for channel, share in shares:
            credit(result, channel, share, path.revenue * share)

    result.meta["paths"] = len(paths)
    return result


def compare(paths, models=("first", "last", "linear", "position", "time_decay")):
    """Run several models over the same paths.

    The spread between models is the honest answer to 'which channel works' -
    a channel that looks strong under every model is a safer bet than one that
    only wins under last touch.
    """
    return {name: attribute(paths, model=name) for name in models}
