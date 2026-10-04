The models in detail
====================

Seven callable models across three modules. All of them take ``paths`` (from :func:`touchpath.paths.build_paths`) and return an :class:`~touchpath.models.base.AttributionResult`.

Read :doc:`concepts` first if you have not — this page assumes the vocabulary.

--------------

The difference between them, at a glance
----------------------------------------

+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| Model                 | Credit goes to                                                  | Why use it                                                                   | Where it misleads                                                      |
+=======================+=================================================================+==============================================================================+========================================================================+
| **Last touch**        | The final touch                                                 | Industry default; simple, unambiguous, easy to reconcile against other tools | Over-credits whatever sits closest to existing intent                  |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **First touch**       | The opening touch                                               | Answers what introduced this customer                                        | Over-credits awareness; ignores what closed                            |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **Linear**            | Split evenly                                                    | Makes no claim about which position mattered                                 | An incidental impression counts as much as the decisive email          |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **Position 40/20/40** | Weighted to the ends                                            | Encodes an explicit belief about intro and close                             | That belief may be wrong; the middle is often where persuasion happens |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **Time decay**        | Weighted toward conversion                                      | Recency as a proxy for influence                                             | Decays by path position, not real elapsed time                         |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **Markov removal**    | Proportional to conversion probability lost without the channel | **Counterfactual** — asks what a budget decision actually needs              | A ubiquitous channel looks indispensable regardless of influence       |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+
| **Shapley value**     | Average marginal contribution across coalitions                 | **Counterfactual** — symmetry, null player and efficiency guarantees         | Expensive above ~12 channels; switches to sampling and rescales        |
+-----------------------+-----------------------------------------------------------------+------------------------------------------------------------------------------+------------------------------------------------------------------------+

The deeper split is between the first five and the last two. The heuristics ask **“where in the path did this sit?”** The counterfactual models ask **“what would happen without it?”** Only the second question is the one you have when deciding whether to cut a budget line.

--------------

Why these seven and not others
------------------------------

**The five heuristics are the industry standard set.** Every commercial attribution tool implements first, last, linear, position-based and time decay. Including them is not because they are good — last touch in particular is the thing this project argues against — but because they are what your existing numbers were produced with. Without them you could not reconcile touchpath’s output against the platform you already use, and an unreconcilable number is an ignorable number.

**The two counterfactual models are the reason the project exists.** Markov removal effects and Shapley values are well documented in the academic literature and rare in open source. They almost always sit behind a platform that wants your data, your budget and an annual contract. Implementing them in readable Python, with the validation tests to prove they are right, is the whole point.

What was deliberately left out
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Data-driven or machine-learned attribution.** Several vendors offer a model that fits weights from your own conversion data — gradient boosting over path features, or similar. These can perform well. They are also unverifiable: you cannot hand-check the answer, you cannot explain to a finance team why a channel moved, and you cannot tell whether the model learned something real or overfitted to last quarter. A project whose stated goal is *make the answer checkable* cannot ship a model nobody can check.

**Custom rule-based models.** “Give 60% to paid social because that is where our growth is” is not a model, it is a conclusion dressed as one. Position-based already covers the legitimate version of this — an explicit, defensible weighting you can state and argue about.

**Higher-order Markov chains.** Second- and third-order chains condition on sequences of channels rather than single states, and can capture ordering effects the first-order model misses. They need considerably more data to estimate reliably, and on typical path lengths the gain is small. It is on the roadmap, not in the current version.

**Survival and hazard models.** Genuinely interesting for time-to-conversion questions, and a different enough problem that mixing them into an attribution comparison would confuse more than it clarified.

The honest summary
~~~~~~~~~~~~~~~~~~

Five models you probably already use, so you can compare. Two models you probably cannot buy without a contract, implemented so you can read them. And an incrementality module, because all seven of them answer a question that is less important than the one the experiment answers.

--------------

Heuristic models
----------------

All five live in ``touchpath.models.heuristic`` behind one function.

