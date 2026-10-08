"""FastAPI service: upload events, run attribution, see the result.

Two surfaces over the same core:

    GET  /                     the dashboard
    POST /analyze              form submission -> rendered dashboard
    POST /report.pdf           the result on screen, as a downloadable report
    POST /api/analyze          JSON in, JSON out
    POST /api/incrementality   holdout statistics
    GET  /healthz              liveness

The web layer does no attribution of its own; it parses input, calls the
library and shapes the response. That keeps the models testable without a
server and the server testable without a browser.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import datasets as sample_data
from ..generate import generate_events
from ..incrementality import holdout_test
from ..ingest import ingest_records
from ..models import heuristic, markov, shapley
from ..paths import build_paths, path_stats
from .report import PayloadError, render_report

HERE = Path(__file__).parent
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_REPORT_BYTES = 2 * 1024 * 1024
ALL_MODELS = ("last", "first", "linear", "position", "time_decay", "markov", "shapley")
MODEL_LABELS = {
    "last": "Last touch",
    "first": "First touch",
    "linear": "Linear",
    "position": "Position 40/20/40",
    "time_decay": "Time decay",
    "markov": "Markov removal",
    "shapley": "Shapley value",
}

app = FastAPI(
    title="touchpath",
    description="Multi-touch attribution: heuristic, Markov-chain and Shapley-value models.",
    version="0.1.0",
)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def run_model(paths, name: str):
    if name == "markov":
        return markov.attribute(paths)
    if name == "shapley":
        return shapley.attribute(paths)
    return heuristic.attribute(paths, model=name)


def parse_upload(raw: bytes, filename: str):
    """Decode an uploaded file into records. Raises HTTPException on bad input."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "file is not valid UTF-8 text")

    name = filename.lower()
    if name.endswith((".json", ".jsonl", ".ndjson")):
        stripped = text.lstrip()
        try:
            if stripped.startswith("["):
                records = json.loads(text)
            else:
                records = [json.loads(line) for line in text.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise HTTPException(400, f"could not parse JSON: {error}")
    elif name.endswith((".csv", ".tsv")):
        delimiter = "\t" if name.endswith(".tsv") else ","
        records = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    else:
        raise HTTPException(400, "expected a .json, .jsonl, .csv or .tsv file")

    if not records:
        raise HTTPException(400, "file contained no records")
    return records


def analyse(records, lookback_days: int, model_names, ground_truth=None) -> dict:
    """Ingest, build paths, run every requested model, shape it for the view."""
    events, report = ingest_records(records)
    if not events:
        raise HTTPException(400, "no usable events - check the field names in your file")

    paths = build_paths(events, lookback_days=lookback_days)
    stats = path_stats(paths)

    results = {name: run_model(paths, name) for name in model_names}
    channels = sorted(
        {channel for result in results.values() for channel in result.revenue},
        key=lambda channel: -max(results[name].revenue.get(channel, 0.0) for name in model_names),
    )

    series = [
        {
            "model": name,
            "label": MODEL_LABELS[name],
            "share": [round(results[name].share().get(channel, 0.0) * 100, 2) for channel in channels],
            "revenue": [round(results[name].revenue.get(channel, 0.0), 2) for channel in channels],
        }
        for name in model_names
    ]

    spread = {}
    for index, channel in enumerate(channels):
        values = [s["share"][index] for s in series]
        spread[channel] = round(max(values) - min(values), 2)

    # Provenance, derived from the events themselves rather than from the form.
    # A chart with no statement of what produced it invites the reader to assume
    # it is whatever they last clicked, which is how the demo run and a sample
    # run get confused for each other - they share channel names but not weights.
    stamps = [event.ts for event in events]
    users_seen = len({event.user_id for event in events})

    payload = {
        "window": {
            "first": min(stamps).strftime("%d %b %Y"),
            "last": max(stamps).strftime("%d %b %Y"),
            "days": (max(stamps) - min(stamps)).days + 1,
        },
        "users": users_seen,
        "models_run": list(model_names),
        "ingest": {
            "total": report.total,
            "accepted": report.accepted,
            "rejected": report.rejected,
            "reject_rate": round(report.reject_rate * 100, 2),
            "reasons": [
                {"reason": reason, "count": count} for reason, count in report.reasons.most_common()
            ],
        },
        "paths": stats,
        "lookback_days": lookback_days,
        "channels": channels,
        "series": series,
        "spread": spread,
        "markov_removal_effects": results["markov"].meta.get("removal_effects") if "markov" in results else None,
    }
    if ground_truth:
        payload["ground_truth"] = [round(ground_truth.get(c, 0.0) * 100, 2) for c in channels]
    return payload


_sample_cache: dict[str, tuple[list, dict]] = {}


def load_sample(slug: str):
    """Build a named sample, memoised. Seeds are fixed, so this is stable."""
    if slug not in _sample_cache:
        try:
            records, ground_truth, _ = sample_data.build(slug)
        except KeyError:
            raise HTTPException(404, f"no sample dataset called {slug!r}")
        _sample_cache[slug] = (records, ground_truth)
    return _sample_cache[slug]


@app.get("/", response_class=HTMLResponse)
def landing(request: Request):
    """The front door.

    A first-time visitor arriving at an attribution dashboard has no idea what
    the models are or which one to trust, so the entry point explains the
    project before offering the controls. The dashboard lives at /dashboard.
    """
    return templates.TemplateResponse(request, "about.html", {"active": "about"})


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    """Kept so older links still work."""
    return templates.TemplateResponse(request, "about.html", {"active": "about"})


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": None,
            "models": ALL_MODELS,
            "labels": MODEL_LABELS,
            "samples": sample_data.catalogue(),
            "active": "dashboard",
        },
    )


