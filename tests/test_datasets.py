"""The sample datasets and the pages that serve them."""

import json

import pytest
from fastapi.testclient import TestClient

from touchpath import datasets
from touchpath.ingest import ingest_records
from touchpath.models import heuristic
from touchpath.paths import build_paths, non_converting_journeys, path_stats
from touchpath.web.app import app

client = TestClient(app)


def test_every_sample_builds_and_ingests():
    for sample in datasets.SAMPLES:
        records, truth, meta = datasets.build(sample.slug)
        assert records, f"{sample.slug} produced no records"
        assert meta.slug == sample.slug

        events, report = ingest_records(records)
        assert events, f"{sample.slug} produced nothing usable"
        # ground truth is a share, so it sums to 1
        assert abs(sum(truth.values()) - 1.0) < 0.01


def test_samples_are_deterministic():
    first, truth_a, _ = datasets.build("retail-baseline")
    second, truth_b, _ = datasets.build("retail-baseline")
    assert len(first) == len(second)
    assert truth_a == truth_b
    assert first[0] == second[0]


def test_unknown_sample_raises():
    with pytest.raises(KeyError):
        datasets.build("no-such-dataset")


def test_messy_feed_actually_rejects_rows():
    records, _, _ = datasets.build("messy-feed")
    _, report = ingest_records(records)
    assert report.rejected > 0
    assert report.reject_rate > 0.05
    assert report.reasons, "rejections must carry reasons"


def test_short_paths_are_short_and_long_consideration_is_long():
    short, _, _ = datasets.build("short-paths")
    long_, _, _ = datasets.build("long-consideration")

    short_stats = path_stats(build_paths(ingest_records(short)[0], lookback_days=30))
    long_stats = path_stats(build_paths(ingest_records(long_)[0], lookback_days=30))

    assert short_stats["avg_path_length"] < 1.6
    assert long_stats["avg_path_length"] > 2.5
    assert long_stats["avg_path_length"] > short_stats["avg_path_length"]


def test_last_touch_trap_over_credits_the_closing_channel():
    """The point of the sample: last touch gives branded search far more than
    its true influence. If this stops being true the sample is lying."""
    records, truth, _ = datasets.build("last-touch-trap")
    events, _ = ingest_records(records)
    paths = build_paths(events, lookback_days=30)
    last = heuristic.attribute(paths, "last").share()

    assert truth["branded_search"] < 0.12
    assert last["branded_search"] > 0.25
    assert last["branded_search"] > truth["branded_search"] * 2


def test_non_converting_journeys_are_found():
    records, _, _ = datasets.build("retail-baseline")
    events, _ = ingest_records(records)
    journeys = non_converting_journeys(events)

    assert journeys, "a 2% conversion rate must leave non-converting journeys"
    assert all(isinstance(j, tuple) and j for j in journeys)

    converted = {e.user_id for e in events if e.is_conversion}
    assert len(journeys) + len(converted) <= len({e.user_id for e in events if e.is_touch}) + 1


def test_catalogue_matches_samples():
    cards = datasets.catalogue()
    assert len(cards) == len(datasets.SAMPLES)
    for card in cards:
        assert card["slug"] in datasets.BY_SLUG
        assert card["summary"] and card["shows"]


def test_write_all(tmp_path):
    written = datasets.write_all(tmp_path)
    assert len(written) == len(datasets.SAMPLES)
    for path in written:
        assert path.exists()
        with open(path) as handle:
            records = json.load(handle)
        assert isinstance(records, list) and records


# ----------------------------------------------------------------- web layer


def test_about_page_renders():
    response = client.get("/about")
    assert response.status_code == 200
    assert "attribution" in response.text.lower()


def test_datasets_page_lists_every_sample():
    response = client.get("/datasets")
    assert response.status_code == 200
    for sample in datasets.SAMPLES:
        assert sample.name in response.text
        assert f"/datasets/{sample.slug}.json" in response.text


def test_sample_download():
    response = client.get("/datasets/short-paths.json")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    records = response.json()
    assert isinstance(records, list) and records
    assert "user_id" in records[0] or "timestamp" in records[0]


def test_unknown_sample_download_is_404():
    assert client.get("/datasets/nope.json").status_code == 404


def test_analyze_runs_a_sample():
    response = client.post(
        "/analyze",
        data={
            "source": "sample",
            "sample": "retail-baseline",
            "lookback_days": "30",
            "models": ["last", "markov"],
        },
    )
    assert response.status_code == 200
    assert "Retail baseline" in response.text
    # ground truth must come through, since that is the point of the samples
    assert "Truth" in response.text


def test_dashboard_offers_the_samples():
    response = client.get("/dashboard")
    assert response.status_code == 200
    for sample in datasets.SAMPLES:
        assert sample.name in response.text
