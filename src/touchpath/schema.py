"""Canonical event schema and parsing.

Every vendor sends marketing data in a different shape. Everything in
touchpath works on one normalised record, so adding a new source means
writing a field mapping, not a new pipeline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

TOUCH_TYPES = frozenset({"impression", "click", "visit", "open"})
CONVERSION_TYPES = frozenset({"purchase", "conversion", "signup", "subscription"})

DIRECT = "direct"


@dataclass(frozen=True, slots=True)
class Event:
    """One normalised marketing event."""

    user_id: str
    ts: datetime
    event_type: str
    channel: str = "unknown"
    campaign: str = "unknown"
    revenue: float = 0.0
    event_id: str = ""
    source: str = "unknown"

    @property
    def is_touch(self) -> bool:
        return self.event_type in TOUCH_TYPES

    @property
    def is_conversion(self) -> bool:
        return self.event_type in CONVERSION_TYPES

    @property
    def date(self) -> str:
        return self.ts.date().isoformat()


class RejectReason:
    """Why a record could not be normalised. Rejects are counted, not dropped
    silently: a pipeline that loses rows without telling you is worse than one
    that fails."""

    MISSING_USER = "missing user_id"
    MISSING_TIMESTAMP = "missing timestamp"
    BAD_TIMESTAMP = "unparseable timestamp"
    MISSING_TYPE = "missing event_type"
    UNKNOWN_TYPE = "unknown event_type"
    BAD_REVENUE = "revenue not numeric"
    NEGATIVE_REVENUE = "negative revenue"
    NOT_AN_OBJECT = "record is not an object"


# Formats seen in the wild, tried in order. ISO-8601 is handled separately.
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y/%m/%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d-%b-%Y %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
)


def parse_timestamp(value) -> datetime | None:
    """Parse the timestamp formats vendors actually send.

    Accepts datetimes, epoch seconds or milliseconds, ISO-8601 (including a
    trailing Z), and the formats listed above. Returns None if nothing works,
    so the caller decides what a bad row means.
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value if value.tzinfo is None else value.astimezone(timezone.utc).replace(tzinfo=None)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000.0 if value > 1e11 else float(value)
        try:
            return datetime.utcfromtimestamp(seconds)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None

    if text.isdigit():
        number = int(text)
        seconds = number / 1000.0 if number > 1e11 else float(number)
        try:
            return datetime.utcfromtimestamp(seconds)
        except (OverflowError, OSError, ValueError):
            return None

    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(iso)
        return parsed if parsed.tzinfo is None else parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        pass

    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def normalise_label(value, default: str = "unknown") -> str:
    """Channel and campaign names arrive as 'Google Ads', ' google_ads ', 'GOOGLE ADS'."""
    if value is None:
        return default
    text = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text or default


@dataclass(slots=True)
class FieldMap:
    """Maps one vendor's field names onto the canonical schema.

    Values are dotted paths, so nested payloads work: ``customer.id``.
    """

    user_id: str = "user_id"
    ts: str = "timestamp"
    event_type: str = "event_type"
    channel: str = "channel"
    campaign: str = "campaign"
    revenue: str = "revenue"
    event_id: str = "event_id"
    type_aliases: dict[str, str] = field(default_factory=dict)


def get_path(record, path: str):
    """Read a nested value by dotted path; None if any step is missing."""
    current = record
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def parse_event(raw, mapping: FieldMap | None = None, source: str = "unknown"):
    """Normalise one record.

    Returns ``(Event, None)`` on success or ``(None, reason)`` on failure.
    Accepts a dict or a JSON string, because APIs hand back both.
    """
    mapping = mapping or FieldMap()

    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, RejectReason.NOT_AN_OBJECT
    if not isinstance(raw, dict):
        return None, RejectReason.NOT_AN_OBJECT

    user_id = get_path(raw, mapping.user_id)
    if user_id is None or str(user_id).strip() == "":
        return None, RejectReason.MISSING_USER

    raw_ts = get_path(raw, mapping.ts)
    if raw_ts is None or raw_ts == "":
        return None, RejectReason.MISSING_TIMESTAMP
    ts = parse_timestamp(raw_ts)
    if ts is None:
        return None, RejectReason.BAD_TIMESTAMP

    raw_type = get_path(raw, mapping.event_type)
    if raw_type is None or str(raw_type).strip() == "":
        return None, RejectReason.MISSING_TYPE
    event_type = normalise_label(raw_type)
    event_type = mapping.type_aliases.get(event_type, event_type)
    if event_type not in TOUCH_TYPES and event_type not in CONVERSION_TYPES:
        return None, RejectReason.UNKNOWN_TYPE

    raw_revenue = get_path(raw, mapping.revenue)
    if raw_revenue in (None, ""):
        revenue = 0.0
    else:
        try:
            revenue = float(str(raw_revenue).replace(",", "").replace("$", ""))
        except (TypeError, ValueError):
            return None, RejectReason.BAD_REVENUE
        if revenue < 0:
            return None, RejectReason.NEGATIVE_REVENUE

    return (
        Event(
            user_id=str(user_id).strip(),
            ts=ts,
            event_type=event_type,
            channel=normalise_label(get_path(raw, mapping.channel)),
            campaign=normalise_label(get_path(raw, mapping.campaign)),
            revenue=revenue,
            event_id=str(get_path(raw, mapping.event_id) or ""),
            source=source,
        ),
        None,
    )