.. code:: python

   from touchpath.models import heuristic

   heuristic.attribute(paths, model="last")
   heuristic.attribute(paths, model="position", first_weight=0.4, last_weight=0.4)
   heuristic.attribute(paths, model="time_decay", half_life_days=7.0)

``model`` is one of ``first``, ``last``, ``linear``, ``position``, ``time_decay``. Hyphens are accepted (``time-decay``) and case is ignored.

first
~~~~~

All credit to the opening touch.

**Use it to answer:** what introduces people to us? **It over-credits:** awareness channels, and anything that happens to be cheap enough to achieve wide reach.

last
~~~~

All credit to the closing touch. The industry default.

**Use it to answer:** what is in front of people when they decide? **It over-credits:** branded search, retargeting, affiliate coupon sites — in general, anything positioned close to existing intent.

linear
~~~~~~

Even split across every touch in the path.

**Use it to answer:** what is involved, without claiming to know what mattered? **Its weakness:** an incidental display impression counts exactly as much as the email that persuaded them.

position
~~~~~~~~

Weighted toward the ends. Defaults give 40% to the first touch, 40% to the last, and spread the remaining 20% across the middle.

.. code:: python

   heuristic.attribute(paths, model="position", first_weight=0.3, last_weight=0.5)

``first_weight`` and ``last_weight`` must leave room for the middle — they should sum to less than 1.0.

**Encodes the belief:** introduction and closing are what matter, the middle is support. That might be wrong for your business, but it is at least explicit.

time_decay
~~~~~~~~~~

Exponential weighting toward the conversion, with a configurable half-life in days.

.. code:: python

   heuristic.attribute(paths, model="time_decay", half_life_days=3.0)

A shorter half-life concentrates credit nearer the conversion; 7.0 is the default.


.. admonition:: A known limitation
   :class: note

   The current implementation decays by **path position** rather than by the real elapsed time between touches. On evenly spaced journeys these are nearly the same thing; on journeys with a long gap followed by a burst, they are not. Decaying on actual timestamps is on the roadmap.


compare
~~~~~~~

A convenience wrapper that runs several heuristics at once.

.. code:: python

   from touchpath.models import heuristic

   results = heuristic.compare(paths)
   results = heuristic.compare(paths, models=("first", "last", "linear"))

--------------

Markov removal effect
---------------------

.. code:: python

   from touchpath.models import markov
   from touchpath.paths import non_converting_journeys

   result = markov.attribute(paths)
   result = markov.attribute(paths, non_converting=non_converting_journeys(events))

**How it works.** Journeys become walks through a graph whose states are channels, plus ``start``, ``conversion`` and ``null``. Transition counts across all journeys become transition probabilities. From that matrix, the model computes the probability that a walk starting at ``start`` reaches ``conversion``.

Then, for each channel in turn, it removes that channel from the graph — walks that would have passed through it go to ``null`` instead — and recomputes. The drop in conversion probability is that channel’s **removal effect**. Credit is allocated in proportion to removal effects.

**Why iteration rather than matrix inversion.** Journeys are short, so a fixed-point iteration converges in a handful of passes. It is numerically stable and keeps the dependency list at zero for this module.

**The ``non_converting`` argument** is the part most implementations skip, and it is explained at length in :doc:`concepts`. Short version: without journeys that never converted, a channel that appears constantly in dead ends cannot be penalised, because every path in your sample ended in a conversion by definition.

**Removal effects are available directly** on the result, which is often more interesting than the credit split:

.. code:: python

   result = markov.attribute(paths)
   result.meta["removal_effects"]
   # {'paid_search': 0.43, 'display': 0.35, ...}

A removal effect near 1.0 means essentially every conversion passed through that channel. Note that this is a statement about the graph, not about causation — see the prevalence warning in :doc:`concepts`.


.. admonition:: Failure mode
   :class: warning

   A channel present in a very large share of all journeys will show a large removal effect regardless of its true influence, because removing it breaks most paths. This is the single most important limitation of the model and it is not fixable within the model. Use a holdout.


