"""Render an analysis payload as a PDF report.

The input is the dict :func:`touchpath.web.app.analyse` already builds for the
dashboard — not the raw events. That matters for a practical reason: an
uploaded file is parsed in memory and discarded once the request ends, so by
the time anyone asks for a report there is nothing left to re-analyse. Taking
the payload instead means one code path serves demo runs, sample runs and
uploads alike, and the numbers in the PDF are by construction the same numbers
that were on the screen.

The payload arrives from the browser, so :func:`validate_payload` checks its
shape before anything is drawn. It is a public endpoint; an absent key should
produce a 400, not a traceback.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

__all__ = ["PayloadError", "render_report", "validate_payload", "score_models"]

MAX_CHANNELS = 200
MAX_SERIES = 32

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#5f6b7a")
RULE = colors.HexColor("#d8dee6")
BAND = colors.HexColor("#f4f6f9")
TRUTH_BAND = colors.HexColor("#eef4ec")


class PayloadError(ValueError):
    """The posted payload is not an analysis result this module can render."""


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "tp-title", parent=base["Title"], fontSize=20, leading=24,
            alignment=0, textColor=INK, spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "tp-subtitle", parent=base["Normal"], fontSize=9.5, leading=13,
            textColor=MUTED, spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "tp-h2", parent=base["Heading2"], fontSize=12.5, leading=16,
            textColor=INK, spaceBefore=16, spaceAfter=6, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "tp-body", parent=base["Normal"], fontSize=9.5, leading=13.5,
            textColor=INK, spaceAfter=6,
        ),
        "note": ParagraphStyle(
            "tp-note", parent=base["Normal"], fontSize=8.5, leading=12,
            textColor=MUTED, spaceAfter=4,
        ),
    }


def validate_payload(payload) -> dict:
    """Check the posted object is shaped like an analysis result.

    Raises :class:`PayloadError` with a message fit to show a caller. Bounds on
    channel and series counts stop a hand-rolled POST from asking the server to
    lay out an arbitrarily large table.
    """
    if not isinstance(payload, dict):
        raise PayloadError("payload must be a JSON object")

    channels = payload.get("channels")
    series = payload.get("series")
    if not isinstance(channels, list) or not channels:
        raise PayloadError("payload is missing its channel list")
    if not isinstance(series, list) or not series:
        raise PayloadError("payload is missing its model results")
    if len(channels) > MAX_CHANNELS:
        raise PayloadError(f"too many channels (limit {MAX_CHANNELS})")
    if len(series) > MAX_SERIES:
        raise PayloadError(f"too many models (limit {MAX_SERIES})")
    if not all(isinstance(channel, str) for channel in channels):
        raise PayloadError("channel names must be strings")

    for entry in series:
        if not isinstance(entry, dict):
            raise PayloadError("each model result must be an object")
        share = entry.get("share")
        if not isinstance(share, list) or len(share) != len(channels):
            raise PayloadError("each model needs one share per channel")
        if not all(isinstance(value, (int, float)) for value in share):
            raise PayloadError("shares must be numbers")

    truth = payload.get("ground_truth")
    if truth is not None:
        if not isinstance(truth, list) or len(truth) != len(channels):
            raise PayloadError("ground truth needs one value per channel")
        if not all(isinstance(value, (int, float)) for value in truth):
            raise PayloadError("ground truth values must be numbers")

    return payload


def score_models(payload: dict) -> list[tuple[str, float]]:
    """Mean absolute error, in share points, of each model against the truth.

    Only meaningful for simulated data, where the true influence is recorded.
    Returns an empty list when the payload carries no answer key — which is the
    normal case for an upload, and the reason the report says so plainly rather
    than printing a scoreboard of nothing.
    """
    truth = payload.get("ground_truth")
    if not truth:
        return []

    scored = []
    for entry in payload["series"]:
        errors = [abs(share - actual) for share, actual in zip(entry["share"], truth)]
        label = entry.get("label") or entry.get("model") or "model"
        scored.append((label, round(sum(errors) / len(errors), 2)))
    return sorted(scored, key=lambda row: row[1])


def _grid(data, style_extra=None, header_band=BAND):
    table = Table(data, repeatRows=1, hAlign="LEFT")
    style = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("BACKGROUND", (0, 0), (-1, 0), header_band),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ("GRID", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if style_extra:
        style.extend(style_extra)
    table.setStyle(TableStyle(style))
    return table


def _provenance_rows(payload: dict) -> list[list[str]]:
    source = payload.get("source") or {}
    window = payload.get("window") or {}
    ingest = payload.get("ingest") or {}

    analysed = []
    if ingest.get("accepted") is not None:
        analysed.append(f"{ingest['accepted']:,} events")
    if payload.get("users") is not None:
        analysed.append(f"{payload['users']:,} users")
    if window.get("first") and window.get("last"):
        analysed.append(f"{window['first']} to {window['last']} ({window.get('days', '?')} days)")
    if payload.get("lookback_days") is not None:
        analysed.append(f"{payload['lookback_days']}-day lookback")
    if ingest.get("rejected"):
        analysed.append(f"{ingest['rejected']:,} rows rejected ({ingest.get('reject_rate', 0)}%)")

    models = " · ".join(
        entry.get("label") or entry.get("model") or "?" for entry in payload["series"]
    )

    label = source.get("label") or payload.get("dataset") or "unnamed run"
    detail = source.get("detail")
    truth_note = source.get("truth") or (
        "none — scoring is unavailable for this source"
        if not payload.get("ground_truth")
        else "recorded answer key — share of converted revenue per channel"
    )

    return [
        ["Data", f"{label}" + (f" — {detail}" if detail else "")],
        ["Analysed", " · ".join(analysed) or "—"],
        ["Models", models],
        ["Answer key", truth_note],
    ]


def _headline_rows(payload: dict) -> list[list[str]] | None:
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return None
    ingest = payload.get("ingest") or {}
    return [
        ["Conversions", "Revenue", "Avg path", "Channels", "Rejected"],
        [
            f"{paths.get('conversions', 0):,}",
            f"${paths.get('revenue', 0):,.0f}",
            str(paths.get("avg_path_length", "—")),
            str(paths.get("unique_channels", len(payload["channels"]))),
            f"{ingest.get('reject_rate', 0)}%",
        ],
    ]


def _share_table(payload: dict, styles):
    channels = payload["channels"]
    series = payload["series"]
    truth = payload.get("ground_truth")

    header = ["Channel"]
    if truth:
        header.append("Truth")
    header.extend(entry.get("label") or entry.get("model") or "?" for entry in series)

    rows = [header]
    for index, channel in enumerate(channels):
        row = [channel]
        if truth:
            row.append(f"{truth[index]:.1f}%")
        row.extend(f"{entry['share'][index]:.1f}%" for entry in series)
        rows.append(row)

    extra = [("ALIGN", (1, 0), (-1, -1), "RIGHT")]
    if truth:
        # The answer key is not another opinion in the row, so it is banded
        # away from the model columns rather than sitting flush among them.
        extra.append(("BACKGROUND", (1, 1), (1, -1), TRUTH_BAND))
        extra.append(("FONTNAME", (1, 1), (1, -1), "Helvetica-Bold"))
    return _grid(rows, extra)


def _spread_table(payload: dict):
    spread = payload.get("spread")
    if not isinstance(spread, dict) or not spread:
        return None
    ordered = sorted(spread.items(), key=lambda row: -row[1])[:15]
    rows = [["Channel", "Spread (share points)"]]
    rows.extend([channel, f"{value:.1f}"] for channel, value in ordered)
    return _grid(rows, [("ALIGN", (1, 0), (-1, -1), "RIGHT")])


def _removal_table(payload: dict):
    effects = payload.get("markov_removal_effects")
    if not isinstance(effects, dict) or not effects:
        return None
    ordered = sorted(effects.items(), key=lambda row: -row[1])
    rows = [["Channel", "Removal effect"]]
    rows.extend([channel, f"{value * 100:.1f}%"] for channel, value in ordered)
    return _grid(rows, [("ALIGN", (1, 0), (-1, -1), "RIGHT")])


def _page_furniture(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.75 * inch, 0.55 * inch, "touchpath — multi-touch attribution")
    canvas.drawRightString(
        LETTER[0] - 0.75 * inch, 0.55 * inch, f"page {canvas.getPageNumber()}"
    )
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.4)
    canvas.line(0.75 * inch, 0.72 * inch, LETTER[0] - 0.75 * inch, 0.72 * inch)
    canvas.restoreState()


def render_report(payload: dict, generated_at: datetime | None = None) -> bytes:
    """Render a validated payload to PDF bytes."""
    validate_payload(payload)
    styles = _styles()
    stamp = (generated_at or datetime.now(timezone.utc)).strftime("%d %b %Y, %H:%M UTC")

    source = payload.get("source") or {}
    dataset = source.get("label") or payload.get("dataset") or "attribution run"

    story = [
        Paragraph("Attribution report", styles["title"]),
        Paragraph(f"{dataset} · generated {stamp}", styles["subtitle"]),
    ]

    headline = _headline_rows(payload)
    if headline:
        story.append(_grid(headline, [("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(Spacer(1, 10))

    story.append(Paragraph("Where these numbers came from", styles["h2"]))
    provenance = _grid(
        _provenance_rows(payload),
        [
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (0, -1), BAND),
            ("BACKGROUND", (0, 0), (-1, 0), colors.white),
            ("BACKGROUND", (0, 0), (0, 0), BAND),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ],
        header_band=colors.white,
    )
    story.append(provenance)

    story.append(Paragraph("Revenue share by channel and model", styles["h2"]))
    story.append(
        Paragraph(
            "Each column is one model's answer to the same question: how should "
            "the credit be divided. Where the columns disagree, at most one of "
            "them is right.",
            styles["body"],
        )
    )
    story.append(_share_table(payload, styles))

    scored = score_models(payload)
    if scored:
        best, worst = scored[0], scored[-1]
        block = [
            Paragraph("Model accuracy against the answer key", styles["h2"]),
            Paragraph(
                "Mean absolute error in share points. The data is simulated, so "
                "the answer key records what each channel genuinely earned — "
                "every conversion's revenue split across the channels that "
                "caused it — and the models can be scored instead of argued "
                "about. Zero is not reachable: damaged rows and the lookback "
                "window hide part of what the simulation did, and a model given "
                "the generator's own weights still scores around 0.5. Read "
                "these against that floor.",
                styles["body"],
            ),
            _grid(
                [["Model", "Mean absolute error"]]
                + [[label, f"{error:.2f}"] for label, error in scored],
                [
                    ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ],
            ),
            Spacer(1, 6),
            Paragraph(
                f"{best[0]} is closest at {best[1]:.2f} points; {worst[0]} is "
                f"furthest at {worst[1]:.2f}.",
                styles["note"],
            ),
        ]
        story.append(KeepTogether(block))
    else:
        story.append(Paragraph("Model accuracy", styles["h2"]))
        story.append(
            Paragraph(
                "This run carries no answer key, so the models cannot be scored. "
                "Real conversion data does not record what would have happened "
                "without each touch; that counterfactual is the thing being "
                "estimated. Scoring is available on the simulated samples.",
                styles["body"],
            )
        )

    spread = _spread_table(payload)
    if spread is not None:
        story.append(
            KeepTogether(
                [
                    Paragraph("Where the models disagree most", styles["h2"]),
                    Paragraph(
                        "Spread is the gap between the highest and lowest share "
                        "any model assigns a channel. A wide spread means the "
                        "choice of model, not the data, is deciding the answer.",
                        styles["body"],
                    ),
                    spread,
                ]
            )
        )

    removal = _removal_table(payload)
    if removal is not None:
        story.append(
            KeepTogether(
                [
                    Paragraph("Markov removal effects", styles["h2"]),
                    Paragraph(
                        "The drop in conversion probability when a channel is "
                        "removed from the graph. This is a counterfactual "
                        "measure, not a positional one.",
                        styles["body"],
                    ),
                    removal,
                ]
            )
        )

    story.append(Spacer(1, 18))
    story.append(
        Paragraph(
            "Attribution divides credit that has already been earned; it does not "
            "establish that a channel caused anything. For a causal claim, run a "
            "holdout test. Figures are rounded to one decimal place and may not "
            "sum to exactly 100%.",
            styles["note"],
        )
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.9 * inch,
        title=f"touchpath attribution report — {dataset}",
        author="touchpath",
        subject="Multi-touch attribution model comparison",
    )
    doc.build(story, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buffer.getvalue()
