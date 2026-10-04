Command line reference
======================

Installed as ``touchpath`` when the package is installed. Every subcommand is a thin wrapper over the library — nothing happens here that you cannot do in Python.

.. code:: bash

   touchpath --help
   touchpath <command> --help

--------------

``demo``
--------

End-to-end run on synthetic data with a known answer key. The fastest way to see what the project does.

.. code:: bash

   touchpath demo
   touchpath demo --users 50000

=========== ======= ===============
Flag        Default Meaning
=========== ======= ===============
``--users`` 20000   Simulated users
=========== ======= ===============

Generates journeys, ingests them, builds paths, runs five models and scores each against ground truth, printing mean absolute error per model.

--------------

``generate``
------------

Write synthetic events to a file.

.. code:: bash

   touchpath generate --users 20000 --out events.json

================ =============== ==============================
Flag             Default         Meaning
================ =============== ==============================
``--users``      5000            Simulated users
``--days``       60              Length of the simulated period
``--corruption`` 0.02            Share of rows damaged
``--seed``       42              Fixed for reproducibility
``--out``        ``events.json`` Output path
================ =============== ==============================

Also prints the ground-truth influence share, so you can check a model against it afterwards.

--------------

``datasets``
------------

The five named sample datasets.

.. code:: bash

   touchpath datasets --list
   touchpath datasets --out datasets/

========== ============ ==========================
Flag       Default      Meaning
========== ============ ==========================
``--list`` off          Print the samples and exit
``--out``  ``datasets`` Directory to write into
========== ============ ==========================

Seeds are fixed, so a given slug always produces identical data. See :doc:`data` for what each one demonstrates.

--------------

``report``
----------

Ingestion and path statistics. Run this first on any new file.

.. code:: bash

   touchpath report events.json
   touchpath report events.json --lookback 14

============== ======= ==========================
Flag           Default Meaning
============== ======= ==========================
``--lookback`` 30      Attribution window in days
============== ======= ==========================

Prints the ingestion summary with rejection reasons, then conversions, revenue, direct conversions, average and maximum path length, and channel count.

--------------

``attribute``
-------------

Run one model.

.. code:: bash

   touchpath attribute events.json --model markov
   touchpath attribute events.json --model time_decay --lookback 14 --verbose
   touchpath attribute events.json --model shapley --json

============== ======== ==================================
Flag           Default  Meaning
============== ======== ==================================
``--model``    ``last`` One of the seven
``--lookback`` 30       Window in days
``--json``     off      Also print machine-readable output
``--verbose``  off      Include the ingestion report
============== ======== ==================================

--------------

``compare``
-----------

Run several models side by side.

.. code:: bash

   touchpath compare events.json
   touchpath compare events.json --models last markov shapley

============== ========= ==============
Flag           Default   Meaning
============== ========= ==============
``--lookback`` 30        Window in days
``--models``   all seven Subset to run
============== ========= ==============

The useful output is the spread between columns. A channel where every model agrees is a safe decision; a channel with a wide spread is not.

--------------

``incrementality``
------------------

Holdout test statistics.

.. code:: bash

   touchpath incrementality --treatment 100000/2300 --control 100000/2000
   touchpath incrementality --treatment 50000/1150 --control 50000/1000 --confidence 0.99

================ ======== =============================
Flag             Default  Meaning
================ ======== =============================
``--treatment``  required ``USERS/CONVERSIONS``
``--control``    required ``USERS/CONVERSIONS``
``--confidence`` 0.95     One of 0.80, 0.90, 0.95, 0.99
================ ======== =============================

--------------

``sample-size``
---------------

How many users per group you need. **Run this before the test, not after.**

.. code:: bash

   touchpath sample-size --baseline 0.02 --lift 0.10
   touchpath sample-size --baseline 0.02 --lift 0.05 --power 0.90

================ ======== ======================================
Flag             Default  Meaning
================ ======== ======================================
``--baseline``   required Current conversion rate, e.g. ``0.02``
``--lift``       required Relative lift to detect, e.g. ``0.10``
``--confidence`` 0.95     0.80, 0.90, 0.95 or 0.99
``--power``      0.80     0.80, 0.90 or 0.95
================ ======== ======================================

An underpowered holdout costs real revenue in withheld advertising and returns a result you cannot act on.

--------------

``serve``
---------

Run the dashboard.

.. code:: bash

   touchpath serve
   touchpath serve --host 0.0.0.0 --port 8080 --reload

============ ============= ===========================================
Flag         Default       Meaning
============ ============= ===========================================
``--host``   ``127.0.0.1`` Bind address
``--port``   8000          Port
``--reload`` off           Auto-reload on code change, for development
============ ============= ===========================================

Requires the web extra: ``pip install -e ".[web]"``. Binding to ``127.0.0.1`` means the app is not exposed directly — put a reverse proxy in front for anything public. See :doc:`deployment`.