--------------

Shapley value
-------------

.. code:: python

   from touchpath.models import shapley

   result = shapley.attribute(paths)
   result = shapley.attribute(paths, exact_limit=12, samples=10_000, seed=7)

**How it works.** Each channel is a player in a cooperative game. The characteristic function ``v(S)`` gives the value produced by a coalition ``S``. A channel’s Shapley value is its average marginal contribution across every coalition it could join.

**Parameters:**

``exact_limit`` (default 12) — the channel count up to which exact enumeration is used. Exact enumeration is ``2^n`` coalitions, so 12 channels is 4,096 subsets, which is instant. Above the limit the model switches to Monte Carlo.

``samples`` (default 10,000) — the number of random permutations sampled when above ``exact_limit``. More samples means less variance and more time.

``seed`` (default 7) — fixed so that repeated runs on the same data give the same answer. Reproducibility matters when someone asks why a number changed.

**Rescaling.** Shapley values are efficient in theory — they sum exactly to the total value. In practice, sampling and subset-based characteristic functions drift. The implementation rescales so attributed revenue matches actual revenue to the cent. A model whose numbers do not reconcile will not survive its first review.

**Tested properties:**

-  Two channels that contribute identically receive identical credit (symmetry).
-  A channel that adds nothing to any coalition receives nothing (null player).
-  The values sum to the total (efficiency).

--------------

What every model returns
------------------------

:class:`~touchpath.models.base.AttributionResult`, with:

.. code:: python

   result.model        # "markov"
   result.revenue      # {channel: revenue}
   result.conversions  # {channel: fractional conversion count}
   result.meta         # model-specific extras, e.g. removal_effects

   result.share()      # {channel: share of total revenue, 0..1}
   result.ranked()     # [(channel, revenue)] sorted descending
   result.rounded()    # a copy with values rounded, for display
   result.table()      # a formatted string for terminal output

Every model credits conversions that had no touches in the window to ``direct``, and revenue always sums to the actual total.

--------------

Incrementality
--------------

Not an attribution model — a different kind of measurement entirely. Lives in ``touchpath.incrementality``.

.. code:: python

   from touchpath.incrementality import (
       holdout_test, required_sample_size, compare_to_attribution,
   )

   result = holdout_test(
       treatment_users=100_000,
       treatment_conversions=2_300,
       control_users=100_000,
       control_conversions=2_000,
       confidence=0.95,
   )
   print(result.summary())

``HoldoutResult`` carries the treatment and control rates, absolute and relative lift, the confidence interval on the absolute difference, the p-value, a significance flag, and the implied count of incremental conversions.

**Plan the test before running it:**

.. code:: python

   required_sample_size(baseline_rate=0.02, minimum_detectable_lift=0.10)
   # users needed per group to detect a 10% relative lift

Optional ``confidence`` (default 0.95) and ``power`` (default 0.80). Running an underpowered holdout is worse than running none — it costs real revenue in withheld advertising and returns a result you cannot act on.

**Then compare it to what attribution claimed:**

.. code:: python

   compare_to_attribution(result, attributed_conversions=1_000)
   # {'incrementality_ratio': 0.3, 'overstated_by': 700.0}

--------------

Choosing between them
---------------------

There is no single right model, but there is a reasonable process.

**Look at average path length first.** Under about 1.5, every model converges and the argument is academic — use last touch and spend your energy elsewhere. Above 3, the choice moves real money.

**Run all of them and look at the spread.** Channels where the models agree are safe to act on. Channels with a wide spread are where your budget decision rests on a modelling assumption, and those are the ones to test.

**Treat the counterfactual models as better, not correct.** They ask a better question than the heuristics. They are still correlational, and they fail together on ubiquitous channels.

**Calibrate against a holdout periodically.** Attribution for continuous day-to-day allocation; experiments to find out how far off the attribution runs. The ratio between them is the most valuable number in this whole library.
