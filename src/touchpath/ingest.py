"""Ingestion: raw records in, validated events plus a reject report out."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .schema import Event, FieldMap, parse_event


@dataclass(slots=True)
class IngestReport:
    """What happened during a load. Printed by the CLI, asserted in tests,
    and the thing you alert on in production."""

    total: int = 0
    accepted: int = 0
    rejected: int = 0
    reasons: Counter = field(default_factory=Counter)
    by_source: Counter = field(default_factory=Counter)

    @property
    def reject_rate(self) -> float:
        return 0.0 if self.total == 0 else self.rejected / self.total

    def summary(self) -> str:
        lines = [
            f"records   : {self.total}",
            f"accepted  : {self.accepted}",
            f"rejected  : {self.rejected} ({self.reject_rate:.1%})",
        ]
        for reason, count in self.reasons.most_common():
            lines.append(f"    - {reason}: {count}")
        return "\n".join(lines)


def ingest_records(records, mapping: FieldMap | None = None, source: str = "unknown"):
    """Normalise an iterable of raw records.

    Returns ``(events, report)``. Bad rows never raise; they are counted by
    reason so a feed that quietly changes format is visible the same day.
    """
    events: list[Event] = []
    report = IngestReport()

    for raw in records:
        report.total += 1
        event, reason = parse_event(raw, mapping=mapping, source=source)
        if event is None:
            report.rejected += 1
            report.reasons[reason] += 1
        else:
            events.append(event)
            report.accepted += 1
            report.by_source[event.source] += 1

    return events, report


def _read_json(path: Path):
    text = path.read_text()
    stripped = text.lstrip()
    if stripped.startswith("["):
        return json.loads(text)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def ingest_file(path, mapping: FieldMap | None = None, source: str | None = None):
    """Load .json, .jsonl, .csv or .parquet into events.

    Parquet goes through DuckDB so a file larger than memory still works.
    """
    path = Path(path)
    name = source or path.stem

    if path.suffix in (".json", ".jsonl", ".ndjson"):
        records = _read_json(path)
    elif path.suffix in (".csv", ".tsv"):
        delimiter = "\t" if path.suffix == ".tsv" else ","
        with path.open(newline="") as handle:
            records = list(csv.DictReader(handle, delimiter=delimiter))
    elif path.suffix == ".parquet":
        import duckdb

        rows = duckdb.sql(f"SELECT * FROM read_parquet('{path}')").fetchall()
        columns = [d[0] for d in duckdb.sql(f"SELECT * FROM read_parquet('{path}') LIMIT 0").description]
        records = [dict(zip(columns, row)) for row in rows]
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")

    return ingest_records(records, mapping=mapping, source=name)


def ingest_sources(sources, mapping_by_source=None):
    """Load several vendor files into one event stream.

    ``sources`` is {name: path}; ``mapping_by_source`` is {name: FieldMap}.
    The merged report keeps per-reason counts across all of them.
    """
    mapping_by_source = mapping_by_source or {}
    all_events: list[Event] = []
    merged = IngestReport()

    for name, path in sources.items():
        events, report = ingest_file(path, mapping=mapping_by_source.get(name), source=name)
        all_events.extend(events)
        merged.total += report.total
        merged.accepted += report.accepted
        merged.rejected += report.rejected
        merged.reasons.update(report.reasons)
        merged.by_source.update(report.by_source)

    all_events.sort(key=lambda e: (e.user_id, e.ts))
    return all_events, merged
