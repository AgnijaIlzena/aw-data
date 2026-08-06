# Model card — RHI (Resilience Horizon Index)

**What it measures.** Days a household could cope, taken as the *minimum* across five lifelines: water, power, gas/heating, food, medication. The minimum is the point — a household with a month of food and one day of water has a one-day horizon.

**Type.** Deterministic index (no fitting) plus an ordered probit for drivers.

**Inputs.** `qc7_1`–`qc7_5`, banded: 1 = ≤1 day · 2 = 2–3 days · 3 = 4–7 days · 4 = >7 days. Midpoints used for averages: {1: 1.0, 2: 2.5, 3: 5.5, 4: 10.0}.

**Target.** 3 days.

## Design decisions

- **Reported as a bracket, not a point.** Band 2 ("2–3 days") straddles the 72-hour target, so the share below target is given as a range. Imputing a midpoint would manufacture precision the instrument never had.
- **"Not applicable" is excluded from the minimum, not counted as failure.** For medication it means the respondent takes none.
- **A partial minimum is an upper bound** and is flagged `rhi_partial`: an unanswered lifeline could have been the weakest.

## Distribution (EU, weighted)

|   band | label            |     share |
|-------:|:-----------------|----------:|
|      1 | 1 day or less    | 0.644562  |
|      2 | 2-3 days         | 0.239106  |
|      3 | 4-7 days         | 0.0734121 |
|      4 | More than 7 days | 0.0429196 |


## Which lifeline binds first

| domain      |   share_binding |   median_band |   pct_one_day_or_less |
|:------------|----------------:|--------------:|----------------------:|
| water       |       0.579569  |             2 |              0.318061 |
| power       |       0.326777  |             1 |              0.521427 |
| gas_heating |       0.0563363 |             2 |              0.375949 |
| medication  |       0.0199335 |             4 |              0.165897 |
| food        |       0.0173847 |             3 |              0.113444 |


## Ordered probit — accuracy beside its baseline

| domain      |     n |   accuracy |   baseline |   lift |   pseudo_r2 | beats_baseline   |
|:------------|------:|-----------:|-----------:|-------:|------------:|:-----------------|
| water       | 25183 |     0.3535 |     0.3522 | 0.0013 |      0.0146 | True             |
| power       | 24361 |     0.5371 |     0.5371 | 0      |      0.0029 | False            |
| gas_heating | 20504 |     0.3944 |     0.3414 | 0.053  |      0.0159 | True             |
| food        | 25042 |     0.3698 |     0.3415 | 0.0283 |      0.015  | True             |
| medication  | 20370 |     0.5008 |     0.5008 | 0      |      0.0204 | False            |

**Two of five domains do not beat their baseline.** Demographics barely predict resilience; that is the finding, not a failure to hide.

---

*Generated 2026-08-05 by `scripts/build_model_cards.py` · Python 3.11.7 · source `ZA8841_v1-0-0.sav` (26,405 × 668).*
