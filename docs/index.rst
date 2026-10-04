touchpath
=========

**Multi-touch attribution for marketing measurement.** Seven models over raw event data — including the two counterfactual ones that are rare in open source — plus incrementality testing to check whether the credit they divide up was ever real.

Pure Python. One dependency, and only for Parquet. Runs on a laptop.


.. admonition:: Try it before you read any further
   :class: tip

   `touchpath.onrender.com <https://touchpath.onrender.com>`__ — run the `sample datasets <https://touchpath.onrender.com/datasets>`__ or upload your own event file. Nothing is stored. Hosted on a free tier, so the first request after an idle period takes up to a minute to wake the instance.


--------------

Start here
----------

If you have ten minutes and want to understand the whole thing, read these three pages in order:

1. **:doc:`overview`** — what the project is, what problem it solves, and why it exists at all.
2. **:doc:`concepts`** — the measurement ideas the code is built on. Attribution, counterfactuals, incrementality, and why a channel can look essential and be worthless.
3. **:doc:`architecture`** — how data moves through the system, module by module.

Everything else is reference you can reach for when you need it.

--------------

Everything else
---------------

+-----------------------------------+-------------------------------------------------------------+
| Page                              | What is in it                                               |
+===================================+=============================================================+
| :doc:`overview`                   | The problem, what the project does about it, and its goals  |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`concepts`                   | Attribution, counterfactuals, incrementality, data quality  |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`models`                     | Each of the seven models, with parameters and failure modes |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`quickstart`                 | Install and first run, in about two minutes                 |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`data`                       | Input formats, the five sample datasets, real-world sources |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`web`                        | The dashboard and the JSON API                              |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`cli`                        | Every command and flag                                      |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`architecture`               | Module-by-module code flow and design decisions             |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`api/index`                  | Generated API reference                                     |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`development`                | Tests, layout, conventions, how to add a model              |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`deployment`                 | How the live instance runs, and three other ways            |
+-----------------------------------+-------------------------------------------------------------+
| :doc:`glossary`                   | Every term, defined                                         |
+-----------------------------------+-------------------------------------------------------------+


.. toctree::
   :hidden:
   :caption: Understanding it

   overview
   concepts
   models



.. toctree::
   :hidden:
   :caption: Using it

   quickstart
   data
   web
   cli



.. toctree::
   :hidden:
   :caption: Building on it

   architecture
   api/index
   development
   deployment



.. toctree::
   :hidden:
   :caption: Reference

   glossary


--------------

The shortest possible summary
-----------------------------

Marketing attribution answers the question *“which channels get credit for this sale?”* Nearly everyone answers it with **last touch** — all credit to the final click — because it is cheap and explainable. It is also systematically wrong: it flatters whatever closes and starves whatever created the demand.

touchpath implements seven models over the same journeys so you can see how much your answer depends on the model you picked:

+-----------------------------------+----------------------------------------------------------------------+
| Model                             | How it assigns credit                                                |
+===================================+======================================================================+
| First touch                       | All of it to the opening touch                                       |
+-----------------------------------+----------------------------------------------------------------------+
| Last touch                        | All of it to the closing touch                                       |
+-----------------------------------+----------------------------------------------------------------------+
| Linear                            | Split evenly across the path                                         |
+-----------------------------------+----------------------------------------------------------------------+
| Position 40/20/40                 | Weighted toward first and last                                       |
+-----------------------------------+----------------------------------------------------------------------+
| Time decay                        | Exponentially weighted toward the conversion                         |
+-----------------------------------+----------------------------------------------------------------------+
| **Markov removal effect**         | How much conversion probability is lost if the channel did not exist |
+-----------------------------------+----------------------------------------------------------------------+
| **Shapley value**                 | Average marginal contribution across every coalition of channels     |
+-----------------------------------+----------------------------------------------------------------------+

The last two are counterfactual: they ask what would happen without a channel, rather than dividing credit by position. That is a different and better question.

And then — because all seven of those still only divide up conversions that *already happened* — there is a holdout module that measures how many conversions a channel actually **caused**.


.. admonition:: The uncomfortable finding
   :class: warning

   The `last-touch-trap sample <https://touchpath.onrender.com/datasets>`__ contains a channel with 7% true influence that last touch credits with 35%. The Markov removal effect, which is supposed to fix exactly this, credits it with 30%.

   A channel present in two thirds of all journeys looks indispensable to *any* model that asks what happens when you remove it. Prevalence is not influence, and no amount of modelling separates them. Only an experiment does. That finding is why the incrementality module exists, and it is explained in full under :doc:`concepts`.
