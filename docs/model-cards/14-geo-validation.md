# Model card — external validation

Two independent checks. One passes; the other is a documented null, reported as such rather than re-specified until a correlation appeared.

## 1. Against VUGD's published national average — passes

|   published_mean_arrival_min |   model_mean_response_min |   delta_min | direction_expected    | pass   | note                                                                                                                                     |
|-----------------------------:|--------------------------:|------------:|:----------------------|:-------|:-----------------------------------------------------------------------------------------------------------------------------------------|
|                          9.2 |                       7.5 |        -1.7 | model below published | True   | the published figure includes dispatch and real-world routing; the model includes neither, so a gap of 1-3 minutes is the expected shape |

The published figure (9.2 min) includes dispatch and real-world routing; the model includes neither, so it should sit 1–3 minutes below. Landing *above* would mean the speed model is wrong; landing far below would mean the network is.

## 2. Against NMPD per-municipality compliance — null

| predictor              |    rho |     p |   ci_low |   ci_high |   n | significant   |
|:-----------------------|-------:|------:|---------:|----------:|----:|:--------------|
| mean_response_min      | -0.182 | 0.294 |   -0.486 |     0.161 |  35 | False         |
| euclidean_baseline_min | -0.101 | 0.565 |   -0.42  |     0.241 |  35 | False         |
| mean_density           |  0.093 | 0.594 |   -0.248 |     0.414 |  35 | False         |
| depots_per_100k        | -0.008 | 0.966 |   -0.34  |     0.327 |  35 | False         |

No predictor reaches significance, **the Euclidean baseline included**.

**Why, and why it is not a failure of the model.** At the 25-minute rural target the model places 93–100% of every municipality within reach while observed compliance runs 70–93%. That gap is operational — crew availability, dispatch, hospital handover, and an ambulance network sited independently of the fire one — not spatial.

The model's own positive controls pass: response time correlates with density (rho = -0.32), with depots per head (rho = -0.43), and with the Euclidean baseline (rho = +0.82). The failure belongs to the comparison.

## What the comparison cannot see

- the 7 valstspilsētas are **one aggregate row** (`Valstspilsēta`) carrying **54%** of all priority 1–2 calls, and cannot be mapped
- NMPD ambulance station locations are **not published**
- compliance is weighted by **calls**, the model by **residents**
- 2025 is a partial year and is excluded

NMPD's own targets (MK Nr. 555, 2018) are 12/15/25 minutes — a different regulation from the fire service's 8/23, and not to be mixed.

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
