# Model card — PGI (Preparedness Gap Index) and its drivers

**What it measures.** The share of measures a respondent was aware of but had not taken. High PGI marks someone already convinced and not yet acting — the addressable segment.

**Type.** Deterministic index, plus a LightGBM regression to identify drivers.

**Inputs.** `qc5_1` (saw information in the last 12 months) crossed with `qc6.1`–`qc6.13` (measures taken).

## Leakage control

PGI is computed from the qc6 battery, so every feature derived from it — `act_*`, `n_actions`, `pri`, `theta_*` — is the target in disguise. `assert_no_leakage` **raises** rather than warns, and runs before every fit.

## Validation design

Grouped 5-fold cross-validation **by country**: rows from one country share sampling design and national context, so a random split would let the model memorise country effects and report an optimistic score.

## Against baselines

| model             |   n_features |   r2_oof |   mae_oof |
|:------------------|-------------:|---------:|----------:|
| mean predictor    |            0 |   0      |  0.135656 |
| demographics only |            5 |  -0.013  |  0.1371   |
| full model        |           23 |   0.1159 |  0.1264   |

**Demographics alone score below the mean predictor.** Who you are barely predicts preparedness — which is the case for a personalised tool rather than demographic targeting.

## Drivers (top 10 by |SHAP|)

| feature                   |   mean_abs_shap |   mean_shap |
|:--------------------------|----------------:|------------:|
| prep_feels_well_prepared  |          0.0266 |     -0.0001 |
| prep_no_time_or_money     |          0.0199 |      0.0006 |
| top_personal_risk         |          0.0131 |     -0      |
| age                       |          0.0123 |      0.0003 |
| n_disasters_experienced   |          0.01   |     -0.0002 |
| prep_employer_encourages  |          0.0094 |     -0.0001 |
| prep_knows_what_to_do     |          0.0092 |      0.0002 |
| prep_knows_alert_channel  |          0.0084 |     -0      |
| volunteers_for_responders |          0.0075 |      0.0001 |
| prep_prep_helps_cope      |          0.0072 |      0.0006 |


## Capability versus information

| barrier                       | feature               |   spread_agree_minus_disagree |
|:------------------------------|:----------------------|------------------------------:|
| capability  (no time / money) | prep_no_time_or_money |                        0.0915 |
| information (needs more info) | prep_needs_more_info  |                        0.0414 |

The survey's own headline is that two in three Europeans *say* they need more information. Modelled, the capability barrier ranks far above the information barrier. **The stated barrier and the operative barrier differ** — which argues for making action cheaper and easier over producing more guidance.

## Variance audit

Run before fitting; drops features with `n_unique < 2` or `std < 0.01`. Currently dropping **0**.


The threshold targets *constant* columns. An earlier `min_unique=5` discarded every 4-point Likert item — including both barriers the model exists to compare — and would have produced the conclusion that nothing predicts the gap. A regression test now pins this.

---

*Generated 2026-08-05 by `scripts/build_model_cards.py` · Python 3.11.7 · source `ZA8841_v1-0-0.sav` (26,405 × 668).*
