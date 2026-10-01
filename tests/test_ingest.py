import json

from touchpath.generate import generate_events
from touchpath.ingest import ingest_file, ingest_records, ingest_sources


GOOD = {"user_id": "u1", "timestamp": "2026-09-14T10:00:00", "event_type": "click", "channel": "email"}


def test_report_counts_everything():
    events, report = ingest_records([GOOD, dict(GOOD), {"event_type": "click"}])
    assert len(events) == 2
    assert report.total == 3 and report.accepted == 2 and report.rejected == 1
    assert abs(report.reject_rate - 1 / 3) < 1e-9


def test_reasons_are_itemised():
    _, report = ingest_records([{"user_id": "u1"}, {"user_id": "u2"}, GOOD])
    assert report.reasons["missing timestamp"] == 2


def test_empty_input_is_not_an_error():
    events, report = ingest_records([])
    assert events == [] and report.total == 0 and report.reject_rate == 0.0


def test_reads_json_and_csv(tmp_path):
    records, _ = generate_events(users=200, seed=3)

    json_path = tmp_path / "events.json"
    json_path.write_text(json.dumps(records))
    events, report = ingest_file(json_path)
    assert report.accepted == len(events) > 0

    csv_path = tmp_path / "events.csv"
    columns = ["user_id", "timestamp", "event_type", "channel", "campaign", "revenue", "event_id"]
    lines = [",".join(columns)]
    for record in records:
        lines.append(",".join(str(record.get(c, "")) for c in columns))
    csv_path.write_text("\n".join(lines))
    csv_events, csv_report = ingest_file(csv_path)
    assert csv_report.accepted == report.accepted


def test_several_sources_merge_into_one_sorted_stream(tmp_path):
    for name in ("a", "b"):
        records, _ = generate_events(users=100, seed=1 if name == "a" else 2)
        (tmp_path / f"{name}.json").write_text(json.dumps(records))

    events, report = ingest_sources({"a": tmp_path / "a.json", "b": tmp_path / "b.json"})
    assert report.by_source["a"] > 0 and report.by_source["b"] > 0
    assert events == sorted(events, key=lambda e: (e.user_id, e.ts))


def test_corrupt_feed_is_quarantined_not_fatal():
    records, _ = generate_events(users=500, corruption_rate=0.2, seed=5)
    events, report = ingest_records(records)
    assert report.rejected > 0
    assert report.accepted > 0
    assert report.accepted + report.rejected == report.total
