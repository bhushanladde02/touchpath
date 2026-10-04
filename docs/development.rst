Development
===========

Setup
-----

.. code:: bash

   git clone https://github.com/bhushanladde02/touchpath.git
   cd touchpath
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[web,dev,docs]"

Tests
-----

.. code:: bash

   pytest -q          # 84 tests, about 9 seconds
   pytest -v          # see each one
   pytest tests/test_models.py -q

What the suite covers
~~~~~~~~~~~~~~~~~~~~~

+-----------------------------------+----------------------------------------------------------------------------+
| File                              | Covers                                                                     |
+===================================+============================================================================+
| ``test_schema.py``                | Timestamp formats, every rejection reason, dotted paths, field mapping     |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_ingest.py``                | Report counts, file dispatch, multi-source ingestion                       |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_paths.py``                 | Lookback windows, de-duplication, cross-user isolation, direct conversions |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_models.py``                | Model correctness against hand-computed values, revenue conservation       |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_incrementality.py``        | Statistics against simulated data with known lift                          |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_datasets.py``              | Sample generation, determinism, the web routes                             |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_end_to_end.py``            | The CLI and full pipeline runs                                             |
+-----------------------------------+----------------------------------------------------------------------------+
| ``test_web.py``                   | Dashboard render, uploads, API validation                                  |
+-----------------------------------+----------------------------------------------------------------------------+

The correctness tests worth knowing about
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

These enforce mathematical properties rather than checking that code runs:

-  A symmetric channel pair receives identical Shapley credit.
-  A null player receives no Shapley credit.
-  A single-channel chain has a removal effect of exactly 1.0.
-  Position-based produces exactly 40/20/40.
-  Every model conserves revenue to the cent.
-  ``last-touch-trap`` really does over-credit its closing channel — if that stops being true, the sample is lying and the test fails.

Documentation
-------------

.. code:: bash

   pip install -e ".[docs]"
   sphinx-build -b html docs docs/_build/html
   open docs/_build/html/index.html

Pages are reStructuredText; the API reference is autodoc from docstrings.
Build with ``-W`` to treat warnings as errors before committing.

Project layout
--------------

::

   touchpath/
   ├── src/touchpath/
   │   ├── schema.py            parse one record into an Event, or reject it
   │   ├── ingest.py            many records in, events plus a report out
   │   ├── paths.py             events in, conversion paths out
   │   ├── incrementality.py    holdout statistics
   │   ├── generate.py          synthetic data with known ground truth
   │   ├── datasets.py          the five named samples
   │   ├── cli.py               terminal interface
   │   ├── models/
   │   │   ├── base.py          AttributionResult and the credit helper
   │   │   ├── heuristic.py     first, last, linear, position, time decay
   │   │   ├── markov.py        removal effect
   │   │   └── shapley.py       exact and Monte Carlo
   │   └── web/
   │       ├── app.py           FastAPI routes
   │       ├── templates/       index, about, datasets
   │       └── static/          style.css, dashboard.js
   ├── tests/
   ├── docs/
   ├── Dockerfile
   ├── render.yaml
   └── DEPLOY.md

Conventions
-----------

**Models are pure functions** from paths to an ``AttributionResult``. No I/O, no global state. That is what makes them testable against hand-computed values.

**Nothing fails silently.** A record that cannot be parsed produces a reason, not an exception and not a guess.

**Revenue conservation is non-negotiable.** Any new model must tie out to actual revenue to the cent, and there is a test that enforces it.

**Docstrings explain why, not what.** The signature says what. Comments say why it is done this way and what it would break if changed.

Adding a model
--------------

1. Write it in ``models/``, taking ``paths`` and returning an ``AttributionResult``. Use the ``credit()`` helper from ``base.py`` so accumulation stays uniform.
2. Add a revenue-conservation test and at least one hand-computed case.
3. Register it in ``ALL_MODELS`` and ``MODEL_LABELS`` in ``web/app.py``, and in the CLI’s ``ALL_MODELS``.
4. Document it in :doc:`models`, including its failure mode. Every model has one.

Adding a sample dataset
-----------------------

Add a ``Sample`` to ``SAMPLES`` in ``datasets.py`` with channel frequencies and influence weights chosen to demonstrate something specific, then write the ``shows`` text explaining what to look for. If the sample is supposed to prove a point, add a test that asserts the point still holds — see ``test_last_touch_trap_over_credits_the_closing_channel``.

Roadmap
-------

-  Partitioned Parquet output by conversion date, with idempotent partition replacement for late-arriving data
-  A watermark table so downstream consumers only read dates every source has delivered
-  Higher-order Markov chains
-  Time decay on real timestamps rather than path position
-  Bayesian credible intervals on channel credit

Licence and credit
------------------

MIT. Built by `Bhushan Ladde <https://github.com/bhushanladde02>`__. Claude (Anthropic) was used as a pair-programming assistant during development; design decisions, validation and testing are the author’s own.
