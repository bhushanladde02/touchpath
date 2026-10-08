"""Synthetic event generator with known ground truth.

Attribution models are hard to validate because real data has no answer key.
This generator simulates journeys from an explicit model - each channel has a
true conversion influence - so model output can be scored against the values
that produced the data.

It also injects the kinds of damage real feeds carry (bad timestamps, missing
ids, text revenue) so ingestion gets tested on something realistic.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

# channel -> (how often it appears, how much it moves conversion odds)
DEFAULT_CHANNELS = {
    "paid_search": (0.30, 0.45),
    "paid_social": (0.25, 0.25),
    "display": (0.20, 0.08),
    "email": (0.15, 0.35),
    "affiliate": (0.10, 0.15),
    "organic_search": (0.22, 0.30),
}

_BROKEN_TIMESTAMPS = ["", "not-a-date", "2026-13-45 99:99:99", None, "yesterday"]


def generate_events(
    users: int = 5_000,
    days: int = 60,
    channels=None,
    base_conversion_rate: float = 0.02,
    revenue_mean: float = 120.0,
    corruption_rate: float = 0.0,
    seed: int = 42,
    start: datetime | None = None,
):
    """Simulate journeys and return ``(records, ground_truth)``.

    Args:
        users: How many user journeys to simulate.
        days: Spread of journey *start* times, over ``0`` to ``days * 0.7``.
            Not the span of the output: touches are spaced by an exponential
            draw averaging 2.5 days and a conversion lags the last touch
            again, so the observed window routinely exceeds ``days`` by a
            fortnight or more. Read the real span off the event timestamps.
        channels: ``{name: (frequency, influence)}``. Frequency is how often the
            channel appears in a journey; influence is how much it moves the odds
            of conversion. Defaults to a balanced six-channel mix.
        base_conversion_rate: Conversion probability before any channel influence.
        revenue_mean: Mean of the lognormal revenue distribution.
        corruption_rate: Share of rows to damage, so a pipeline can be tested
            against dirty input rather than a clean fixture.
        seed: Fixed for reproducibility.
        start: First timestamp in the simulated period.

    Returns:
        A tuple of ``records`` (dicts ready for
        :func:`touchpath.ingest.ingest_records`) and ``ground_truth``.

        ``ground_truth`` is ``{channel: share of converted revenue}``: each
        conversion's revenue split across the channels that caused it, in
        proportion to their influence, then normalised. That is deliberately
        the same quantity a model reports — revenue share over converting
        journeys — so the two can be subtracted. Scoring a model against
        anything else, influence-weighted exposure over all journeys for
        instance, compares two different measurements and flatters whichever
        model happens to track the wrong one.
    """
    rng = random.Random(seed)
    channels = channels or DEFAULT_CHANNELS
    start = start or datetime(2026, 1, 1)

    records = []
    # Revenue credited to each channel for the conversions it actually helped
    # cause. Deliberately not a count of touches: a model divides revenue among
    # converting journeys, so the answer key has to be the same quantity over
    # the same population or the two are not comparable. Summing influence over
    # every journey instead would measure influence-weighted *exposure*, which
    # includes journeys that never converted and which no attribution model is
    # trying to estimate.
    credited_revenue = {channel: 0.0 for channel in channels}

    for user_index in range(users):
        user_id = f"u{user_index:07d}"
        journey_start = start + timedelta(days=rng.uniform(0, days * 0.7))

        touched = [channel for channel, (frequency, _) in channels.items() if rng.random() < frequency]
        if not touched:
            continue
        rng.shuffle(touched)

        offset = 0.0
        for channel in touched:
            offset += rng.expovariate(1 / 2.5)  # days between touches
            ts = journey_start + timedelta(days=offset)
            records.append(
                {
                    "user_id": user_id,
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "event_type": "click" if rng.random() < 0.4 else "impression",
                    "channel": channel,
                    "campaign": f"{channel}_q1",
                    "event_id": f"t{len(records):08d}",
                }
            )

        # conversion probability rises with the influence of channels touched
        influence = sum(channels[channel][1] for channel in touched)
        probability = 1 - (1 - base_conversion_rate) ** (1 + influence * 4)

        if rng.random() < probability:
            offset += rng.expovariate(1 / 1.5)
            ts = journey_start + timedelta(days=offset)
            revenue = round(rng.lognormvariate(0, 0.6) * revenue_mean, 2)
            records.append(
                {
                    "user_id": user_id,
                    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                    "event_type": "purchase",
                    "revenue": revenue,
                    "event_id": f"c{len(records):08d}",
                }
            )
            # Split this conversion's revenue across the channels that produced
            # it, in proportion to the influence that produced it. A perfect
            # model recovers exactly this. When every touched channel has zero
            # influence the sale happened at the base rate and no channel caused
            # it; an even split is the least-wrong answer available, and no
            # model could do better.
            if influence > 0:
                for channel in touched:
                    credited_revenue[channel] += revenue * channels[channel][1] / influence
            else:
                for channel in touched:
                    credited_revenue[channel] += revenue / len(touched)

    if corruption_rate > 0:
        for _ in range(int(len(records) * corruption_rate)):
            victim = dict(rng.choice(records))
            damage = rng.choice(["timestamp", "user", "revenue", "type"])
            if damage == "timestamp":
                victim["timestamp"] = rng.choice(_BROKEN_TIMESTAMPS)
            elif damage == "user":
                victim.pop("user_id", None)
            elif damage == "revenue":
                victim["revenue"] = rng.choice(["N/A", "twelve", "-50"])
            else:
                victim["event_type"] = rng.choice(["", "unknown_thing", None])
            records.append(victim)

    rng.shuffle(records)

    # Computed from the clean simulation, before corruption is applied. Truth
    # is what the simulation did; corruption is a measurement problem, and the
    # rows it destroys put a floor under how well any model can score. So does
    # the lookback window, which clips journeys the simulation never clipped.
    total_credited = sum(credited_revenue.values()) or 1.0
    ground_truth = {
        channel: round(value / total_credited, 4)
        for channel, value in sorted(credited_revenue.items())
    }
    return records, ground_truth


def generate_holdout(
    users_per_group: int = 50_000,
    control_rate: float = 0.020,
    true_lift: float = 0.15,
    seed: int = 42,
):
    """Simulate a holdout test with a known true lift, for validating the
    incrementality maths against an answer you already know."""
    rng = random.Random(seed)
    treatment_rate = control_rate * (1 + true_lift)

    control_conversions = sum(1 for _ in range(users_per_group) if rng.random() < control_rate)
    treatment_conversions = sum(1 for _ in range(users_per_group) if rng.random() < treatment_rate)

    return {
        "treatment_users": users_per_group,
        "treatment_conversions": treatment_conversions,
        "control_users": users_per_group,
        "control_conversions": control_conversions,
        "true_lift": true_lift,
    }
