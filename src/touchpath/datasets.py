"""Sample datasets with known ground truth.

Real attribution data has no answer key. You can compare models to each other,
but you cannot tell which one is closer to the truth, because the truth is not
recorded anywhere.

These five samples are simulated from explicit per-channel influence weights,
so the answer key exists. Each one is shaped to make a specific phenomenon
visible: a closing channel that last touch over-credits, journeys long enough
that position-based and time-decay diverge, paths too short for attribution to
say much, and a feed damaged the way real feeds are damaged.

They are meant to be downloaded and run anywhere, not only here - the files
are ordinary JSON records with the field names the ingest layer expects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from .generate import generate_events


@dataclass(frozen=True)
class Sample:
    """One named scenario, plus the parameters that produce it."""

    slug: str
    name: str
    summary: str          # one line, for the card
    shows: str            # what a visitor should look for
    users: int
    channels: dict
    corruption_rate: float = 0.02
    days: int = 60
    seed: int = 7
    notes: str = ""

    @property
    def filename(self) -> str:
        return f"{self.slug}.json"

    @property
    def truth_filename(self) -> str:
        """The answer key sits beside the records, never inside them.

        The records are one row per event; the truth is one number per channel,
        so there is no column in the event table where it could live. Keeping
        them apart also leaves the records a plain array that loads anywhere
        without being unwrapped first.
        """
        return f"{self.slug}.truth.json"


# (how often a channel appears in a journey, how much it moves conversion odds)
SAMPLES: tuple[Sample, ...] = (
    Sample(
        slug="retail-baseline",
        name="Retail baseline",
        summary="A balanced direct-to-consumer mix, nothing pathological.",
        shows=(
            "Start here. Influence is spread across six channels in roughly the "
            "proportions you would expect from a healthy retail programme, and the models "
            "broadly agree. Use it to see what small disagreement looks like, so the "
            "large disagreement in the other samples is recognisable."
        ),
        users=20_000,
        channels={
            "paid_search": (0.30, 0.35),
            "paid_social": (0.25, 0.25),
            "organic_search": (0.22, 0.28),
            "email": (0.18, 0.30),
            "display": (0.20, 0.10),
            "affiliate": (0.10, 0.12),
        },
        corruption_rate=0.02,
    ),
    Sample(
        slug="last-touch-trap",
        name="The last-touch trap",
        summary="A channel that closes almost everything and causes almost nothing.",
        shows=(
            "Branded search appears in nearly two thirds of journeys but barely moves the "
            "odds of conversion - people search the brand name because they have already "
            "decided. Its true influence is about 7%. Last touch gives it roughly 35%. "
            "The uncomfortable part is that Markov removal effect also over-credits it, "
            "because a channel present in almost every journey looks indispensable to any "
            "model that asks what happens when you remove it. Prevalence is not influence, "
            "and no amount of modelling separates them. Only an experiment does - which is "
            "what the incrementality panel is for."
        ),
        users=25_000,
        channels={
            "branded_search": (0.62, 0.04),
            "paid_social": (0.34, 0.40),
            "video": (0.26, 0.34),
            "display": (0.30, 0.22),
            "email": (0.16, 0.24),
        },
        corruption_rate=0.01,
        notes="The clearest single argument for not budgeting on last touch.",
    ),
    Sample(
        slug="long-consideration",
        name="Long consideration",
        summary="Considered purchases with many touches before a decision.",
        shows=(
            "Average path length is high, which is where the heuristics separate. "
            "Position-based protects the opening and closing touches, time decay "
            "concentrates credit near the conversion, and linear spreads it flat - on a "
            "two-touch path those are nearly the same answer, and on an eight-touch path "
            "they are not."
        ),
        users=18_000,
        channels={
            "organic_search": (0.52, 0.22),
            "content": (0.46, 0.26),
            "paid_search": (0.44, 0.24),
            "email": (0.40, 0.30),
            "webinar": (0.30, 0.34),
            "display": (0.38, 0.10),
            "paid_social": (0.36, 0.18),
            "review_site": (0.28, 0.20),
        },
        days=90,
        corruption_rate=0.02,
    ),
    Sample(
        slug="short-paths",
        name="Short paths",
        summary="Most conversions follow one or two touches.",
        shows=(
            "When journeys are short, every model converges - there is simply not much "
            "credit to divide, and the elaborate ones stop earning their complexity. "
            "This is the honest case for using last touch, and it is worth knowing which "
            "regime your own data is in before arguing about models."
        ),
        users=30_000,
        channels={
            "paid_search": (0.18, 0.40),
            "paid_social": (0.12, 0.30),
            "email": (0.10, 0.35),
            "affiliate": (0.08, 0.20),
        },
        corruption_rate=0.01,
    ),
    Sample(
        slug="messy-feed",
        name="Messy feed",
        summary="The same data, damaged the way vendor feeds are damaged.",
        shows=(
            "Fifteen per cent of these rows are broken: unparseable timestamps, missing "
            "user ids, revenue arriving as text, event types that mean nothing. Look at "
            "the rejection breakdown rather than the chart. Every bad row is counted and "
            "given a reason, because a pipeline that silently drops eight per cent of a "
            "feed is worse than one that fails loudly."
        ),
        users=20_000,
        channels={
            "paid_search": (0.30, 0.35),
            "paid_social": (0.25, 0.25),
            "organic_search": (0.22, 0.28),
            "email": (0.18, 0.30),
            "display": (0.20, 0.10),
            "affiliate": (0.10, 0.12),
        },
        corruption_rate=0.15,
        notes="Use this one to see the ingestion layer rather than the models.",
    ),
)

BY_SLUG = {sample.slug: sample for sample in SAMPLES}


def build(slug: str):
    """Return (records, ground_truth, sample) for one sample.

    Deterministic: the same slug always produces the same data, so a figure
    quoted from a sample stays true.
    """
    try:
        sample = BY_SLUG[slug]
    except KeyError:
        raise KeyError(f"unknown sample {slug!r}; choose from {', '.join(BY_SLUG)}")

    records, ground_truth = generate_events(
        users=sample.users,
        days=sample.days,
        channels=sample.channels,
        corruption_rate=sample.corruption_rate,
        seed=sample.seed,
    )
    return records, ground_truth, sample


def write_all(out_dir) -> list[Path]:
    """Materialise every sample into out_dir, two files each.

    ``<slug>.json`` holds the event records; ``<slug>.truth.json`` holds the
    answer key. A model scored outside this project needs both, so the CLI
    writes both rather than leaving the truth only reachable from Python.

    Args:
        out_dir: Directory to write into. Created if absent.

    Returns:
        Every path written, records and answer keys together, in sample order.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    written = []
    for sample in SAMPLES:
        records, ground_truth, _ = build(sample.slug)

        target = out / sample.filename
        with open(target, "w") as handle:
            json.dump(records, handle)
        written.append(target)

        truth_target = out / sample.truth_filename
        with open(truth_target, "w") as handle:
            json.dump(truth_payload(sample.slug, ground_truth), handle, indent=2)
        written.append(truth_target)
    return written


