Glossary
========


.. glossary::

   Attribution
      Dividing credit for conversions that already happened among the channels that
      preceded them. An accounting exercise, not a causal claim.

   Attribution window
      See :term:`Lookback window`.

   Channel
      A marketing source — paid search, paid social, display, email, affiliate. Free
      text in touchpath; whatever your data calls them.

   Characteristic function
      In Shapley attribution, ``v(S)``: the value produced by a coalition ``S`` of
      channels. The basis for computing marginal contributions.

   Coalition
      A subset of channels, in the game-theoretic sense used by Shapley values.

   Control group
      The holdout. Users randomly assigned to see no advertising, so the treatment
      group can be compared against them.

   Contamination
      When the control group is exposed, or the treatment group is not, despite the
      assignment. Dilutes measured lift silently — nothing errors, the numbers are
      simply wrong.

   Conversion
      The outcome being measured: a purchase, signup or booking. Carries revenue and
      no channel.

   Counterfactual
      What would have happened otherwise. The question the Markov and Shapley models
      attempt to answer, and the question an experiment answers directly.

   Dark partition
      A date partition that never gets populated in a source system. Pipelines that
      rescan them on every run accumulate cost and log volume indefinitely.

   Dead end
      A journey containing touches that never resulted in a conversion. Essential
      evidence for the Markov model — see :term:`Non-converting journey`.

   De-duplication
      Collapsing consecutive repeats of the same channel in a path, so that a
      high-frequency channel does not swamp it.

   Direct
      The synthetic channel credited with conversions that had no touch inside the
      lookback window. An honest measure of what attribution cannot explain.

   Efficiency
      The Shapley property that individual values sum exactly to the total being
      divided. Preserved in touchpath by rescaling after sampling.

   Event
      One thing that happened to one user at one time. Either a :term:`Touch` or a
      :term:`Conversion`.

   Ground truth
      The true per-channel influence, which exists only in simulated data. What
      makes the sample datasets useful for validating a model.

   Heuristic model
      An attribution model that assigns credit by position in the path: first, last,
      linear, position-based, time decay.

   Holdout
      A randomised experiment in which a control group is shown no advertising, so
      that incremental effect can be measured rather than modelled.

   Incrementality
      The conversions actually caused by advertising, as distinct from those merely
      preceded by it. Measured by experiment, not by attribution.

   Incrementality ratio
      Incremental conversions divided by attributed conversions. How much of the
      credit attribution assigned was real.

   Journey
      Everything that happened to one user, in time order.

   Lift
      The difference in conversion rate between treatment and control. Absolute lift
      is the difference in rates; relative lift expresses it as a percentage of the
      control rate.

   Lookback window
      How far back before a conversion touches are counted. Default 30 days.

   Markov removal effect
      The share of total conversion probability lost when a channel is removed from
      the transition graph entirely. The basis for Markov attribution.

   Non-converting journey
      A user's touch sequence where that user never converted. Passing these to the
      Markov model is what allows it to penalise channels that appear mostly in dead
      ends.

   Null player
      A channel that adds nothing to any coalition. Must receive zero Shapley credit;
      enforced by a test.

   Path
      The ordered channels preceding one conversion, within the lookback window.
      What every attribution model consumes.

   Power
      The probability a test detects an effect that genuinely exists. Conventionally
      0.80. Used in sample-size planning.

   Prevalence
      How often a channel appears across journeys. Frequently mistaken for influence
      — the central caution of this project.

   p-value
      The probability of observing a difference at least this large if the
      advertising had no effect.

   Reject reason
      The recorded cause of a row failing to parse. Counted, never dropped silently.

   Shapley value
      A channel's average marginal contribution across every coalition it could
      join. From cooperative game theory.

   Spread
      The percentage-point gap between the highest and lowest model's credit for a
      channel. A wide spread means your decision depends on a modelling assumption.

   Symmetry
      The Shapley property that two channels contributing identically receive
      identical credit. Enforced by a test.

   Touch
      An interaction with a marketing channel — impression, click, view, open.
      Carries a channel and no revenue.

   Transition matrix
      The probabilities of moving between states in the Markov model: channel to
      channel, to conversion, or to null.

   Treatment group
      Users who see the advertising, compared against the control group in a holdout
      test.

   Two-proportion z-test
      The significance test used for holdout results, comparing two conversion
      rates.
