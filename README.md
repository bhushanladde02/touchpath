# touchpath

Multi-touch attribution for marketing measurement — heuristic, Markov-chain and Shapley-value models over raw event data, with incrementality testing to check whether the attributed credit was ever real.

Pure Python, one dependency (DuckDB, and only for Parquet). Runs on a laptop.

**Try it: [touchpath.onrender.com](https://touchpath.onrender.com)** — run the
[sample datasets](https://touchpath.onrender.com/datasets) or upload your own
event file. Nothing is stored. Hosted on a free tier, so the first request after
an idle period takes up to a minute to wake the instance.

**Documentation: [bhushanladde02.github.io/touchpath](https://bhushanladde02.github.io/touchpath/)**
— the concepts, every model and why it was chosen, the data format, the code
flow, and deployment.

```bash
pip install -e .
touchpath demo
```

---

## Why

Most attribution tooling stops at last touch. Last touch is cheap, explainable, and systematically wrong: it hands every conversion to the final click, flattering the bottom of the funnel and starving everything that created the demand in the first place.

The models that answer the real question — *what would happen to conversions if we turned this channel off* — are the counterfactual ones: Markov-chain removal effects and Shapley values. They're well documented in the literature and rare in open source. `touchpath` implements both, alongside the heuristics, so they can be compared on identical paths.

And because attribution only ever divides credit for conversions that already happened, there's a holdout module: lift, confidence intervals, required sample size, and a direct comparison of attributed versus incremental conversions. That comparison is usually uncomfortable, which is the point.

---

## What it does

**Ingestion** — JSON, JSONL, CSV, Parquet. Vendor field mappings with dotted paths for nested payloads. Eleven timestamp formats, epoch seconds and milliseconds. Malformed records are quarantined with a reason, never silently dropped.

**Path building** — journeys per user, ordered, with a lookback window, consecutive-touch de-duplication and optional path truncation.

**Attribution models**

| Model | What it does |
|---|---|
| `first` / `last` | All credit to the opening or closing touch |
| `linear` | Even split across the path |
| `position` | 40 / 20 / 40 — first and last carry most of the weight |
| `time_decay` | Exponential decay toward the conversion, configurable half-life |
| `markov` | Removal effect on a first-order Markov chain; uses non-converting journeys too |
| `shapley` | Average marginal contribution across coalitions; exact to 12 channels, Monte Carlo above |

**Incrementality** — two-proportion holdout tests, confidence intervals, significance, sample-size planning, and `compare_to_attribution()` to see how much of the credit was incremental.

**Synthetic data with ground truth** — the generator simulates journeys from explicit per-channel influence weights, so model output can be scored against the answer key. It also injects broken timestamps, missing ids and text revenue, so ingestion is tested against something that resembles a real feed.

---

## Use

```python
from touchpath import ingest_file, build_paths, path_stats
from touchpath.models import heuristic, markov, shapley

events, report = ingest_file("events.json")
print(report.summary())          # accepted / rejected, itemised by reason

paths = build_paths(events, lookback_days=30)
print(path_stats(paths))

print(heuristic.attribute(paths, "linear").table())
print(markov.attribute(paths).table())
print(shapley.attribute(paths).table())
```

Several vendors at once:

```python
from touchpath import FieldMap, ingest_sources

shopify = FieldMap(
    user_id="customer.id", ts="created_at", event_type="kind",
    channel="source_name", revenue="total_price",
    type_aliases={"order_completed": "purchase"},
)
events, report = ingest_sources(
    {"shopify": "shopify.json", "meta": "meta_ads.json"},
    mapping_by_source={"shopify": shopify},
)
```

Incrementality:

```python
from touchpath.incrementality import holdout_test, compare_to_attribution

result = holdout_test(
    treatment_users=100_000, treatment_conversions=2_300,
    control_users=100_000,   control_conversions=2_000,
)
print(result.summary())
print(compare_to_attribution(result, attributed_conversions=1_000))
# {'incrementality_ratio': 0.3, 'overstated_by': 700.0}
```

CLI:

```bash
touchpath generate --users 20000 --out events.json
touchpath report events.json
touchpath attribute events.json --model markov --lookback 30
touchpath compare events.json
touchpath incrementality --treatment 100000/2300 --control 100000/2000
touchpath sample-size --baseline 0.02 --lift 0.10
```

---

## Sample datasets

Real attribution data has no answer key, so you can compare models to each other
but never tell which one was closer. These five are simulated from explicit
per-channel influence weights, so the truth is recorded and every model is scored
against it. Seeds are fixed — the same slug always produces the same data.

| Dataset | What it shows |
|---|---|
| `retail-baseline` | A balanced mix where the models broadly agree. Start here. |
| `last-touch-trap` | A channel in two thirds of journeys with 7% true influence. Last touch gives it 35% — and so does Markov removal, because prevalence is not influence and no model separates them. Only an experiment does. |
| `long-consideration` | Long paths, where position-based, time-decay and linear stop agreeing. |
| `short-paths` | Mostly one or two touches. Every model converges; the honest case for last touch. |
| `messy-feed` | 15% damaged rows — broken timestamps, missing ids, text revenue. Read the reject breakdown, not the chart. |

```bash
touchpath datasets --list
touchpath datasets --out datasets/
```

They are also downloadable from the running dashboard at `/datasets`, as plain
JSON event records.

---

## Web dashboard

```bash
pip install -e ".[web]"
touchpath serve          # http://127.0.0.1:8000
```

Pages: `/` the dashboard, `/datasets` the sample data, `/about` what the project
is for, `/docs` the API reference.

Upload a JSON/JSONL/CSV/TSV event file or run the built-in sample, pick a lookback
window and the models to compare, and the dashboard shows:

- headline stats — conversions, revenue, average path length, reject rate
- a grouped bar chart of revenue share per channel for every model, drawn as
  inline SVG with no charting library or CDN dependency
- **model disagreement** — the percentage-point spread per channel, which is the
  number that tells you how much your budget decision rests on model choice
- the ingestion reject breakdown by cause
- Markov removal effects
- a full table view (so nothing is conveyed by colour alone)
- an incrementality calculator wired to the holdout endpoint

Dark mode is a selected palette, not an inverted one, and the categorical colours
are validated for colour-vision deficiency separation.

### JSON API

```bash
curl -X POST localhost:8000/api/analyze \
  -H 'content-type: application/json' \
  -d '{"events": [...], "lookback_days": 30, "models": ["last", "markov", "shapley"]}'

curl -X POST localhost:8000/api/incrementality \
  -H 'content-type: application/json' \
  -d '{"treatment_users": 100000, "treatment_conversions": 2300,
       "control_users": 100000, "control_conversions": 2000}'
```

Interactive docs at `/docs`, liveness at `/healthz`.

### Deploy

```bash
docker build -t touchpath . && docker run -p 8000:8000 touchpath
```

`render.yaml` and `Procfile` are included for Render / Railway / Fly.

For a permanent deployment on a free Oracle Cloud instance with a real hostname
and HTTPS — no cold starts, no sleeping — see [DEPLOY.md](DEPLOY.md).

---

## Documentation

Full documentation lives in `docs/` — what the project is for, every concept it
rests on, each model with its failure modes, the code flow module by module,
input formats and sample data, the CLI and API reference, deployment, and a
glossary.

```bash
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
open docs/_build/html/index.html
```

---

## Validation

`touchpath demo` generates journeys from known influence weights, runs every model, and scores each against that ground truth. A representative run (20,000 users, 3% corrupted records):

```
channel               truth      last     first    linear    markov   shapley
-----------------------------------------------------------------------------
affiliate              4.3%      7.1%      6.7%      6.7%      7.5%      6.7%
display                4.7%     11.4%     11.1%     11.8%     13.0%     11.8%
email                 15.1%     14.9%     14.1%     14.7%     14.3%     14.7%
organic_search        19.1%     18.7%     16.2%     17.5%     18.0%     17.5%
paid_search           39.0%     30.2%     29.8%     29.2%     27.5%     29.2%
paid_social           17.9%     17.6%     22.2%     20.1%     19.6%     20.1%
```

The models are also checked against hand-computed values: a symmetric channel pair must receive identical Shapley credit, a null player must receive none, a single-channel chain must have a removal effect of exactly 1.0, position-based must produce 40/20/40, and every model must conserve revenue exactly.

**Throughput** (MacBook-class hardware, single process):

| Scale | Records | Ingest | Paths | Markov | Shapley |
|---|---|---|---|---|---|
| 10k users | 12.5k | 0.09s | 0.04s | <0.01s | <0.01s |
| 100k users | 126k | 0.89s | 0.63s | 0.01s | 0.01s |

Attribution itself is cheap; ingestion and path construction dominate, which is the expected shape — the models run on aggregated paths, not raw events.

---

## Design decisions

**Rejects carry reasons.** A feed that silently drops 8% of rows after a vendor changes a date format is worse than one that fails loudly. `IngestReport` counts every rejection by cause, so a schema change is visible the same day rather than in next quarter's numbers.

**Credit always ties out.** Every model's attributed revenue equals actual revenue to the cent. Shapley values are efficient in theory, but sampling and subset-based characteristic functions drift; the implementation rescales so the total matches the ledger. A model whose numbers don't reconcile won't survive its first review.

**Markov uses non-converting journeys.** Removal effect computed only on converting paths rewards channels that appear in dead ends. Passing `non_converting` is what lets the model penalise them.

**Conversion probability by iteration, not matrix inversion.** Journeys are short, so the fixed-point iteration converges in a handful of passes — numerically stable, no linear-algebra dependency.

**Direct is a channel, not a gap.** Conversions with no touch in the window are credited to `direct` rather than discarded, so the totals remain honest about how much of the business attribution cannot explain.

**One normalised record.** Adding a vendor means writing a `FieldMap`, not a new pipeline. Dotted paths handle nested payloads without a flattening pass.

---

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 84 tests
```

Tests cover the web layer end to end (dashboard render, uploads, API validation), timestamp parsing across formats, rejection reasons, vendor field mapping, lookback windows, cross-user isolation, model correctness against hand-computed values, revenue conservation, Shapley sampling convergence, incrementality statistics against simulated data with known lift, and the CLI end to end.

---

## Roadmap

- Partitioned Parquet output by conversion date, with idempotent partition replacement for late-arriving data
- A watermark/control table so downstream consumers only read dates every source has delivered
- Higher-order Markov chains
- Time-decay using real timestamps rather than path position
- Bayesian credible intervals on channel credit

---

## License

MIT — see [LICENSE](LICENSE).

Built by [Bhushan Ladde](https://github.com/bhushanladde02). Claude (Anthropic) was used as a pair-programming assistant during development; design decisions, validation and testing are my own.
