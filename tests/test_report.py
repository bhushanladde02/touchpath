"""The PDF report: scoring arithmetic, payload validation, and the route.

The renderer takes a payload posted back from a browser, so most of what is
worth testing here is what happens when that payload is wrong. A malformed
body should produce a 400 with a readable message, never a traceback and never
a 500.
"""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from touchpath.datasets import catalogue
from touchpath.web.app import ALL_MODELS, app
from touchpath.web.report import (
    MAX_CHANNELS,
    PayloadError,
    render_report,
    score_models,
    validate_payload,
)

client = TestClient(app)


def payload_with_truth() -> dict:
    return {
        "channels": ["paid_search", "social", "email"],
        "series": [
            {"model": "last", "label": "Last touch", "share": [50.0, 30.0, 20.0]},
            {"model": "markov", "label": "Markov removal", "share": [40.0, 25.0, 35.0]},
        ],
        "ground_truth": [38.8, 24.7, 36.5],
        "spread": {"paid_search": 10.0, "email": 15.0, "social": 5.0},
        "markov_removal_effects": {"paid_search": 0.41, "social": 0.22},
        "paths": {
            "conversions": 1234,
            "revenue": 98765.0,
            "avg_path_length": 3.2,
            "max_path_length": 9,
            "unique_channels": 3,
            "direct_conversions": 120,
        },
        "ingest": {"total": 5000, "accepted": 4900, "rejected": 100, "reject_rate": 2.0},
        "window": {"first": "01 Jan 2026", "last": "31 Jan 2026", "days": 31},
        "users": 2000,
        "lookback_days": 30,
        "models_run": ["last", "markov"],
        "source": {
            "kind": "sample",
            "label": "Retail baseline",
            "detail": "sample dataset retail-baseline",
            "truth": "recorded answer key for retail-baseline",
        },
        "dataset": "Retail baseline",
    }


def payload_without_truth() -> dict:
    data = payload_with_truth()
    data.pop("ground_truth")
    data["source"] = {
        "kind": "upload",
        "label": "events.csv",
        "detail": "your own file",
        "truth": None,
    }
    return data


# --- renderer -------------------------------------------------------------


def test_render_returns_a_pdf():
    pdf = render_report(payload_with_truth())
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1500


def test_render_without_ground_truth_still_works():
    """An upload has no answer key. That is a normal run, not an error."""
    pdf = render_report(payload_without_truth())
    assert pdf.startswith(b"%PDF-")


def test_render_survives_a_minimal_payload():
    """Only channels and series are structurally required; the rest is optional."""
    pdf = render_report(
        {
            "channels": ["a", "b"],
            "series": [{"model": "last", "label": "Last touch", "share": [60.0, 40.0]}],
        }
    )
    assert pdf.startswith(b"%PDF-")


# --- scoring --------------------------------------------------------------


def test_score_models_ranks_by_mean_absolute_error():
    scored = score_models(payload_with_truth())
    labels = [label for label, _ in scored]
    assert labels == ["Markov removal", "Last touch"]

    # Markov: |40-38.8| + |25-24.7| + |35-36.5| = 1.2 + 0.3 + 1.5 = 3.0 -> 1.0
    # Last:   |50-38.8| + |30-24.7| + |20-36.5| = 11.2 + 5.3 + 16.5 = 33.0 -> 11.0
    assert dict(scored)["Markov removal"] == pytest.approx(1.0)
    assert dict(scored)["Last touch"] == pytest.approx(11.0)


def test_score_models_is_empty_without_truth():
    assert score_models(payload_without_truth()) == []


# --- validation -----------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda d: d.update(channels=[]), "channel list"),
        (lambda d: d.update(series=[]), "model results"),
        (lambda d: d.update(channels=["a", "b", "c", "d"]), "one share per channel"),
        (lambda d: d.update(ground_truth=[1.0]), "one value per channel"),
        (lambda d: d.update(channels=[1, 2, 3]), "must be strings"),
        (lambda d: d["series"][0].update(share=["x", "y", "z"]), "must be numbers"),
        (lambda d: d.update(series=["not-an-object"]), "must be an object"),
        (lambda d: d.update(channels=["c"] * (MAX_CHANNELS + 1)), "too many channels"),
    ],
)
def test_validate_rejects_malformed_payloads(mutate, message):
    data = payload_with_truth()
    mutate(data)
    with pytest.raises(PayloadError) as excinfo:
        validate_payload(data)
    assert message in str(excinfo.value)


def test_validate_rejects_non_objects():
    with pytest.raises(PayloadError):
        validate_payload(["channels", "series"])


# --- route ----------------------------------------------------------------


def test_report_route_returns_a_pdf_attachment():
    response = client.post("/report.pdf", data={"payload": json.dumps(payload_with_truth())})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "touchpath-retail-baseline-" in disposition
    assert disposition.endswith('.pdf"')
    assert response.content.startswith(b"%PDF-")


def test_report_route_rejects_bad_json():
    response = client.post("/report.pdf", data={"payload": "{not json"})
    assert response.status_code == 400
    assert "JSON" in response.json()["detail"]