@app.get("/datasets", response_class=HTMLResponse)
def datasets_page(request: Request):
    return templates.TemplateResponse(
        request,
        "datasets.html",
        {"samples": sample_data.catalogue(), "active": "datasets"},
    )


@app.get("/datasets/{slug}.report.pdf")
def download_sample_report(slug: str):
    """A finished report for one sample, in a single click.

    The dashboard export needs a run on screen first. This does not: it builds
    the sample, analyses it with every model and returns the PDF, so somebody
    arriving cold can see what the tool produces without filling in a form.

    Declared **above** ``/datasets/{slug}.json``, for the reason given on the
    answer-key route below — the looser pattern would otherwise capture this as
    ``slug="<name>.report"`` and 404. ``test_sample_report_beats_the_json_route``
    guards the ordering.

    Samples are memoised by :func:`load_sample` and seeds are fixed, so
    repeated pulls cost one analysis each rather than a fresh simulation.
    """
    records, ground_truth = load_sample(slug)
    payload = analyse(records, 30, ALL_MODELS, ground_truth)
    meta = sample_data.BY_SLUG[slug]
    payload["source"] = {
        "kind": "sample",
        "label": meta.name,
        "detail": f"sample dataset {meta.slug} · {len(meta.channels)} channels · seed {meta.seed}",
        "truth": f"recorded answer key for {meta.slug}",
    }
    payload["dataset"] = meta.name
    return Response(
        content=render_report(payload),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="touchpath-{slug}.pdf"'},
    )


@app.get("/datasets/{slug}.truth.json")
def download_truth(slug: str):
    """The answer key for one sample.

    A separate file from the records on purpose. The records are one row per
    event; the answer is one number per channel, so there is no column in the
    event table where it could live. Kept out of the records download as well,
    so the records stay a plain array that loads into anything without being
    reshaped first.

    This route must stay declared **above** ``/datasets/{slug}.json``. Routes
    match in declaration order, and the looser pattern would otherwise swallow
    this one with ``slug="<name>.truth"``, which fails as an unknown sample and
    returns 404. ``test_answer_key_download`` guards the ordering.
    """
    _, ground_truth = load_sample(slug)
    return JSONResponse(
        sample_data.truth_payload(slug, ground_truth),
        headers={"Content-Disposition": f'attachment; filename="{slug}.truth.json"'},
    )


@app.get("/datasets/{slug}.json")
def download_sample(slug: str):
    """The raw records, as a file. Same data the dashboard runs on."""
    records, _ = load_sample(slug)
    return JSONResponse(
        records,
        headers={"Content-Disposition": f'attachment; filename="{slug}.json"'},
    )


