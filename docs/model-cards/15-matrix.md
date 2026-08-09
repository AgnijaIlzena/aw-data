# Model card — Preparedness × Proximity

**What it is.** The join between the two projects: project #1's resilience horizon (days a household lasts) beside project #2's response time (minutes until help arrives), per community type.

**Deliberately two axes, never one number.** RHI measures endurance through a prolonged utility disruption; TTH measures arrival for an acute incident. A ratio would imply they describe one scenario.

| community_class   |   population |   mean_response_min |   share_beyond_23min |   cells |   n |   n_effective |   mean_rhi_days |   share_under_target_certain |   share_under_target_upper |   ci_low |   ci_high | thin_cell   |
|:------------------|-------------:|--------------------:|---------------------:|--------:|----:|--------------:|----------------:|-----------------------------:|---------------------------:|---------:|----------:|:------------|
| rural             |       547560 |              11.885 |                0.032 |   28839 | 247 |         153.4 |           3.621 |                        0.425 |                      0.683 |    0.609 |     0.756 | False       |
| urban_cluster     |       601789 |               6.3   |                0.003 |     617 | 330 |         241.8 |           2.601 |                        0.533 |                      0.831 |    0.784 |     0.878 | False       |
| urban_centre      |       734420 |               5.257 |                0     |     130 | 396 |         330.9 |           1.858 |                        0.652 |                      0.919 |    0.89  |     0.949 | False       |

## The finding

**The two axes run in opposite directions.** Rural Latvia is slower to reach *and better stocked*; the cities are quick to reach *and least prepared*. Remoteness and unpreparedness do not compound — they partly cancel, which means one national message cannot serve both.

This inverts the assumption the project was pitched on.

## Method notes

- **The join runs on community type**, not geography. EB547's `d25` holds n>=262 in every category. The full NUTS3 route is **not** attempted: no verified municipality-to-NUTS3 crosswalk exists in the source data, and inventing one for 35 novadi would put a guess under the headline. Rīga (LV006) is unambiguous and is reported alone.
- **The classes are calibrated before comparison.** Measured density and self-reported community type split Latvia differently, so the density cutoffs are set to reproduce the survey's own population shares. Both sides then describe the same three groups of people.
- **RHI stays a bracket.** EB547 band 2 is literally *'2-3 days'*, so whether those households clear the 3-day target is unknowable from the answer. Collapsing to a midpoint would turn the upper bound into an estimate.
- **Intervals use Kish's effective sample size**, not the raw row count.

## Rīga vs the rest

| area           |   population |   mean_response_min |   survey_n |   n_effective |   mean_rhi_days | thin_cell   |
|:---------------|-------------:|--------------------:|-----------:|--------------:|----------------:|:------------|
| Rīga (LV006)   |       611301 |                5.93 |        286 |         255.1 |            1.89 | False       |
| rest of Latvia |      1272468 |                8.27 |        688 |         450   |            2.95 | False       |

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
