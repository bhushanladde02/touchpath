"""touchpath - multi-touch attribution for marketing measurement.

    from touchpath import ingest_file, build_paths
    from touchpath.models import heuristic, markov, shapley

    events, report = ingest_file("events.json")
    paths = build_paths(events, lookback_days=30)

    print(heuristic.attribute(paths, "linear").table())
    print(markov.attribute(paths).table())
    print(shapley.attribute(paths).table())
"""

from .schema import Event, FieldMap, parse_event, parse_timestamp
from .ingest import IngestReport, ingest_file, ingest_records, ingest_sources
from .paths import Path, build_paths, channel_universe, path_stats
from .models import AttributionResult

__version__ = "0.1.0"

__all__ = [
    "Event",
    "FieldMap",
    "parse_event",
    "parse_timestamp",
    "IngestReport",
    "ingest_file",
    "ingest_records",
    "ingest_sources",
    "Path",
    "build_paths",
    "channel_universe",
    "path_stats",
    "AttributionResult",
    "__version__",
]