@app.post("/analyze", response_class=HTMLResponse)
async def analyze_form(
    request: Request,
    source: str = Form("demo"),
    events_file: UploadFile | None = File(None),
    lookback_days: int = Form(30),
    demo_users: int = Form(20000),
    sample: str = Form(""),
    models: list[str] = Form(default=list(ALL_MODELS)),
):
    selected = [name for name in models if name in ALL_MODELS] or ["last"]
    lookback_days = max(1, min(lookback_days, 365))
    ground_truth = None
    error = None
    payload = None

    try:
        if source == "upload":
            if events_file is None or not events_file.filename:
                raise HTTPException(400, "choose a file, or run on the demo data")
            records = parse_upload(await events_file.read(), events_file.filename)
            origin = {
                "kind": "upload",
                "label": events_file.filename,
                "detail": "your own file, parsed in memory and discarded after this request",
                "truth": None,
            }
        elif source == "sample":
            records, ground_truth = load_sample(sample)
            meta = sample_data.BY_SLUG[sample]
            origin = {
                "kind": "sample",
                "label": meta.name,
                # No user count here: the Analysed row below carries the real
                # one from the data. Two different user figures on one screen
                # reads as a contradiction rather than as request-vs-actual.
                "detail": (
                    f"sample dataset {meta.slug} · {len(meta.channels)} channels · "
                    f"seed {meta.seed}"
                ),
                "truth": f"recorded answer key for {meta.slug}",
            }
        else:
            users = max(500, min(demo_users, 100_000))
            records, ground_truth = generate_events(users=users, corruption_rate=0.03, seed=11)
            origin = {
                "kind": "demo",
                "label": "Demo (synthetic)",
                "detail": (
                    "generator defaults · seed 11 · 3% damaged rows"
                ),
                "truth": (
                    "the generator's own channel weights — these differ from every "
                    "sample dataset, so figures here will not match a sample's answer key"
                ),
            }

        payload = analyse(records, lookback_days, selected, ground_truth)
        payload["source"] = origin
        payload["dataset"] = origin["label"]
    except HTTPException as exc:
        error = exc.detail

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "result": payload,
            "result_json": json.dumps(payload) if payload else "null",
            "error": error,
            "models": ALL_MODELS,
            "labels": MODEL_LABELS,
            "selected": selected,
            "lookback_days": lookback_days,
            "samples": sample_data.catalogue(),
            "chosen_sample": sample,
            "active": "dashboard",
        },
    )


def _report_filename(payload: dict) -> str:
    """A filename a person can find again a week later."""
    source = payload.get("source") or {}
    label = source.get("label") or payload.get("dataset") or "attribution"
    slug = "".join(char.lower() if char.isalnum() else "-" for char in label)
    slug = "-".join(part for part in slug.split("-") if part)[:48] or "attribution"
    return f"touchpath-{slug}-{datetime.now(timezone.utc):%Y%m%d}.pdf"


@app.post("/report.pdf")
async def report_pdf(payload: str = Form(...)):
    """Render the analysis currently on screen as a downloadable PDF.

    The page posts its own result payload back rather than the server
    re-running anything. An uploaded file is parsed in memory and discarded
    when that request ends, so there is nothing to re-analyse by the time a
    report is asked for; taking the payload means demo, sample and upload runs
    all travel the same path, and the PDF cannot drift from what was shown.

    Nothing here trusts the body. It arrives from a browser the server does not
    control, so it is size-capped before parsing and shape-checked after.
    """
    if len(payload) > MAX_REPORT_BYTES:
        raise HTTPException(413, "that result is too large to render as a report")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, "report payload must be JSON")

    try:
        pdf = render_report(data)
    except PayloadError as exc:
        raise HTTPException(400, str(exc))

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_report_filename(data)}"'},
    )


@app.post("/api/analyze")
async def analyze_api(request: Request):
    """JSON API: {"events": [...], "lookback_days": 30, "models": ["last","markov"]}"""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "body must be JSON")

    records = body.get("events")
    if not isinstance(records, list) or not records:
        raise HTTPException(400, "'events' must be a non-empty list")

    models = [name for name in body.get("models", list(ALL_MODELS)) if name in ALL_MODELS]
    lookback = int(body.get("lookback_days", 30))
    return JSONResponse(analyse(records, max(1, min(lookback, 365)), models or ["last"]))


@app.post("/api/incrementality")
async def incrementality_api(request: Request):
    """JSON API for holdout statistics."""
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(400, "body must be JSON")

    try:
        result = holdout_test(
            int(body["treatment_users"]),
            int(body["treatment_conversions"]),
            int(body["control_users"]),
            int(body["control_conversions"]),
            float(body.get("confidence", 0.95)),
        )
    except KeyError as error:
        raise HTTPException(400, f"missing field: {error}")
    except (TypeError, ValueError) as error:
        raise HTTPException(400, str(error))

    return JSONResponse(
        {
            "treatment_rate": round(result.treatment_rate * 100, 4),
            "control_rate": round(result.control_rate * 100, 4),
            "relative_lift": round(result.relative_lift * 100, 2),
            "absolute_lift": round(result.absolute_lift * 100, 4),
            "incremental_conversions": round(result.incremental_conversions, 1),
            "ci_low": round(result.ci_low * 100, 4),
            "ci_high": round(result.ci_high * 100, 4),
            "p_value": round(result.p_value, 5),
            "significant": result.significant,
        }
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "version": app.version}
