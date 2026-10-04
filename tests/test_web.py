"""Web layer tests: the dashboard renders, the API validates its input."""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from touchpath.generate import generate_events  # noqa: E402
from touchpath.web.app import app  # noqa: E402

client = TestClient(app)


def test_health():
    response = client.get("/healthz")
    assert response.status_code == 200 and response.json()["status"] == "ok"


def test_dashboard_renders_the_form():
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Run attribution" in response.text
    assert "Shapley value" in response.text


def test_demo_run_renders_results():
    response = client.post(
        "/analyze",
        data={"source": "demo", "demo_users": 1000, "lookback_days": 30,
              "models": ["last", "markov", "shapley"]},
    )
    assert response.status_code == 200
    assert "Revenue share by model" in response.text
    assert "Markov removal effects" in response.text
    assert "True influence" not in response.text or "ground_truth" in response.text


def test_upload_json(tmp_path):
    records, _ = generate_events(users=400, seed=3)
    payload = json.dumps(records).encode()
    response = client.post(
        "/analyze",
        data={"source": "upload", "lookback_days": 30, "models": ["last", "linear"]},
        files={"events_file": ("events.json", payload, "application/json")},
    )
    assert response.status_code == 200
    assert "events.json" in response.text


def test_upload_csv():
    records, _ = generate_events(users=300, seed=4)
    columns = ["user_id", "timestamp", "event_type", "channel", "revenue"]
    rows = [",".join(columns)]
    for record in records:
        rows.append(",".join(str(record.get(c, "")) for c in columns))
    csv_bytes = "\n".join(rows).encode()

    response = client.post(
        "/analyze",
        data={"source": "upload", "lookback_days": 14, "models": ["last"]},
        files={"events_file": ("events.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == 200
    assert "Revenue share by model" in response.text


def test_upload_without_file_shows_an_error():
    response = client.post("/analyze", data={"source": "upload", "models": ["last"]})
    assert response.status_code == 200
    assert "choose a file" in response.text


def test_unsupported_file_type_is_rejected():
    response = client.post(
        "/analyze",
        data={"source": "upload", "models": ["last"]},
        files={"events_file": ("events.txt", b"nope", "text/plain")},
    )
    assert "expected a .json" in response.text


def test_api_analyze_returns_shares_that_sum_to_one_hundred():
    records, _ = generate_events(users=600, seed=8)
    response = client.post(
        "/api/analyze",
        json={"events": records, "lookback_days": 30, "models": ["last", "shapley"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["paths"]["conversions"] > 0
    for series in body["series"]:
        assert abs(sum(series["share"]) - 100.0) < 0.5


def test_api_analyze_rejects_empty_events():
    assert client.post("/api/analyze", json={"events": []}).status_code == 400


def test_api_incrementality():
    response = client.post(
        "/api/incrementality",
        json={"treatment_users": 100000, "treatment_conversions": 2300,
              "control_users": 100000, "control_conversions": 2000},
    )
    body = response.json()
    assert body["significant"] is True
    assert abs(body["relative_lift"] - 15.0) < 0.1
    assert body["incremental_conversions"] == 300.0


def test_api_incrementality_validates_input():
    assert client.post("/api/incrementality", json={"treatment_users": 10}).status_code == 400
    bad = client.post(
        "/api/incrementality",
        json={"treatment_users": 0, "treatment_conversions": 0,
              "control_users": 10, "control_conversions": 1},
    )
    assert bad.status_code == 400


def test_landing_page_is_the_introduction():
    """A first-time visitor should meet the explanation, not the controls."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Run attribution" not in response.text
    assert "Start here" in response.text        # the nav
    assert "Try a sample dataset" in response.text


def test_about_still_resolves():
    assert client.get("/about").status_code == 200


def test_every_page_carries_the_same_nav():
    for path in ("/", "/dashboard", "/datasets", "/about"):
        text = client.get(path).text
        for label in ("Start here", "Dashboard", "Sample data"):
            assert label in text, f"{label} missing from {path}"


def test_active_tab_is_marked():
    assert 'href="/dashboard" class="on"' in client.get("/dashboard").text
    assert 'href="/datasets" class="on"' in client.get("/datasets").text
    assert 'href="/" class="on"' in client.get("/").text
