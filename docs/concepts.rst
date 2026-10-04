Concepts
========

Everything the code assumes you know, explained from scratch. If you read only one page of this documentation, read this one.

--------------

Events, touches and conversions
-------------------------------

The input to touchpath is a flat list of **events**. Each event is one thing that happened to one user at one moment.

Events come in two kinds:

**A touch** is an interaction with a marketing channel — an impression, a click, a video view, an email open. It has a channel attached.

**A conversion** is the outcome you care about — a purchase, a signup, a booking. It has revenue attached and no channel, because the conversion is not itself a marketing interaction.

.. code:: json

   {"user_id": "u001", "timestamp": "2026-01-04 11:02:00", "event_type": "impression", "channel": "display"}
   {"user_id": "u001", "timestamp": "2026-01-06 09:14:00", "event_type": "click",      "channel": "paid_social"}
   {"user_id": "u001", "timestamp": "2026-01-08 20:31:00", "event_type": "purchase",   "revenue": 120.00}

That is the whole data model. Everything else is derived from it.

--------------

Journeys and paths
------------------

A **journey** is everything that happened to one user, in time order.

A **path** is the part of a journey that precedes a particular conversion and falls inside the lookback window. Paths are what every attribution model actually consumes.

For the events above, with a 30-day lookback, the path is:

::

   display → paid_social   ⟹   $120.00

Three rules shape how paths are built, and each one is a deliberate decision you can change:

**Lookback window.** Only touches within *N* days before the conversion count. Default 30. A touch six months before a purchase almost certainly did not cause it, and including it would dilute every model. Set ``lookback_days=None`` to disable the window entirely.

**Consecutive de-duplication.** Ten display impressions in a row collapse to one. Without this, a channel that serves high frequency swamps the path and every model over-credits it — not because it is influential, but because it is noisy. Controlled by ``dedupe_consecutive``, on by default.

**Path truncation.** Optionally keep only the most recent *N* touches, via ``max_path_length``. Off by default.


.. admonition:: Direct conversions
   :class: note

   A conversion with no touches inside the window is credited to a synthetic channel called ``direct``. It is tempting to drop these, because they make the numbers look worse. Don’t. They are the honest measure of how much of your business attribution cannot explain, and hiding them makes every other channel’s share look larger than it is.


--------------

What attribution actually is
----------------------------

**Attribution divides credit for conversions that already happened.**

That sentence is worth reading twice, because almost every misuse of attribution comes from forgetting it. Attribution is an accounting exercise. You have 1,000 conversions and $120,000 of revenue; attribution decides which channels get which slices. The total never changes — every model here conserves revenue to the cent, and there is a test that enforces it.

What attribution cannot tell you is whether those 1,000 conversions would have happened without any advertising at all. That is the incrementality question, and it needs an experiment rather than a model.

--------------

The heuristic models
--------------------

Four models that assign credit by **position in the path**. They are simple, fast, and require no assumptions beyond the ordering.

**First touch** gives everything to the opening interaction. Answers “what introduced this customer to us?” Over-credits awareness channels.

**Last touch** gives everything to the closing interaction. Answers “what was in front of them when they decided?” Over-credits whatever sits closest to intent — usually branded search and retargeting.

**Linear** splits evenly across every touch. Makes no claim about which position matters, which is honest, but it also means a single incidental display impression counts as much as the email that actually persuaded them.

**Position-based (40/20/40)** gives 40% to the first touch, 40% to the last, and splits the remaining 20% across the middle. It encodes a specific belief: that introduction and closing are what matter and the middle is support. That belief might be wrong for your business, but at least it is explicit.

**Time decay** weights touches exponentially toward the conversion, with a configurable half-life. Encodes the belief that recency correlates with influence.


.. admonition:: The thing to notice
   :class: tip

   On a **two-touch path**, linear, position-based and time-decay give nearly identical answers. On an **eight-touch path** they diverge sharply.

   So before arguing about which heuristic is right, look at your average path length. If it is 1.3, the argument is pointless — every model will agree and last touch is fine. If it is 4.5, the choice is worth real money. The ``short-paths`` and ``long-consideration`` sample datasets exist to make this concrete.


--------------

Counterfactual models
---------------------

Here is the conceptual jump. The heuristics ask *“where in the path did this channel sit?”* The counterfactual models ask a fundamentally better question:

   **What would have happened if this channel did not exist?**

That is the question a marketer actually has when deciding whether to cut a budget line. Two models answer it, by different routes.

Markov removal effect
~~~~~~~~~~~~~~~~~~~~~

Model every journey as a walk through a graph. States are channels, plus a start state, a conversion state and a null (no-conversion) state. Count the transitions across all journeys and convert them to probabilities.

