"""Markov-chain attribution via the removal effect.

The idea: model customer journeys as a first-order Markov chain over channel
states, with absorbing states for conversion and for dropping out. The value
of a channel is how much the overall conversion probability falls when that
channel is removed from the graph - the "removal effect".

Unlike the heuristics, this answers a counterfactual: what happens to total
conversions if we switch this channel off? That is much closer to the question
a marketer actually has, and it is why Markov attribution is a standard tool
in measurement work rather than a rule of thumb.

Both converting and non-converting journeys are used: a channel that appears
mostly in journeys that go nowhere should not be rewarded for it.
"""

from __future__ import annotations

from ..schema import DIRECT
from .base import AttributionResult

START = "__start__"
CONVERSION = "__conversion__"
NULL = "__null__"


def _transition_counts(journeys):
    """journeys: [(channels, converted)] -> {state: {next_state: count}}."""
    counts: dict[str, dict[str, int]] = {}

    for channels, converted in journeys:
        states = [START] + list(channels) + [CONVERSION if converted else NULL]
        for current, nxt in zip(states, states[1:]):
            row = counts.setdefault(current, {})
            row[nxt] = row.get(nxt, 0) + 1

    return counts


def _transition_matrix(counts):
    """Counts to probabilities, row by row."""
    matrix: dict[str, dict[str, float]] = {}
    for state, row in counts.items():
        total = sum(row.values())
        if total:
            matrix[state] = {nxt: value / total for nxt, value in row.items()}
    return matrix


def _conversion_probability(matrix, removed: str | None = None, max_iter: int = 1000, tol: float = 1e-10):
    """Probability of reaching CONVERSION from START.

    Solved by iteration rather than matrix inversion: it is numerically stable,
    needs no dependencies, and converges quickly because journeys are short.
    Removing a channel means any path through it is redirected to NULL, which
    is exactly the counterfactual "this channel did not exist".
    """
    states = set(matrix)
    for row in matrix.values():
        states.update(row)
    states.discard(CONVERSION)
    states.discard(NULL)
    if removed is not None:
        states.discard(removed)

    # value[s] = probability of eventually converting, starting from s
    value = {state: 0.0 for state in states}

    for _ in range(max_iter):
        delta = 0.0
        for state in states:
            row = matrix.get(state)
            if not row:
                continue
            probability = 0.0
            for nxt, p in row.items():
                if nxt == CONVERSION:
                    probability += p
                elif nxt == NULL or nxt == removed:
                    continue  # absorbed without converting
                else:
                    probability += p * value.get(nxt, 0.0)
            delta = max(delta, abs(probability - value[state]))
            value[state] = probability
        if delta < tol:
            break

    return value.get(START, 0.0)


def removal_effects(journeys):
    """{channel: removal effect in [0, 1]} - the share of conversion
    probability lost when that channel is taken out of the graph."""
    matrix = _transition_matrix(_transition_counts(journeys))
    baseline = _conversion_probability(matrix)
    if baseline <= 0:
        return {}

    channels = {channel for channels, _ in journeys for channel in channels}
    effects = {}
    for channel in sorted(channels):
        without = _conversion_probability(matrix, removed=channel)
        effects[channel] = max(0.0, (baseline - without) / baseline)
    return effects


def attribute(paths, non_converting=None) -> AttributionResult:
    """Markov attribution over conversion paths.

    Credit is allocated in proportion to each channel's removal effect: the
    share of total conversion probability lost when that channel is removed
    from the transition graph. Conversions with no touches at all stay with
    ``direct``.

    Args:
        paths: Converting journeys, from :func:`touchpath.paths.build_paths`.
        non_converting: Optional channel tuples for journeys that never
            converted, from :func:`touchpath.paths.non_converting_journeys`.
            Including them is what lets the model penalise channels that appear
            mostly in dead ends — without them, every path in the sample ended
            in a conversion by definition.

    Returns:
        An :class:`~touchpath.models.base.AttributionResult`. Removal effects
        are available on ``result.meta["removal_effects"]``.
    """
    result = AttributionResult(model="markov")

    direct_conversions = sum(1 for p in paths if p.is_direct)
    direct_revenue = sum(p.revenue for p in paths if p.is_direct)
    attributable = [p for p in paths if not p.is_direct]

    if direct_conversions:
        result.conversions[DIRECT] = float(direct_conversions)
        result.revenue[DIRECT] = direct_revenue

    if not attributable:
        result.meta["note"] = "no non-direct paths"
        return result

    journeys = [(p.channels, True) for p in attributable]
    if non_converting:
        journeys.extend((tuple(channels), False) for channels in non_converting)

    effects = removal_effects(journeys)
    total_effect = sum(effects.values())
    total_conversions = float(len(attributable))
    total_revenue = sum(p.revenue for p in attributable)

    if total_effect <= 0:
        share = 1.0 / len(effects) if effects else 0.0
        effects = {channel: share for channel in effects}
        total_effect = sum(effects.values()) or 1.0

    for channel, effect in effects.items():
        weight = effect / total_effect
        result.conversions[channel] = result.conversions.get(channel, 0.0) + total_conversions * weight
        result.revenue[channel] = result.revenue.get(channel, 0.0) + total_revenue * weight

    result.meta["removal_effects"] = {k: round(v, 4) for k, v in effects.items()}
    result.meta["journeys"] = len(journeys)
    result.meta["non_converting"] = len(non_converting or [])
    return result