def test_report_route_rejects_a_payload_of_the_wrong_shape():
    response = client.post("/report.pdf", data={"payload": json.dumps({"hello": "world"})})
    assert response.status_code == 400
    assert "channel list" in response.json()["detail"]


def test_report_route_rejects_an_oversized_payload():
    """An oversized body is refused, and refused cheaply.

    Which refusal arrives depends on the installed ``python-multipart``: newer
    releases cap a single form field themselves and answer 400 before the
    handler runs, older ones hand the field over and the route's own size check
    answers 413. Both are correct, so the assertion is on the contract — a 4xx
    and no PDF — rather than on whichever layer happened to say no first.
    """
    response = client.post("/report.pdf", data={"payload": "x" * (2 * 1024 * 1024 + 1)})
    assert response.status_code in (400, 413), response.status_code
    assert not response.content.startswith(b"%PDF-")


def test_dashboard_offers_the_download_after_a_run():
    """The button only means anything once there is a result to export."""
    empty = client.get("/")
    assert 'action="/report.pdf"' not in empty.text

    ran = client.post(
        "/analyze",
        data={"source": "demo", "demo_users": "800", "lookback_days": "30", "models": ["last", "markov"]},
    )
    assert ran.status_code == 200
    assert 'action="/report.pdf"' in ran.text
    assert "Download report (PDF)" in ran.text


def test_the_downloaded_report_matches_the_run_on_screen():
    """End to end: run the demo, post its own payload back, get a PDF."""
    page = client.post(
        "/analyze",
        data={"source": "demo", "demo_users": "800", "lookback_days": "30", "models": ["last", "markov"]},
    )
    response = client.post("/report.pdf", data={"payload": _embedded_payload(page.text)})
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")


def _embedded_payload(html: str) -> str:
    """The result payload the dashboard embeds for its own chart and export."""
    match = re.search(
        r'<script id="payload" type="application/json">(.*?)</script>', html, re.S
    )
    assert match, "the dashboard should embed its result payload"
    return match.group(1)


# --- every source exports -------------------------------------------------


@pytest.mark.parametrize("slug", [entry["slug"] for entry in catalogue()])
def test_every_sample_exports_from_the_dashboard(slug):
    page = client.post(
        "/analyze",
        data={"source": "sample", "sample": slug, "lookback_days": "30", "models": list(ALL_MODELS)},
    )
    assert page.status_code == 200
    response = client.post("/report.pdf", data={"payload": _embedded_payload(page.text)})
    assert response.status_code == 200, slug
    assert response.content.startswith(b"%PDF-")


def test_an_uploaded_file_exports_too():
    """No answer key, so no scoring — but the export must still work."""
    rows = ["user_id,timestamp,event_type,channel,revenue,event_id"]
    for user in range(40):
        day = f"{user % 9 + 1:02d}"
        rows.append(f"u{user},2026-01-{day} 10:00:00,impression,email,,t{user}a")
        rows.append(f"u{user},2026-01-{day} 12:00:00,click,paid_search,,t{user}b")
        rows.append(f"u{user},2026-01-{day} 14:00:00,purchase,,120.0,c{user}")
    csv_bytes = "\n".join(rows).encode()

    page = client.post(
        "/analyze",
        data={"source": "upload", "lookback_days": "30", "models": ["last", "markov"]},
        files={"events_file": ("events.csv", csv_bytes, "text/csv")},
    )
    assert page.status_code == 200
    payload = json.loads(_embedded_payload(page.text))
    assert "ground_truth" not in payload, "an upload has no answer key"

    response = client.post("/report.pdf", data={"payload": json.dumps(payload)})
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")


# --- one-click sample report ----------------------------------------------


@pytest.mark.parametrize("slug", [entry["slug"] for entry in catalogue()])
def test_sample_report_downloads_in_one_click(slug):
    response = client.get(f"/datasets/{slug}.report.pdf")
    assert response.status_code == 200, slug
    assert response.headers["content-type"] == "application/pdf"
    assert f'filename="touchpath-{slug}.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF-")


def test_sample_report_beats_the_json_route():
    """Route ordering: the looser /datasets/{slug}.json must not swallow this.

    Declared below it, this request would arrive as slug="retail-baseline.report",
    fail to load as a sample and 404. The same trap the answer-key route sits in.
    """
    response = client.get("/datasets/retail-baseline.report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"

    # and the neighbours still resolve to themselves
    assert client.get("/datasets/retail-baseline.json").headers[
        "content-type"
    ].startswith("application/json")
    assert client.get("/datasets/retail-baseline.truth.json").status_code == 200


def test_unknown_sample_report_is_a_404():
    assert client.get("/datasets/not-a-sample.report.pdf").status_code == 404


def test_datasets_page_offers_every_download():
    page = client.get("/datasets")
    assert page.status_code == 200
    for entry in catalogue():
        slug = entry["slug"]
        assert f"/datasets/{slug}.report.pdf" in page.text
        assert f"/datasets/{slug}.truth.json" in page.text
        assert f"/datasets/{slug}.json" in page.text
