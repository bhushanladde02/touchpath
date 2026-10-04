Quickstart
==========

From nothing to a scored attribution comparison in about two minutes.

--------------

Install
-------

.. code:: bash

   git clone https://github.com/bhushanladde02/touchpath.git
   cd touchpath
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .

Python 3.10 or newer. The core library has **one** dependency — DuckDB, and only for reading Parquet.

Optional extras:

.. code:: bash

   pip install -e ".[web]"   # the dashboard: FastAPI, uvicorn, Jinja2
   pip install -e ".[dev]"   # pytest and the test suite
   pip install -e ".[docs]"  # Sphinx, to build this documentation

--------------

See it work
-----------

.. code:: bash

   touchpath demo

This generates 20,000 synthetic user journeys from known channel influence weights, corrupts 3% of the rows the way real feeds get corrupted, ingests them, builds paths, runs five models, and scores each one against the answer key.

Expect something close to:

::

   channel               truth      last     first    linear    markov   shapley
   -----------------------------------------------------------------------------
   affiliate              4.3%      7.1%      6.7%      6.7%      7.5%      6.7%
   display                4.7%     11.4%     11.1%     11.8%     13.0%     11.8%
   email                 15.1%     14.9%     14.1%     14.7%     14.3%     14.7%
   organic_search        19.1%     18.7%     16.2%     17.5%     18.0%     17.5%
   paid_search           39.0%     30.2%     29.8%     29.2%     27.5%     29.2%
   paid_social           17.9%     17.6%     22.2%     20.1%     19.6%     20.1%

The ``truth`` column is what a perfect model would recover. Every other column is a model’s attempt. That column exists only because the data was simulated — on real data there is no answer key, which is the whole reason the sample datasets are useful.

--------------

Run the dashboard
-----------------

.. code:: bash

   pip install -e ".[web]"
   touchpath serve

Open http://127.0.0.1:8000. Four pages:

+-----------------------------------+-------------------------------------------------------------------+
| Path                              | What it is                                                        |
+===================================+===================================================================+
| ``/``                             | The dashboard — demo data, a sample dataset, or your own upload   |
+-----------------------------------+-------------------------------------------------------------------+
| ``/datasets``                     | Five sample datasets, each downloadable and runnable in one click |
+-----------------------------------+-------------------------------------------------------------------+
| ``/about``                        | What the project is for, in plain language                        |
+-----------------------------------+-------------------------------------------------------------------+
| ``/docs``                         | Auto-generated OpenAPI reference for the JSON API                 |
+-----------------------------------+-------------------------------------------------------------------+

Start with ``/datasets`` and run **The last-touch trap**. It makes the central argument of the project visible in one chart.

--------------

Run your own data
-----------------

The shortest useful script:

.. code:: python

   from touchpath import ingest_file, build_paths, path_stats
   from touchpath.models import heuristic, markov, shapley

   events, report = ingest_file("events.json")
   print(report.summary())          # accepted / rejected, itemised by reason

   paths = build_paths(events, lookback_days=30)
   print(path_stats(paths))         # conversions, revenue, average path length

   print(heuristic.attribute(paths, "last").table())
   print(markov.attribute(paths).table())
   print(shapley.attribute(paths).table())

Read :doc:`data` for the input format and the field names.

--------------

Several vendors at once
-----------------------

Different sources name their fields differently. Describe each one with a ``FieldMap`` rather than reshaping the files first:

.. code:: python

   from touchpath import FieldMap, ingest_sources

   shopify = FieldMap(
       user_id="customer.id",       # dotted paths reach into nested payloads
       ts="created_at",
       event_type="kind",
       channel="source_name",
       revenue="total_price",
       type_aliases={"order_completed": "purchase"},
   )

   events, report = ingest_sources(
       {"shopify": "shopify.json", "meta": "meta_ads.json"},
       mapping_by_source={"shopify": shopify},
   )

Sources without an entry in ``mapping_by_source`` use the default field names.

--------------

Check incrementality
--------------------

.. code:: python

   from touchpath.incrementality import holdout_test, compare_to_attribution

   result = holdout_test(
       treatment_users=100_000, treatment_conversions=2_300,
       control_users=100_000,   control_conversions=2_000,
   )
   print(result.summary())

   print(compare_to_attribution(result, attributed_conversions=1_000))
   # {'incrementality_ratio': 0.3, 'overstated_by': 700.0}

Attribution credited this channel with 1,000 conversions. The experiment says it caused 300.

--------------

Run the tests
-------------

.. code:: bash

   pip install -e ".[dev]"
   pytest -q

84 tests. They cover timestamp parsing across formats, every rejection reason, vendor field mapping, lookback windows, cross-user isolation, model correctness against hand-computed values, revenue conservation, Shapley sampling convergence, incrementality statistics against simulated data with known lift, the sample datasets, the CLI, and the web layer end to end.

--------------

Where to go next
----------------

-  :doc:`concepts` — the ideas, if you skipped them.
-  :doc:`data` — input formats, sample data, and real-world sources.
-  :doc:`cli` — every command and flag.
-  :doc:`architecture` — how it is put together.
