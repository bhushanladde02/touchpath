Architecture and code flow
==========================

How data moves through the system, which module owns what, and why it is split this way.

--------------

The pipeline in one line
------------------------

::

   raw records → Event objects → Path objects → AttributionResult → table / chart / JSON

Five stages, each owned by one module, each independently testable.

::

                       ┌──────────────┐
     JSON/CSV/TSV ────▶│  schema.py   │  parse one record into an Event,
     Parquet           │              │  or reject it with a reason
                       └──────┬───────┘
                              │ Event
                       ┌──────▼───────┐
                       │  ingest.py   │  loop over records, collect an
                       │              │  IngestReport of what failed and why
                       └──────┬───────┘
                              │ list[Event] + IngestReport
                       ┌──────▼───────┐
                       │   paths.py   │  group by user, order by time, apply
                       │              │  the lookback window, build one Path
                       └──────┬───────┘  per conversion
                              │ list[Path]
             ┌────────────────┼────────────────┐
             │                │                │
      ┌──────▼─────┐  ┌───────▼──────┐  ┌──────▼──────┐
      │ heuristic  │  │   markov     │  │   shapley   │
      └──────┬─────┘  └───────┬──────┘  └──────┬──────┘
             └────────────────┼────────────────┘
                              │ AttributionResult
                       ┌──────▼───────┐
                       │  cli.py      │  terminal tables
                       │  web/app.py  │  HTML dashboard and JSON API
                       └──────────────┘

Two modules sit outside the main flow:

-  ``generate.py`` and ``datasets.py`` manufacture input with known ground truth.
-  ``incrementality.py`` answers a different question entirely and consumes counts rather than paths.

--------------

Why this shape
--------------

**One normalised record type.** Everything downstream of ``schema.py`` works on ``Event``, regardless of whether it came from JSON, CSV or Parquet, and regardless of what the vendor called its fields. Adding a source means writing a ``FieldMap``, not a new pipeline.

**Windowing lives in exactly one place.** Lookback, de-duplication and truncation are all in ``build_paths``. No model implements its own, so changing the window changes every model consistently and there is nowhere for the rules to drift apart.

**Models consume paths, not events.** Each model is a pure function from paths to a result. That makes them trivially testable — hand-write four paths, assert the exact credit — and it is why the correctness tests can check hand-computed values rather than approximations.

**The web layer does no attribution.** ``web/app.py`` parses input, calls the library, and shapes the response. The models stay testable without a server and the server stays testable without a browser.

--------------

Module by module
----------------

``schema.py`` — one record in, one Event or one rejection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The parsing boundary. Everything that can go wrong with an individual row goes wrong here, and nothing downstream has to defend against malformed input.

+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| Name                                      | Role                                                                                               |
+===========================================+====================================================================================================+
| :class:`~touchpath.schema.Event`          | Frozen dataclass. The normalised record.                                                           |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :class:`~touchpath.schema.FieldMap`       | Which source field maps to which canonical field, with dotted-path support and event-type aliases. |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :class:`~touchpath.schema.RejectReason`   | The fixed vocabulary of failure causes.                                                            |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :func:`~touchpath.schema.parse_timestamp` | Eleven textual formats plus epoch seconds and milliseconds.                                        |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :func:`~touchpath.schema.parse_event`     | Returns ``(Event, None)`` or ``(None, reason)``.                                                   |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :func:`~touchpath.schema.get_path`        | Dotted-path lookup into nested payloads.                                                           |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+
| :func:`~touchpath.schema.normalise_label` | Consistent casing and whitespace for channel names.                                                |
+-------------------------------------------+----------------------------------------------------------------------------------------------------+

``parse_event`` never raises on bad data and never guesses. It returns a reason.

``ingest.py`` — many records in, events plus a report out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+------------------------------------------+----------------------------------------------------+
| Name                                     | Role                                               |
+==========================================+====================================================+
| :class:`~touchpath.ingest.IngestReport`  | Totals, reject rate, and a ``Counter`` of reasons. |
+------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.ingest.ingest_records` | From an in-memory list.                            |
+------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.ingest.ingest_file`    | From a path; dispatches on extension.              |
+------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.ingest.ingest_sources` | Several files, each with its own ``FieldMap``.     |
+------------------------------------------+----------------------------------------------------+

The report is returned alongside the events rather than logged, so a caller cannot ignore it by accident.

``paths.py`` — events in, conversion paths out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

+--------------------------------------------------+----------------------------------------------------+
| Name                                             | Role                                               |
+==================================================+====================================================+
| :class:`~touchpath.paths.Path`                   | One conversion and the touches credited to it.     |
+--------------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.paths.build_paths`             | The windowing logic.                               |
+--------------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.paths.path_stats`              | Headline numbers — the sanity check you run first. |
+--------------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.paths.non_converting_journeys` | Dead-end journeys, for the Markov model.           |
+--------------------------------------------------+----------------------------------------------------+
| :func:`~touchpath.paths.channel_universe`        | Every channel seen, plus ``direct`` when relevant. |
+--------------------------------------------------+----------------------------------------------------+