From that transition matrix you can compute the overall probability that a walk beginning at ``start`` reaches ``conversion``.

Now **delete one channel** from the graph — remove its node, and redirect every walk that passed through it to the null state — and recompute that probability. The drop is the channel’s **removal effect**: the share of conversion probability that disappears when the channel does.

Credit is allocated in proportion to removal effects.

Two implementation details worth knowing:

*Conversion probability is computed by iteration, not matrix inversion.* Journeys are short, so a fixed-point iteration converges in a handful of passes. It is numerically stable and avoids a linear-algebra dependency.

*Non-converting journeys matter.* See below — this is the most important and most frequently skipped part of the model.

Shapley value
~~~~~~~~~~~~~

Borrowed from cooperative game theory, where it answers: given a group that produced some value together, what is each member’s fair share?

Treat each channel as a player and each conversion as a payout. The **characteristic function** ``v(S)`` is the value produced by a coalition ``S`` of channels. A channel’s Shapley value is its **average marginal contribution** across every possible coalition it could join — that is, for every subset of the other channels, how much does adding this channel increase the value?

Shapley values have attractive theoretical properties, and touchpath tests for three of them directly:

-  **Symmetry** — two channels that contribute identically receive identical credit.
-  **Null player** — a channel that adds nothing to any coalition receives nothing.
-  **Efficiency** — the values sum to the total value being divided.

Efficiency is the one that needs care in practice. Exact enumeration is ``2^n`` coalitions, which is fine up to about twelve channels and intractable beyond. Above that threshold touchpath switches to Monte Carlo permutation sampling, and sampling introduces drift. The implementation **rescales so the total still ties out to actual revenue exactly** — because a model whose numbers do not reconcile will not survive its first review by a finance team.

--------------

Non-converting journeys
-----------------------

This is the subtlety that separates a correct Markov implementation from a plausible-looking one.

If you compute removal effects using only journeys that **converted**, you have a selection problem: every path in your data ended in a conversion by definition. A channel that appears constantly in dead ends — journeys that went nowhere — never shows up in your sample at all, so the model cannot penalise it. It will look useful purely because you threw away the evidence against it.

Feeding in journeys that never converted is what lets the model distinguish *“this channel appears before conversions”* from *“this channel appears before conversions more often than before non-conversions.”*

.. code:: python

   from touchpath.paths import build_paths, non_converting_journeys
   from touchpath.models import markov

   paths = build_paths(events, lookback_days=30)
   dead_ends = non_converting_journeys(events)

   result = markov.attribute(paths, non_converting=dead_ends)


.. admonition:: An honest measurement
   :class: warning

   Across the five sample datasets, passing non-converting journeys turns out to be **net neutral** for accuracy — it helps slightly on three and hurts slightly on two.

   That is not a bug in the implementation; it is a property of those particular datasets. The simulator’s channels all have non-negative influence, so none of them are genuinely dead-end channels in the sense the correction is designed for. On real data, where some channels really do correlate with abandonment, it matters considerably more.

   The function is in the library and documented. The dashboard does not use it, because claiming an improvement that was measured to be neutral would be exactly the kind of thing this project exists to argue against.


--------------

Prevalence is not influence
---------------------------

The single most important idea on this page, and the one that shaped the whole project.

The ``last-touch-trap`` sample dataset contains a channel called ``branded_search`` with these properties: it appears in **62% of all journeys**, and it has a **true influence of 7%**. It is ubiquitous and nearly worthless — exactly the branded search pattern described in :doc:`overview`.

Here is what the models say:

========================= ============================
Model                     Credit to ``branded_search``
========================= ============================
**True influence**        **7.0%**
Last touch                35.3%
First touch               31.8%
Linear                    33.4%
Position 40/20/40         33.5%
Time decay                33.5%
**Markov removal effect** **30.3%**
**Shapley value**         **33.4%**
========================= ============================

The counterfactual models — the sophisticated ones, the ones that are supposed to fix precisely this failure — are wrong in the same direction and by nearly the same amount.

**Why.** A channel present in two thirds of all journeys is load-bearing in the graph. Remove it and most paths break, so the removal effect is enormous. The Markov model is correctly answering the question it was asked: *what happens to this graph if this node disappears?* The answer is “a lot” — and that is true, and it is still not the same thing as “this channel caused conversions.”

**The general principle:** when a channel is present almost everywhere, correlation-based methods cannot separate its prevalence from its influence. No amount of modelling sophistication fixes this, because the information needed to separate them **is not in the observational data at all**.

Only an experiment can resolve it. Which is the next section.

--------------

Incrementality
--------------

An experiment answers what a model cannot.

Take your audience and split it at random into two groups. The **treatment** group sees the advertising. The **control** group — the holdout — sees nothing. Wait. Then compare conversion rates.

