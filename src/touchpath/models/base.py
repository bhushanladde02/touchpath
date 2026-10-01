"""Shared result type for every attribution model."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class AttributionResult:
    """Credit assigned to each channel by one model.

    Holds both conversions and revenue because marketers ask for both, and
    keeps the model name so results from different models can be compared
    side by side without losing track of where each came from.
    """

    model: str
    conversions: dict[str, float] = field(default_factory=dict)
    revenue: dict[str, float] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    @property
    def total_conversions(self) -> float:
        return sum(self.conversions.values())

    @property
    def total_revenue(self) -> float:
        return sum(self.revenue.values())

    def share(self) -> dict[str, float]:
        """Each channel's share of revenue, which is what ends up in a deck."""
        total = self.total_revenue
        if total == 0:
            return {channel: 0.0 for channel in self.revenue}
        return {channel: value / total for channel, value in self.revenue.items()}

    def ranked(self):
        """[(channel, revenue, share)] sorted by revenue, ties by name."""
        shares = self.share()
        rows = [(channel, value, shares[channel]) for channel, value in self.revenue.items()]
        rows.sort(key=lambda row: (-row[1], row[0]))
        return rows

    def rounded(self, places: int = 2) -> "AttributionResult":
        return AttributionResult(
            model=self.model,
            conversions={k: round(v, places) for k, v in self.conversions.items()},
            revenue={k: round(v, places) for k, v in self.revenue.items()},
            meta=dict(self.meta),
        )

    def table(self) -> str:
        lines = [f"{self.model}", f"{'channel':<20}{'revenue':>14}{'share':>9}{'conv':>10}"]
        for channel, revenue, share in self.ranked():
            conversions = self.conversions.get(channel, 0.0)
            lines.append(f"{channel:<20}{revenue:>14,.2f}{share:>8.1%}{conversions:>10.2f}")
        lines.append(f"{'total':<20}{self.total_revenue:>14,.2f}{1.0:>8.1%}{self.total_conversions:>10.2f}")
        return "\n".join(lines)


def _blank(channels):
    return {channel: 0.0 for channel in channels}


def credit(result: AttributionResult, channel: str, conversions: float, revenue: float) -> None:
    result.conversions[channel] = result.conversions.get(channel, 0.0) + conversions
    result.revenue[channel] = result.revenue.get(channel, 0.0) + revenue