**How ``build_paths`` works.** It first indexes touches per user into two parallel sorted lists — timestamps and channels. Then, for each conversion, it finds the window boundaries with ``bisect`` rather than scanning. Each conversion is two binary searches instead of a linear pass over that user’s events, which is what keeps the cost reasonable on large inputs.

``models/`` — paths in, credit out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``base.py`` holds :class:`~touchpath.models.base.AttributionResult` and the ``credit()`` helper that every model uses to record an allocation. Keeping accumulation in one place is why revenue conservation holds uniformly.

``heuristic.py``, ``markov.py`` and ``shapley.py`` implement the models described in :doc:`models`.

``incrementality.py`` — counts in, statistics out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Standalone. Takes four integers and returns a :class:`~touchpath.incrementality.HoldoutResult` with lift, confidence interval, p-value and significance. Also provides ``required_sample_size()`` for planning and ``compare_to_attribution()`` for the comparison that matters.

``generate.py`` and ``datasets.py`` — manufactured input
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``generate_events()`` simulates journeys from explicit per-channel influence weights and returns both the records and the ground truth. ``datasets.py`` wraps it in five named scenarios with fixed seeds and the prose explaining what each demonstrates.

``cli.py`` — the terminal interface
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Thin argparse dispatch. Each subcommand is a ``cmd_*`` function that calls the library and prints. No logic lives here that is not about formatting.

``web/app.py`` — the HTTP interface
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

FastAPI. Routes are documented in :doc:`web`. The important internal piece is ``analyse()``, which runs every requested model and shapes one payload used by both the HTML template and the JSON API — so the dashboard and the API can never disagree about a number.

--------------

A request end to end
--------------------

Following “run the last-touch-trap sample” through the system:

1. **Browser** posts to ``/analyze`` with ``source=sample``, ``sample=last-touch-trap``.
2. **``load_sample()``** builds the dataset — deterministic from a fixed seed — and memoises it so later requests skip regeneration.
3. **``ingest_records()``** parses 43,439 records into events, rejecting about 1% and recording why.
4. **``build_paths()``** indexes touches per user and builds one ``Path`` per conversion inside the 30-day window.
5. **``path_stats()``** produces the headline tiles.
6. **Each selected model** runs over the same paths.
7. **``analyse()``** computes per-channel shares, the spread between models, and attaches the ground truth.
8. **Jinja2** renders the page; the payload is also embedded as JSON.
9. **``dashboard.js``** reads that JSON and draws the grouped bar chart as inline SVG.

Total: well under a second after the first request.

--------------

Performance
-----------

========== ======= ====== ===== ====== =======
Scale      Records Ingest Paths Markov Shapley
========== ======= ====== ===== ====== =======
10k users  12.5k   0.09s  0.04s <0.01s <0.01s
100k users 126k    0.89s  0.63s 0.01s  0.01s
========== ======= ====== ===== ====== =======

Attribution itself is cheap. **Ingestion and path construction dominate**, which is the expected shape — the models run on aggregated paths, not on raw events.

Memory: the five sample datasets cached together occupy about 84 MB, and the whole service idles comfortably under 200 MB. That is why a 1 GB instance is enough.

The practical implication: if you need this to go faster, optimise parsing, not the models.

--------------

Design decisions worth knowing
------------------------------

**Rejects carry reasons.** A feed that silently drops 8% of rows after a vendor changes a date format is worse than one that fails loudly. A schema change becomes visible the same day rather than in next quarter’s numbers.

**Credit always ties out.** Every model’s attributed revenue equals actual revenue to the cent. Shapley values are efficient in theory, but sampling drifts, so the implementation rescales. A model whose numbers do not reconcile will not survive its first review.

**Conversion probability by iteration, not matrix inversion.** Journeys are short, so the fixed-point iteration converges in a handful of passes — numerically stable, no linear-algebra dependency.

**Direct is a channel, not a gap.** Conversions with no touch in the window are credited to ``direct`` rather than discarded, so the totals stay honest about how much of the business attribution cannot explain.

**One normalised record.** Adding a vendor means writing a ``FieldMap``, not a new pipeline. Dotted paths handle nested payloads without a flattening pass.

**No charting library.** The dashboard draws its own SVG. That keeps the page dependency-free — nothing to fetch from a CDN, works offline, no version drift — and lets the marks follow consistent rules in both light and dark themes.
