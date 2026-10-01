"""Incrementality: what a channel actually caused.

Attribution divides credit for conversions that already happened. It cannot
tell you whether those conversions would have happened anyway - and for most
channels, a large share would. A holdout test can: withhold the channel from
a randomised control group and compare.

This module does the statistics for a two-group holdout: lift, incremental
conversions, a confidence interval and a significance test. It is deliberately
dependency-free - the maths is a two-proportion z-test, not a library.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# z values for common two-sided confidence levels
_Z = {0.80: 1.2816, 0.90: 1.6449, 0.95: 1.9600, 0.99: 2.5758}


@dataclass(slots=True)
class HoldoutResult:
    """Outcome of one incrementality test."""

    treatment_users: int
    treatment_conversions: int
    control_users: int
    control_conversions: int
    confidence: float

    treatment_rate: float
    control_rate: float
    absolute_lift: float
    relative_lift: float
    incremental_conversions: float
    ci_low: float
    ci_high: float
    p_value: float
    significant: bool

    def summary(self) -> str:
        return "\n".join(
            [
                f"treatment : {self.treatment_conversions:,}/{self.treatment_users:,} = {self.treatment_rate:.4%}",
                f"control   : {self.control_conversions:,}/{self.control_users:,} = {self.control_rate:.4%}",
                f"lift      : {self.relative_lift:+.2%} relative ({self.absolute_lift:+.4%} absolute)",
                f"{int(self.confidence * 100)}% CI   : [{self.ci_low:+.4%}, {self.ci_high:+.4%}] absolute",
                f"incremental conversions: {self.incremental_conversions:,.0f}",
                f"p-value   : {self.p_value:.4f} -> {'significant' if self.significant else 'not significant'}",
            ]
        )


def _normal_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def holdout_test(
    treatment_users: int,
    treatment_conversions: int,
    control_users: int,
    control_conversions: int,
    confidence: float = 0.95,
) -> HoldoutResult:
    """Compare a treated group against a holdout.

    Returns lift, a confidence interval on the absolute difference in
    conversion rate, and the incremental conversions implied for the treated
    population. A negative lower bound means you cannot rule out that the
    channel did nothing - which is the result most teams least want and most
    need to see.
    """
    if treatment_users <= 0 or control_users <= 0:
        raise ValueError("both groups need at least one user")
    if confidence not in _Z:
        raise ValueError(f"confidence must be one of {sorted(_Z)}")

    p_treatment = treatment_conversions / treatment_users
    p_control = control_conversions / control_users
    absolute = p_treatment - p_control
    relative = 0.0 if p_control == 0 else absolute / p_control

    standard_error = math.sqrt(
        p_treatment * (1 - p_treatment) / treatment_users
        + p_control * (1 - p_control) / control_users
    )
    z = _Z[confidence]
    margin = z * standard_error

    # pooled proportion for the significance test
    pooled = (treatment_conversions + control_conversions) / (treatment_users + control_users)
    pooled_se = math.sqrt(pooled * (1 - pooled) * (1 / treatment_users + 1 / control_users))
    z_stat = 0.0 if pooled_se == 0 else absolute / pooled_se
    p_value = 2 * (1 - _normal_cdf(abs(z_stat)))

    return HoldoutResult(
        treatment_users=treatment_users,
        treatment_conversions=treatment_conversions,
        control_users=control_users,
        control_conversions=control_conversions,
        confidence=confidence,
        treatment_rate=p_treatment,
        control_rate=p_control,
        absolute_lift=absolute,
        relative_lift=relative,
        incremental_conversions=absolute * treatment_users,
        ci_low=absolute - margin,
        ci_high=absolute + margin,
        p_value=p_value,
        significant=p_value < (1 - confidence),
    )


def required_sample_size(
    baseline_rate: float,
    minimum_detectable_lift: float,
    confidence: float = 0.95,
    power: float = 0.80,
) -> int:
    """Users needed per group to detect a given relative lift.

    Run this before the test, not after. Most "inconclusive" holdouts were
    never large enough to conclude anything.
    """
    if not 0 < baseline_rate < 1:
        raise ValueError("baseline_rate must be between 0 and 1")
    if minimum_detectable_lift <= 0:
        raise ValueError("minimum_detectable_lift must be positive")

    z_alpha = _Z[confidence]
    z_beta = {0.80: 0.8416, 0.90: 1.2816, 0.95: 1.6449}[power]

    p1 = baseline_rate
    p2 = baseline_rate * (1 + minimum_detectable_lift)
    pooled = (p1 + p2) / 2

    numerator = (
        z_alpha * math.sqrt(2 * pooled * (1 - pooled))
        + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2
    return math.ceil(numerator / ((p2 - p1) ** 2))


def compare_to_attribution(holdout: HoldoutResult, attributed_conversions: float) -> dict:
    """How much of the attributed credit was actually incremental.

    A ratio well below 1 means the model is handing a channel credit for
    conversions that would have happened without it - the single most common
    way attribution misleads a budget decision.
    """
    incremental = holdout.incremental_conversions
    ratio = 0.0 if attributed_conversions == 0 else incremental / attributed_conversions
    return {
        "attributed_conversions": round(attributed_conversions, 2),
        "incremental_conversions": round(incremental, 2),
        "incrementality_ratio": round(ratio, 3),
        "overstated_by": round(attributed_conversions - incremental, 2),
    }
