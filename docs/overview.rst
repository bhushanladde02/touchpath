What this project is
====================

The problem, in one paragraph
-----------------------------

A customer sees a display ad on Monday, clicks a paid social post on Wednesday, searches your brand name on Friday, and buys. Four touches, one sale, $120 of revenue. Which channel earned the money?

There is no fact of the matter. The sale happened once; it cannot be re-run with the display ad removed to see what would have happened. Every answer to the question is a **model**, and different models give materially different answers on the same data.

That matters because budget gets allocated on those answers.

What nearly everyone does
-------------------------

**Last touch.** All credit to the final interaction before the sale. In the example above, branded search gets the entire $120.

Last touch is popular for good reasons: it needs no modelling, it is trivial to explain to a finance team, and it is unambiguous — there is exactly one last touch per conversion, so nobody argues about the method.

It is also systematically wrong in a specific, predictable direction. The touch closest to the sale is usually the one the customer initiated *after* they had already decided. Branded search is the clearest case: people type your brand name because they have already been convinced by something else. Credit it fully and you will conclude that branded search is your best channel, cut the display and social spend that created the demand, and then watch branded search volume fall without understanding why.

What touchpath does instead
---------------------------

It runs **seven models over identical journeys** and shows you where they disagree.

The disagreement is the product. A channel every model treats the same way is a safe budget decision. A channel with a fifteen percentage-point spread between models is a decision resting entirely on a modelling assumption that nobody chose deliberately — and you should know that before you move money.

Two of the six are counterfactual models, which ask a better question than “where in the path did this sit?”:

-  **Markov removal effect** builds a transition graph over all journeys and measures how much conversion probability is lost when a channel is removed from the graph entirely.
-  **Shapley value** computes each channel’s average marginal contribution across every possible coalition of channels it could belong to.

Both are well documented in the academic literature and rare in open source. They usually sit behind a platform that wants your data, your budget and an annual contract before it will tell you anything.

And then the honest part
------------------------

All seven models — the six plus ground truth where it exists — only ever divide up conversions that **already happened**. None of them can tell you whether those conversions would have happened anyway.

That is a different question, and it has a different answer: run an experiment. Hold out a randomly chosen group, show them nothing, and compare. The difference is **incremental** — caused by the advertising rather than merely correlated with it.

touchpath includes a holdout module for exactly this: two-proportion z-tests, confidence intervals, significance, required sample size, and a direct comparison of attributed conversions against incremental ones. That comparison is usually uncomfortable, which is rather the point.

The goal of the project
-----------------------

Three things, in order of importance.

**Make counterfactual attribution available to people who cannot buy it.** The models are not secret — they are in published papers. The implementations are behind paywalls. A small marketing team, an analyst at a non-profit, or a student should be able to run a Markov removal effect on their own data without a procurement process.

**Make the answer checkable.** A measurement tool you cannot inspect is an opinion with a dashboard. Every model here is implemented in readable Python and validated against hand-computed values: a symmetric channel pair must receive identical Shapley credit, a null player must receive none, a single-channel chain must have a removal effect of exactly 1.0, and every model must conserve revenue to the cent. Those are tests in the suite, not claims in a README.

**Be honest about the limits.** The documentation says plainly where the models break down, including the case where the sophisticated models fail in the same direction as the naive one. A tool that only tells you its good properties is marketing, not measurement.

What it is not
--------------

It is not a tracking system. It does not set cookies, fingerprint users, resolve identity across devices, or collect anything. It consumes event data you already have.

It is not a replacement for a measurement team. It gives you the models and the statistics; deciding what to do about a 15-point spread is judgment.

It is not a production ad server. It is a correct, readable, well-tested implementation of a set of measurement techniques, intended to be run on event exports.

Who it is for
-------------

-  **Marketing analysts** who want to see how much their last-touch numbers are misleading them, without buying a platform.
-  **Data engineers** building or maintaining an attribution pipeline, who want a reference implementation to compare against.
-  **Students and researchers** who want working, readable implementations of Markov removal effects and Shapley attribution with ground-truth data to validate against.
-  **Anyone evaluating an attribution vendor**, who would like to run the same journeys through an open implementation and see whether the numbers agree.

Next
----

:doc:`concepts` explains the measurement ideas properly — including what a counterfactual actually is, why the Markov model needs journeys that never converted, and the specific case where every model gets the same answer and all of them are wrong.
