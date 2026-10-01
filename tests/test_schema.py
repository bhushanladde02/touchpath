from datetime import datetime

from touchpath.schema import FieldMap, RejectReason, normalise_label, parse_event, parse_timestamp


def test_parses_the_formats_vendors_actually_send():
    expected = datetime(2026, 9, 14, 10, 30, 0)
    assert parse_timestamp("2026-09-14 10:30:00") == expected
    assert parse_timestamp("2026-09-14T10:30:00") == expected
    assert parse_timestamp("2026-09-14T10:30:00Z") == expected
    assert parse_timestamp("2026/09/14 10:30:00") == expected
    assert parse_timestamp(expected) == expected
    assert parse_timestamp("2026-09-14").date() == expected.date()


def test_epoch_seconds_and_milliseconds():
    assert parse_timestamp(1757845800).year == 2025
    assert parse_timestamp(1757845800000) == parse_timestamp(1757845800)


def test_unparseable_timestamps_return_none_rather_than_raising():
    for value in ("", None, "not-a-date", "2026-13-45 99:99:99", "yesterday"):
        assert parse_timestamp(value) is None


def test_channel_names_are_normalised():
    assert normalise_label("Google Ads") == "google_ads"
    assert normalise_label("  PAID-SOCIAL ") == "paid_social"
    assert normalise_label(None) == "unknown"


def test_parse_event_accepts_dict_and_json_string():
    record = {"user_id": "u1", "timestamp": "2026-09-14T10:00:00", "event_type": "click", "channel": "Email"}
    event, reason = parse_event(record)
    assert reason is None and event.channel == "email" and event.is_touch

    event, reason = parse_event('{"user_id":"u1","timestamp":"2026-09-14T10:00:00","event_type":"click"}')
    assert reason is None and event.user_id == "u1"


def test_rejects_carry_a_reason():
    cases = [
        ({"timestamp": "2026-09-14", "event_type": "click"}, RejectReason.MISSING_USER),
        ({"user_id": "u1", "event_type": "click"}, RejectReason.MISSING_TIMESTAMP),
        ({"user_id": "u1", "timestamp": "nope", "event_type": "click"}, RejectReason.BAD_TIMESTAMP),
        ({"user_id": "u1", "timestamp": "2026-09-14"}, RejectReason.MISSING_TYPE),
        ({"user_id": "u1", "timestamp": "2026-09-14", "event_type": "sneeze"}, RejectReason.UNKNOWN_TYPE),
        ({"user_id": "u1", "timestamp": "2026-09-14", "event_type": "purchase", "revenue": "N/A"}, RejectReason.BAD_REVENUE),
        ({"user_id": "u1", "timestamp": "2026-09-14", "event_type": "purchase", "revenue": -5}, RejectReason.NEGATIVE_REVENUE),
        ("not json at all", RejectReason.NOT_AN_OBJECT),
    ]
    for record, expected in cases:
        event, reason = parse_event(record)
        assert event is None and reason == expected


def test_vendor_field_mapping_handles_nested_payloads():
    shopify = {
        "id": 1001,
        "created_at": "2026-09-14T10:00:00Z",
        "total_price": "120.50",
        "source_name": "Google Ads",
        "customer": {"id": "c1"},
    }
    mapping = FieldMap(
        user_id="customer.id",
        ts="created_at",
        event_type="kind",
        channel="source_name",
        revenue="total_price",
        event_id="id",
    )
    shopify["kind"] = "purchase"
    event, reason = parse_event(shopify, mapping, source="shopify")
    assert reason is None
    assert event.user_id == "c1" and event.revenue == 120.50 and event.channel == "google_ads"
    assert event.is_conversion and event.source == "shopify"


def test_type_aliases_map_vendor_words_onto_the_schema():
    mapping = FieldMap(type_aliases={"order_completed": "purchase"})
    event, reason = parse_event(
        {"user_id": "u1", "timestamp": "2026-09-14", "event_type": "Order Completed", "revenue": 10},
        mapping,
    )
    assert reason is None and event.is_conversion
