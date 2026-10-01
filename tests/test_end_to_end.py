"""Whole-pipeline tests: dirty records in, attributed revenue out."""

import json

from touchpath import build_paths, ingest_records, path_stats
from touchpath.cli import main
from touchpath.generate import generate_events
from touchpath.models import heuristic, markov, shapley


def test_dirty_feed_runs_end_to_end_and_ties_out():
    records, truth = generate_events(users=2_000, corruption_rate=0.1, seed=17)

    events, report = ingest_records(records)
    assert report.rejected > 0 and report.accepted > report.rejected

    paths = build_paths(events, lookback_days=30)
    stats = path_stats(paths)
    assert stats["conversions"] > 0

    total = stats["revenue"]
    for result in (
        heuristic.attribute(paths, "linear"),
        heuristic.attribute(paths, "position"),
        markov.attribute(paths),
        shapley.attribute(paths),
    ):
        assert abs(result.total_revenue - total) < 0.01, result.model


def test_models_recover_the_strongest_channel_from_synthetic_data():
    records, truth = generate_events(users=6_000, seed=23)
    events, _ = ingest_records(records)
    paths = build_paths(events, lookback_days=30)

    strongest = max(truth, key=truth.get)
    for result in (heuristic.attribute(paths, "linear"), shapley.attribute(paths)):
        ranked = [channel for channel, _, _ in result.ranked() if channel != "direct"]
        assert strongest in ranked[:3], (result.model, ranked)


def test_lookback_window_only_ever_shrinks_the_paths():
    records, _ = generate_events(users=1_500, seed=31)
    events, _ = ingest_records(records)

    wide = path_stats(build_paths(events, lookback_days=90))
    narrow = path_stats(build_paths(events, lookback_days=3))
    assert narrow["avg_path_length"] <= wide["avg_path_length"]
    assert narrow["conversions"] == wide["conversions"]


def test_cli_demo_runs(capsys):
    assert main(["demo", "--users", "800"]) == 0
    out = capsys.readouterr().out
    assert "mean absolute error" in out


def test_cli_generate_report_attribute_compare(tmp_path, capsys):
    events_path = tmp_path / "events.json"
    assert main(["generate", "--users", "600", "--out", str(events_path)]) == 0
    assert json.loads(events_path.read_text())

    assert main(["report", str(events_path)]) == 0
    assert main(["attribute", str(events_path), "--model", "markov"]) == 0
    assert main(["compare", str(events_path), "--models", "last", "shapley"]) == 0
    out = capsys.readouterr().out
    assert "markov" in out


def test_cli_incrementality(capsys):
    assert main(["incrementality", "--treatment", "100000/2300", "--control", "100000/2000"]) == 0
    assert "significant" in capsys.readouterr().out