def truth_payload(slug: str, ground_truth: dict) -> dict:
    """The answer key as a self-describing object.

    Downloaded on its own, a bare mapping of channel to number says nothing
    about what the number measures, so the explanation travels with it.

    Args:
        slug: Which sample this answer key belongs to.
        ground_truth: ``{channel: share of true influence}``, summing to 1.0.

    Returns:
        A JSON-serialisable dict carrying the shares and their explanation.
    """
    sample = BY_SLUG[slug]
    return {
        "dataset": slug,
        "name": sample.name,
        "what_this_is": (
            "The share of converted revenue each channel genuinely earned, "
            "recorded when this dataset was simulated: every conversion's "
            "revenue split across the channels that caused it, in proportion to "
            "their true influence. Real attribution data has no equivalent - "
            "nobody chose the rules behind real customer behaviour, so nobody "
            "can look them up. That is the only reason these samples exist."
        ),
        "measure": "share of converted revenue, summing to 1.0",
        "ground_truth": ground_truth,
        "how_to_score": (
            f"Run your model on the records in {sample.filename}, normalise its "
            "output to shares, and compare per channel. Mean absolute error "
            "against these values is the headline number; also check whether the "
            "model ranks the channels in the right order, which matters more for "
            "budgeting than the decimals. Zero is not reachable: damaged rows "
            "and the lookback window hide part of what the simulation did, so a "
            "model handed the generator's own weights still scores around 0.5 "
            "share points. Read a score against that floor, not against zero."
        ),
        "caveat": (
            "Influence here is causal by construction: how much the channel "
            "moved the odds of converting, not how often it appeared. A channel "
            "can be in most journeys and still be worth almost nothing, which is "
            "what last-touch-trap demonstrates."
        ),
    }


def catalogue() -> list[dict]:
    """Sample metadata for the web layer, without generating any data."""
    return [
        {
            "slug": s.slug,
            "name": s.name,
            "summary": s.summary,
            "shows": s.shows,
            "notes": s.notes,
            "users": s.users,
            "channels": len(s.channels),
            "days": s.days,
            "corruption_rate": s.corruption_rate,
        }
        for s in SAMPLES
    ]
