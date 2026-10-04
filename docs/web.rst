Web dashboard and JSON API
==========================

.. code:: bash

   pip install -e ".[web]"
   touchpath serve                       # http://127.0.0.1:8000
   touchpath serve --host 0.0.0.0 --port 8080 --reload

Live instance: https://touchpath.onrender.com

--------------

Pages
-----

+-------------------------------+-------------------------------------------------------------+
| Route                         | What it does                                                |
+===============================+=============================================================+
| ``GET /``                     | The landing page: what the project is and where to go next. |
+-------------------------------+-------------------------------------------------------------+
| ``GET /dashboard``            | The dashboard. Choose a source, pick models, run.           |
+-------------------------------+-------------------------------------------------------------+
| ``POST /analyze``             | Form submission; returns the rendered dashboard.            |
+-------------------------------+-------------------------------------------------------------+
| ``GET /about``                | Same page as ``/``. Kept so older links keep working.       |
+-------------------------------+-------------------------------------------------------------+
| ``GET /datasets``             | The five sample datasets, with download and run.            |
+-------------------------------+-------------------------------------------------------------+
| ``GET /datasets/{slug}.json`` | Download one sample as raw event records.                   |
+-------------------------------+-------------------------------------------------------------+
| ``GET /docs``                 | Auto-generated OpenAPI reference.                           |
+-------------------------------+-------------------------------------------------------------+
| ``GET /healthz``              | Liveness probe.                                             |
+-------------------------------+-------------------------------------------------------------+

--------------

What the dashboard shows
------------------------

**Headline tiles** — conversions, revenue, average and maximum path length, channel count, and the rejected-row percentage.

**Revenue share by model** — a grouped bar chart, one group per channel, one bar per model. When ground truth exists, it appears as a distinct first bar. This is the main event: it makes disagreement visible at a glance.

**Model disagreement** — the percentage-point spread between the highest and lowest model for each channel, labelled *stable*, *some spread* or *model-dependent*. This is the number that tells you how much your budget decision rests on model choice.

**Ingestion** — rejected rows by cause.

**Markov removal effects** — the share of conversion probability lost if each channel did not exist.

**Full table** — every number, so nothing is conveyed by colour alone.

**Incrementality check** — treatment and control inputs wired to the holdout endpoint.


.. admonition:: A caution about the disagreement table
   :class: warning

   Model agreement is not correctness. In the ``last-touch-trap`` sample, ``branded_search`` shows a spread of only about 5 percentage points and is labelled *some spread* — because every model agrees. All of them are wrong by a factor of four. See :doc:`concepts`.


--------------

Analysis form
-------------

``POST /analyze``, ``multipart/form-data``:

================= ================================ ========
Field             Values                           Default
================= ================================ ========
``source``        ``demo``, ``sample``, ``upload`` ``demo``
``sample``        a dataset slug                   —
``events_file``   the uploaded file                —
``demo_users``    500 – 100,000                    20,000
``lookback_days`` 1 – 365                          30
``models``        repeated; any of the seven       all
================= ================================ ========

Uploads are capped at 25 MB, must be UTF-8, and must be ``.json``, ``.jsonl``, ``.ndjson``, ``.csv`` or ``.tsv``.

--------------

JSON API
--------

``POST /api/analyze``
~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

   curl -X POST https://touchpath.onrender.com/api/analyze \
     -H 'content-type: application/json' \
     -d '{
           "events": [
             {"user_id":"u1","timestamp":"2026-01-04 11:02:00","event_type":"impression","channel":"display"},
             {"user_id":"u1","timestamp":"2026-01-06 09:14:00","event_type":"click","channel":"paid_social"},
             {"user_id":"u1","timestamp":"2026-01-08 20:31:00","event_type":"purchase","revenue":120.00}
           ],
           "lookback_days": 30,
           "models": ["last", "markov", "shapley"]
         }'

Returns ingestion counts and reasons, path statistics, the channel list, one series per model with shares and revenue, the per-channel spread, and Markov removal effects when that model was requested.

``POST /api/incrementality``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

   curl -X POST https://touchpath.onrender.com/api/incrementality \
     -H 'content-type: application/json' \
     -d '{"treatment_users": 100000, "treatment_conversions": 2300,
          "control_users": 100000, "control_conversions": 2000}'

Returns rates, absolute and relative lift, confidence interval, p-value, significance flag and incremental conversions.

Errors
~~~~~~

Standard HTTP codes with a ``detail`` message: ``400`` for malformed input or a file with no usable events, ``404`` for an unknown sample slug, ``413`` for an oversized upload.

--------------

Privacy
-------

Uploads are parsed in memory, analysed, and discarded when the request finishes. Nothing is written to disk, nothing is logged, there is no account, no cookie and no database.

--------------

The chart
---------

Drawn as inline SVG by ``web/static/dashboard.js``. No charting library, so there is nothing to fetch from a CDN, it works offline, and there is no version drift.

Colours come from CSS custom properties, so light and dark stay in step. The categorical palette is checked for colour-vision-deficiency separation, and the full table underneath means no information is carried by colour alone.
