# Model card — traffic adjustment (a negative result)

**What was attempted.** Twelve years of observed vehicle counts on 1,335 Latvian roads, joined to the network through 20,789 usable kilometre markers, converted to a delay with the standard BPR function (alpha=0.15, beta=4.0).

**The finding: congestion does not matter here.**

|   damping | label                  |   mean_response_min |   cci |   beyond_target |
|----------:|:-----------------------|--------------------:|------:|----------------:|
|       0   | unaffected (free-flow) |               7.496 | 0.923 |          141228 |
|       0.5 | half a car's delay     |               7.502 | 0.923 |          141393 |
|       1   | delayed like a car     |               7.508 | 0.923 |          141393 |

Even treating a fire engine as an ordinary car in the queue, the national mean response moves from **7.50** to **7.51** minutes and the CCI does not move at all.

Latvia's roads are empty by the standards of a capacity function. The median secondary road carries **eleven vehicles in the peak hour** against a capacity of 1,400; only the A10 into Rīga (AADT 59,598) reaches V/C = 1.82, and such links are a rounding error in network length.

## What this does not say

It does **not** say urban response is unaffected by traffic. It says *link congestion* is not the mechanism. What delays a vehicle in Rīga is junction and signal delay, which neither AADT nor BPR captures, and the counts cover the numbered network while urban driving happens largely on unnumbered streets with no counts at all.

## The emergency damping parameter

Latvian law requires traffic to yield to a blue-light vehicle, and crews use the oncoming lane and hard shoulder, so a fire engine does not sit in the queue BPR describes. Damping runs **0.0, 0.5, 1.0** — 0 is unaffected, 1 treats the engine as a car. **1.0 is the pessimistic bound, not the expected case.** Applying the full delay would have inflated urban response times and flattered this project's own rural-gap thesis.

## A free consistency check that passed

|   overlapping_rows |   identical |   share_identical |   median_abs_diff |   median_rel_diff |
|-------------------:|------------:|------------------:|------------------:|------------------:|
|               5672 |        5583 |            0.9843 |                 0 |                 0 |

The 2012–2021 and 2014–2023 workbooks overlap on 2014–2021. Keeping the overlap rather than de-duplicating it turns a redundancy into a test.

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