The difference is **incremental**: conversions caused by the advertising rather than merely preceded by it. Random assignment is what does the work, because it means the two groups differ in nothing except exposure.

touchpath’s ``incrementality`` module computes:

**Relative lift** — the percentage increase in conversion rate, treatment over control.

**Absolute lift and confidence interval** — the difference in rates, with the range of values consistent with the observed data at your chosen confidence level.

**Statistical significance** — a two-proportion z-test. The p-value is the probability of seeing a difference at least this large if the advertising actually did nothing.

**Incremental conversions** — the lift applied to the treatment population. The actual count caused.

**Required sample size** — how many users per group you need to detect a lift of a given size, given your baseline rate, confidence level and power. Run this *before* the test, not after. An underpowered holdout tells you nothing and costs you real revenue in withheld advertising.

**Attribution comparison** — ``compare_to_attribution()`` takes your attributed conversions and your measured incremental conversions and returns the ratio.

.. code:: python

   from touchpath.incrementality import holdout_test, compare_to_attribution

   result = holdout_test(
       treatment_users=100_000, treatment_conversions=2_300,
       control_users=100_000,   control_conversions=2_000,
   )
   print(result.summary())

   print(compare_to_attribution(result, attributed_conversions=1_000))
   # {'incrementality_ratio': 0.3, 'overstated_by': 700.0}

That last result reads: attribution gave this channel credit for 1,000 conversions. The experiment says it caused 300. The other 700 would have happened anyway.


.. admonition:: Why the holdout is also imperfect
   :class: note

   Holdouts cost money — you are deliberately withholding advertising from people who might have bought. They take time. They measure one channel at a time in a world where channels interact. And they are often hard to implement cleanly, because suppressing a channel for a specific group is not always possible.

   This is why attribution does not simply go away in favour of experiments. The practical answer is to use attribution continuously for day-to-day allocation, and calibrate it periodically against a holdout — using the ratio above to understand how far off your attributed numbers run.


--------------

Control group contamination
---------------------------

A holdout only works if the control group genuinely saw nothing.

Contamination is when people who were never exposed end up counted as exposed, or the reverse. The effect is to dilute the measured difference between groups, so real lift reads as smaller than it is — or, with contamination in the other direction, as larger.

The failure is silent. Nothing errors. Every job succeeds. The numbers are simply wrong, and nobody downstream can see it from the output.

The usual causes are mundane: survey panels sending questionnaires to their whole list rather than to verified exposed users, suppression that did not fully suppress, identity resolution merging two people into one, or a tagging change that quietly stopped recording exposures for a segment.

The practical defence is to validate the groups themselves as carefully as the result — check that everyone counted as exposed has an exposure record, check that nobody in control does, and watch those counts over time rather than once at setup.

--------------

Data quality as a first-class concern
-------------------------------------

A running theme in the implementation, and a deliberate design position.

**A pipeline that silently drops rows is worse than one that fails loudly.**

If a vendor changes a date format and 8% of your rows stop parsing, a quiet pipeline shows you a modest dip in volume that looks like seasonality. You find out next quarter, if at all. A loud pipeline tells you the same day.

touchpath never drops a malformed record silently. Every rejected row is counted and attributed to a reason:

+-----------------------------------+---------------------------------------------------------+
| Reason                            | Meaning                                                 |
+===================================+=========================================================+
| ``missing user_id``               | No user identifier, so the event cannot join a journey  |
+-----------------------------------+---------------------------------------------------------+
| ``missing timestamp``             | No time, so it cannot be ordered                        |
+-----------------------------------+---------------------------------------------------------+
| ``unparseable timestamp``         | Present but in no recognised format                     |
+-----------------------------------+---------------------------------------------------------+
| ``missing event_type``            | Cannot tell a touch from a conversion                   |
+-----------------------------------+---------------------------------------------------------+
| ``unknown event_type``            | A type that is neither touch nor conversion             |
+-----------------------------------+---------------------------------------------------------+
| ``missing channel``               | A touch with no channel to credit                       |
+-----------------------------------+---------------------------------------------------------+
| ``revenue not numeric``           | Conversion revenue arrived as text                      |
+-----------------------------------+---------------------------------------------------------+
| ``negative revenue``              | A refund or a data error — either way, not a conversion |
+-----------------------------------+---------------------------------------------------------+

The ``messy-feed`` sample dataset exists to exercise this: 15% of its rows are damaged in exactly these ways, so you can see the breakdown rather than read about it.

--------------

Next
----

-  :doc:`models` — each model in detail, with its parameters and failure modes.
-  :doc:`data` — the input format, and how to get data to try.
-  :doc:`architecture` — how all of this is actually wired together.
