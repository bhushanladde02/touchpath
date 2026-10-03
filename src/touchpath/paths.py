"""Journey construction: events in, conversion paths out.

A path is the ordered list of channels a user touched before a conversion,
inside the lookback window. Every attribution model in touchpath consumes
paths, so the windowing and de-duplication rules live in one place.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from .schema import DIRECT, Event


@dataclass(frozen=True, slots=True)
class Path:
    """One conversion and the touches credited with it."""

    user_id: str
    converted_at: datetime
    revenue: float
    channels: tuple[str, ...]
    conversion_id: str = ""

    @property
    def is_direct(self) -> bool:
        return len(self.channels) == 0

    @property
    def length(self) -> int:
        return len(self.channels)

    @property
    def date(self) -> str:
        return self.converted_at.date().isoformat()


def _index_touches(events):
    """{user: (sorted timestamps, channels in the same order)}.

    Built once so each conversion is a binary search rather than a scan.
    """
    by_user: dict[str, list[tuple[datetime, str]]] = {}
    for event in events:
        if event.is_touch:
            by_user.setdefault(event.user_id, []).append((event.ts, event.channel))

    index: dict[str, tuple[list[datetime], list[str]]] = {}
    for user, touches in by_user.items():
        touches.sort(key=lambda pair: pair[0])
        index[user] = ([ts for ts, _ in touches], [channel for _, channel in touches])
    return index


def build_paths(
    events,
    lookback_days: int | None = 30,
    dedupe_consecutive: bool = True,
    max_path_length: int | None = None,
):
    """Build one Path per conversion.

    lookback_days       only touches within this window before the conversion count
                        (None means no limit)
    dedupe_consecutive  collapse repeats of the same channel in a row, so ten
                        impressions from one source do not swamp the path
    max_path_length     keep only the most recent N touches
    """
    index = _index_touches(events)
    window = None if lookback_days is None else timedelta(days=lookback_days)
    paths: list[Path] = []

    for event in events:
        if not event.is_conversion:
            continue

        channels: list[str] = []
        if event.user_id in index:
            timestamps, labels = index[event.user_id]
            high = bisect_right(timestamps, event.ts)
            low = 0 if window is None else bisect_left(timestamps, event.ts - window)
            channels = labels[low:high]

        if dedupe_consecutive:
            collapsed: list[str] = []
            for channel in channels:
                if not collapsed or collapsed[-1] != channel:
                    collapsed.append(channel)
            channels = collapsed

        if max_path_length is not None and len(channels) > max_path_length:
            channels = channels[-max_path_length:]

        paths.append(
            Path(
                user_id=event.user_id,
                converted_at=event.ts,
                revenue=event.revenue,
                channels=tuple(channels),
                conversion_id=event.event_id,
            )
        )

    paths.sort(key=lambda p: (p.converted_at, p.user_id))
    return paths


def path_stats(paths):
    """Headline numbers for a set of paths - the sanity check you run first."""
    if not paths:
        return {
            "conversions": 0,
            "revenue": 0.0,
            "direct_conversions": 0,
            "avg_path_length": 0.0,
            "max_path_length": 0,
            "unique_channels": 0,
        }

    lengths = [p.length for p in paths]
    channels = {channel for p in paths for channel in p.channels}
    return {
        "conversions": len(paths),
        "revenue": round(sum(p.revenue for p in paths), 2),
        "direct_conversions": sum(1 for p in paths if p.is_direct),
        "avg_path_length": round(sum(lengths) / len(lengths), 2),
        "max_path_length": max(lengths),
        "unique_channels": len(channels),
    }


def non_converting_journeys(events, dedupe_consecutive: bool = True):
    """Channel sequences for users who never converted.

    The Markov removal effect is only honest when it can see these. Computed
    on converting paths alone, a channel that appears constantly in dead ends
    looks valuable, because every path it sits in ended in a conversion by
    definition. Passing these to markov.attribute is what lets the model
    penalise it instead.

    Returns a list of channel tuples, one per non-converting user.
    """
    converted = {event.user_id for event in events if event.is_conversion}
    index = _index_touches(events)

    journeys: list[tuple[str, ...]] = []
    for user, (_, labels) in index.items():
        if user in converted:
            continue

        channels = labels
        if dedupe_consecutive:
            collapsed: list[str] = []
            for channel in labels:
                if not collapsed or collapsed[-1] != channel:
                    collapsed.append(channel)
            channels = collapsed

        if channels:
            journeys.append(tuple(channels))
    return journeys


def channel_universe(paths):
    """Every channel seen, plus 'direct' when some conversions had no touch."""
    channels = sorted({channel for p in paths for channel in p.channels})
    if any(p.is_direct for p in paths):
        channels.append(DIRECT)
    return channels
