from datetime import datetime, timedelta

from touchpath.paths import build_paths, channel_universe, path_stats
from touchpath.schema import Event

BASE = datetime(2026, 9, 1)


def event(user, days, kind, channel="unknown", revenue=0.0):
    return Event(user_id=user, ts=BASE + timedelta(days=days), event_type=kind, channel=channel, revenue=revenue)


def test_path_is_ordered_and_windowed():
    events = [
        event("u1", 0, "impression", "display"),
        event("u1", 10, "click", "paid_search"),
        event("u1", 20, "click", "email"),
        event("u1", 25, "purchase", revenue=100.0),
    ]
    paths = build_paths(events, lookback_days=30)
    assert len(paths) == 1
    assert paths[0].channels == ("display", "paid_search", "email")

    windowed = build_paths(events, lookback_days=7)
    assert windowed[0].channels == ("email",)


def test_touches_after_the_conversion_do_not_count():
    events = [
        event("u1", 1, "click", "email"),
        event("u1", 5, "purchase", revenue=50.0),
        event("u1", 9, "click", "display"),
    ]
    assert build_paths(events)[0].channels == ("email",)


def test_conversion_with_no_prior_touch_is_direct():
    paths = build_paths([event("u2", 3, "purchase", revenue=25.0)])
    assert paths[0].is_direct and paths[0].channels == ()


def test_consecutive_duplicates_collapse_by_default():
    events = [
        event("u1", 1, "impression", "display"),
        event("u1", 2, "impression", "display"),
        event("u1", 3, "click", "email"),
        event("u1", 4, "purchase", revenue=10.0),
    ]
    assert build_paths(events)[0].channels == ("display", "email")
    assert build_paths(events, dedupe_consecutive=False)[0].channels == ("display", "display", "email")


def test_max_path_length_keeps_the_most_recent_touches():
    events = [event("u1", i, "click", f"c{i}") for i in range(5)]
    events.append(event("u1", 6, "purchase", revenue=10.0))
    assert build_paths(events, max_path_length=2)[0].channels == ("c3", "c4")


def test_users_do_not_leak_into_each_other():
    events = [
        event("u1", 1, "click", "email"),
        event("u2", 2, "click", "display"),
        event("u2", 3, "purchase", revenue=10.0),
    ]
    paths = build_paths(events)
    assert len(paths) == 1 and paths[0].channels == ("display",)


def test_stats_and_universe():
    events = [
        event("u1", 1, "click", "email"),
        event("u1", 2, "purchase", revenue=100.0),
        event("u2", 3, "purchase", revenue=50.0),
    ]
    paths = build_paths(events)
    stats = path_stats(paths)
    assert stats["conversions"] == 2 and stats["revenue"] == 150.0 and stats["direct_conversions"] == 1
    assert channel_universe(paths) == ["email", "direct"]


def test_stats_on_empty_input():
    assert path_stats([])["conversions"] == 0
