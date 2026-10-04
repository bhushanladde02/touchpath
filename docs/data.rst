Data: formats, samples and sources
==================================

Everything about getting data in — what the format is, how to generate test data, what the five built-in samples demonstrate, and where to find real-world event data.

--------------

The input format
----------------

A flat list of events. One row per thing that happened.

Accepted file types
~~~~~~~~~~~~~~~~~~~

========== ======================= =========================
Format     Extensions              Notes
========== ======================= =========================
JSON       ``.json``               A single array of objects
JSON Lines ``.jsonl``, ``.ndjson`` One object per line
CSV        ``.csv``                Header row required
TSV        ``.tsv``                Tab-delimited
Parquet    ``.parquet``            Read via DuckDB
========== ======================= =========================

Fields
~~~~~~

**Touch events** — an impression, click, view, open:

+-----------------------+-----------------------+----------------------------------------------------------+
| Field                 | Required              | Notes                                                    |
+=======================+=======================+==========================================================+
| ``user_id``           | yes                   | Any stable identifier. Joins events into a journey.      |
+-----------------------+-----------------------+----------------------------------------------------------+
| ``timestamp``         | yes                   | See formats below.                                       |
+-----------------------+-----------------------+----------------------------------------------------------+
| ``event_type``        | yes                   | ``impression``, ``click``, ``view``, ``open``, ``touch`` |
+-----------------------+-----------------------+----------------------------------------------------------+
| ``channel``           | yes                   | The channel to credit. Free text.                        |
+-----------------------+-----------------------+----------------------------------------------------------+
| ``campaign``          | no                    | Carried through, not used by the models.                 |
+-----------------------+-----------------------+----------------------------------------------------------+
| ``event_id``          | no                    | Useful for de-duplication upstream.                      |
+-----------------------+-----------------------+----------------------------------------------------------+

**Conversion events** — a purchase, signup, booking:

+-----------------------+-----------------------+------------------------------------------------------+
| Field                 | Required              | Notes                                                |
+=======================+=======================+======================================================+
| ``user_id``           | yes                   | Must match the touch events.                         |
+-----------------------+-----------------------+------------------------------------------------------+
| ``timestamp``         | yes                   |                                                      |
+-----------------------+-----------------------+------------------------------------------------------+
| ``event_type``        | yes                   | ``purchase``, ``conversion``, ``order``, ``signup``  |
+-----------------------+-----------------------+------------------------------------------------------+
| ``revenue``           | yes                   | Numeric. Strings that parse as numbers are accepted. |
+-----------------------+-----------------------+------------------------------------------------------+
| ``event_id``          | no                    |                                                      |
+-----------------------+-----------------------+------------------------------------------------------+

A minimal valid file:

.. code:: json

   [
     {"user_id": "u1", "timestamp": "2026-01-04 11:02:00", "event_type": "impression", "channel": "display"},
     {"user_id": "u1", "timestamp": "2026-01-06 09:14:00", "event_type": "click", "channel": "paid_social"},
     {"user_id": "u1", "timestamp": "2026-01-08 20:31:00", "event_type": "purchase", "revenue": 120.00}
   ]

Timestamp formats
~~~~~~~~~~~~~~~~~

Eleven textual formats are recognised, plus epoch seconds and epoch milliseconds. Among them:

::

   2026-01-04 11:02:00
   2026-01-04T11:02:00
   2026-01-04T11:02:00Z
   2026-01-04T11:02:00.123456
   2026-01-04
   04/01/2026 11:02:00
   1767524520          (epoch seconds)
   1767524520000       (epoch milliseconds)

Anything unrecognised is rejected with reason ``unparseable timestamp`` rather than guessed at. See :func:`touchpath.schema.parse_timestamp`.

Different field names
~~~~~~~~~~~~~~~~~~~~~

Use a ``FieldMap``. Dotted paths reach into nested JSON:

.. code:: python

   from touchpath import FieldMap, ingest_file

   mapping = FieldMap(
       user_id="customer.id",
       ts="created_at",
       event_type="kind",
       channel="source_name",
       revenue="total_price",
       type_aliases={"order_completed": "purchase"},
   )

   events, report = ingest_file("shopify.json", mapping=mapping)

``type_aliases`` maps your vendor’s event-type vocabulary onto the one touchpath understands.

--------------

What gets rejected, and why
---------------------------

Nothing is dropped silently. Every rejected row is counted against a reason:

+-----------------------------------+---------------------------------------------------+
| Reason                            | Cause                                             |
+===================================+===================================================+
| ``missing user_id``               | No identifier, so the event cannot join a journey |
+-----------------------------------+---------------------------------------------------+
| ``missing timestamp``             | No time, so it cannot be ordered                  |
+-----------------------------------+---------------------------------------------------+
| ``unparseable timestamp``         | Present, but in no recognised format              |
+-----------------------------------+---------------------------------------------------+
| ``missing event_type``            | Cannot tell a touch from a conversion             |
+-----------------------------------+---------------------------------------------------+
| ``unknown event_type``            | A type that is neither                            |
+-----------------------------------+---------------------------------------------------+
| ``missing channel``               | A touch with nothing to credit                    |
+-----------------------------------+---------------------------------------------------+
| ``revenue not numeric``           | Conversion revenue arrived as text                |
+-----------------------------------+---------------------------------------------------+
| ``negative revenue``              | A refund or a data error                          |
+-----------------------------------+---------------------------------------------------+

.. code:: python

   events, report = ingest_file("events.json")

   report.total        # rows seen
   report.accepted     # rows that became events
   report.rejected     # rows that did not
   report.reject_rate  # 0..1
   report.reasons      # Counter of reason -> count
   print(report.summary())

A reject rate above a few per cent is worth investigating before you look at any attribution number. It usually means a vendor changed something.

