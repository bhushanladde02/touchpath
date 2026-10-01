"""Shapley-value attribution.

Game theory's answer to "how much did each player contribute": a channel's
value is its average marginal contribution across every possible coalition of
channels. It is the only allocation satisfying efficiency, symmetry, the null
player property and additivity - which is why it keeps appearing in
measurement work despite the cost.

The characteristic function used here is the standard one for attribution:

    v(S) = total conversion value from journeys whose channel set is a
           subset of S

so a coalition is credited with the conversions it could have produced on its
own. Exact computation is 2^n in the number of channels; touchpath computes
exactly up to `exact_limit` channels and switches to Monte Carlo permutation
sampling above that, which is unbiased and converges as 1/sqrt(samples).
"""

from __future__ import annotations

import random
from itertools import combinations

from ..schema import DIRECT
from .base import AttributionResult


def _coalition_values(paths, use_revenue: bool = True):
    """{frozenset(channels): value} - the value each exact channel set produced."""
    values: dict[frozenset, float] = {}
    for path in paths:
        if path.is_direct:
            continue
        key = frozenset(path.channels)
        values[key] = values.get(key, 0.0) + (path.revenue if use_revenue else 1.0)
    return values


def _characteristic(coalition_values):
    """v(S): total value from journeys whose channels all appear in S."""
    def v(subset: frozenset) -> float:
        total = 0.0
        for channels, value in coalition_values.items():
            if channels <= subset:
                total += value
        return total

    return v


def _exact_shapley(channels, v):
    """Exact values by enumerating every coalition. O(2^n * n)."""
    import math

    n = len(channels)
    shapley = {channel: 0.0 for channel in channels}
    others = {channel: [c for c in channels if c != channel] for channel in channels}

    for channel in channels:
        rest = others[channel]
        for size in range(len(rest) + 1):
            weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            for subset in combinations(rest, size):
                coalition = frozenset(subset)
                marginal = v(coalition | {channel}) - v(coalition)
                shapley[channel] += weight * marginal

    return shapley


def _sampled_shapley(channels, v, samples: int, seed: int):
    """Monte Carlo over random permutations.

    Each permutation gives every channel one marginal contribution; averaging
    over permutations converges on the exact value without enumerating 2^n
    coalitions.
    """
    rng = random.Random(seed)
    shapley = {channel: 0.0 for channel in channels}
    order = list(channels)

    for _ in range(samples):
        rng.shuffle(order)
        coalition: set[str] = set()
        running = 0.0
        for channel in order:
            coalition.add(channel)
            value = v(frozenset(coalition))
            shapley[channel] += value - running
            running = value

    return {channel: total / samples for channel, total in shapley.items()}


def attribute(
    paths,
    exact_limit: int = 12,
    samples: int = 10_000,
    seed: int = 7,
) -> AttributionResult:
    """Shapley attribution over conversion paths.

    Credit is rescaled so attributed revenue equals actual revenue: Shapley
    values are already efficient in theory, but sampling and subset-based
    characteristic functions can drift slightly, and a model whose total does
    not tie out to the ledger will not survive its first review.
    """
    result = AttributionResult(model="shapley")

    direct = [p for p in paths if p.is_direct]
    attributable = [p for p in paths if not p.is_direct]

    if direct:
        result.conversions[DIRECT] = float(len(direct))
        result.revenue[DIRECT] = sum(p.revenue for p in direct)

    if not attributable:
        result.meta["note"] = "no non-direct paths"
        return result

    channels = sorted({channel for p in attributable for channel in p.channels})

    revenue_values = _coalition_values(attributable, use_revenue=True)
    conversion_values = _coalition_values(attributable, use_revenue=False)

    exact = len(channels) <= exact_limit
    method = "exact" if exact else f"sampled({samples})"

    for values, target in ((revenue_values, "revenue"), (conversion_values, "conversions")):
        v = _characteristic(values)
        raw = _exact_shapley(channels, v) if exact else _sampled_shapley(channels, v, samples, seed)

        total_raw = sum(max(0.0, value) for value in raw.values())
        actual = sum(values.values())
        bucket = result.revenue if target == "revenue" else result.conversions

        for channel in channels:
            value = max(0.0, raw[channel])
            scaled = 0.0 if total_raw == 0 else value / total_raw * actual
            bucket[channel] = bucket.get(channel, 0.0) + scaled

    result.meta["method"] = method
    result.meta["channels"] = len(channels)
    result.meta["distinct_coalitions"] = len(revenue_values)
    return result