--------------

The five sample datasets
------------------------

Real attribution data has no answer key. You can compare models to each other but never tell which was closer to right. These five are simulated from explicit per-channel influence weights, so the truth **is** recorded and every model gets scored against it.

Seeds are fixed — the same slug always produces byte-identical data, so a figure quoted from a sample stays true.

retail-baseline
~~~~~~~~~~~~~~~

*A balanced direct-to-consumer mix, nothing pathological.*

Six channels, influence spread roughly as you would expect from a healthy retail programme. The models broadly agree.

**Start here**, so that the large disagreements in the other samples are recognisable as unusual.

last-touch-trap
~~~~~~~~~~~~~~~

*A channel that closes almost everything and causes almost nothing.*

``branded_search`` appears in 62% of journeys and has 7% true influence. Last touch gives it 35%.

The genuinely interesting part is that **Markov removal effect also over-credits it, at 30%** — a channel present in almost every journey looks indispensable to any model that asks what happens when you remove it. Prevalence is not influence, and no amount of modelling separates them.

This is the single most instructive dataset in the set. See :doc:`concepts` for the full table and explanation.

long-consideration
~~~~~~~~~~~~~~~~~~

*Considered purchases with many touches before a decision.*

Eight channels, a 90-day window, high average path length. This is where position-based, time-decay and linear stop agreeing — on a two-touch path they are nearly the same answer, and on an eight-touch path they are not.

short-paths
~~~~~~~~~~~

*Most conversions follow one or two touches.*

Every model converges. There is not much credit to divide, and the elaborate models stop earning their complexity.

This is the honest case **for** last touch, and it is worth knowing which regime your own data is in before arguing about models at all.

messy-feed
~~~~~~~~~~

*The same data, damaged the way vendor feeds are damaged.*

15% of rows are broken: unparseable timestamps, missing user ids, revenue as text, meaningless event types.

Look at the rejection breakdown rather than the chart. Every bad row is counted and given a reason.

Getting them
~~~~~~~~~~~~

**From the hosted dashboard** — https://touchpath.onrender.com/datasets has a download link and a one-click run for each.

**From the CLI:**

.. code:: bash

   touchpath datasets --list
   touchpath datasets --out datasets/

**From Python:**

.. code:: python

   from touchpath import datasets

   records, ground_truth, meta = datasets.build("last-touch-trap")
   print(meta.name, meta.summary)
   print(ground_truth)   # {channel: true influence share}

   datasets.catalogue()  # metadata for all five, without generating anything
   datasets.write_all("datasets/")

**From the running API:**

.. code:: bash

   curl -O https://touchpath.onrender.com/datasets/last-touch-trap.json

They are ordinary JSON arrays of event records. Nothing proprietary — load them into anything.

--------------

Generating your own synthetic data
----------------------------------

The sample datasets are thin wrappers over a general generator. Use it directly to make data with whatever properties you want to test:

.. code:: python

   from touchpath.generate import generate_events

   records, ground_truth = generate_events(
       users=20_000,
       days=60,
       channels={
           # channel: (how often it appears, how much it moves conversion odds)
           "paid_search":    (0.30, 0.45),
           "paid_social":    (0.25, 0.25),
           "display":        (0.20, 0.08),
           "email":          (0.15, 0.35),
       },
       base_conversion_rate=0.02,
       revenue_mean=120.0,
       corruption_rate=0.03,
       seed=42,
   )

The two numbers per channel are the lever. **Frequency** controls how often the channel appears in a journey; **influence** controls how much it raises the odds of conversion. Set a channel to high frequency and near-zero influence and you have built the last-touch trap yourself.

``corruption_rate`` injects the damage classes listed above, so you can test a pipeline against dirty input rather than a clean fixture.

``ground_truth`` comes back as the share of total influence per channel — what a perfect model would recover.

For incrementality testing there is a matching generator with a known true lift:

.. code:: python

   from touchpath.generate import generate_holdout

   holdout = generate_holdout(
       users_per_group=50_000,
       control_rate=0.020,
       true_lift=0.15,
       seed=42,
   )

--------------

Real-world data
---------------

Your own platforms
~~~~~~~~~~~~~~~~~~

Most ad platforms and analytics tools export a raw event log. What you want is **event-level** data, not aggregated reports — one row per impression, click or conversion, with a user identifier and a timestamp.

Common sources: Google Analytics 4 via the BigQuery export, Meta Ads offline conversion exports, your own server-side event stream, a CDP like Segment, or the orders table in your e-commerce platform joined to ad click IDs.

The join key is the hard part in practice. Attribution quality is bounded by identity resolution quality, and no model fixes a broken join.

Public datasets
~~~~~~~~~~~~~~~

**The Criteo attribution dataset** is the best known public multi-touch attribution dataset — roughly 16 million impressions across 30 days, with timestamps, campaign identifiers, conversion flags and an existing attribution label. It was released for research and is widely used in the literature. You will need to map its column names with a ``FieldMap``.

It is large, so start with a subset.

What to check before trusting any result
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

-  **Reject rate.** Above a few per cent, fix the feed first.
-  **Average path length.** Under 1.5 and the model choice barely matters.
-  **Direct share.** How much of your business attribution simply cannot explain.
-  **Lookback window.** Does 30 days match your actual purchase cycle?
-  **Identity coverage.** What fraction of conversions can you tie to any touch at all?

--------------

Privacy
-------

The hosted dashboard parses uploads in memory, analyses them, and discards them when the request finishes. Nothing is written to disk, nothing is logged, there is no account, no cookie and no database.

If that is still more trust than you want to extend — a reasonable position for customer data — install the package and run it locally. The hosted version exists so you can see what it does before deciding whether to install it.
