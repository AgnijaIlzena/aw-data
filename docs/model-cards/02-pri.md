# Model card — PRI (Personal Readiness Index)

**What it measures.** A latent preparedness trait behind the thirteen household measures, rescaled to 0–100 via the normal CDF so it reads directly as "more prepared than N% of the calibration population".

**Type.** 2-parameter logistic item response theory (`girth.twopl_mml`, marginal maximum likelihood). **This is a measurement model, not a predictive one** — there is no accuracy figure because it forecasts nothing.

**Inputs.** `qc6.1`–`qc6.13`, binary. Complete cases only; a "don't know" battery carries no information about the trait and imputing zeros would read as maximally unprepared.

**Calibration sample.** 23,912 complete response patterns.

## Item bank

| label                                |   difficulty |   discrimination |   p_observed |
|:-------------------------------------|-------------:|-----------------:|-------------:|
| Flashlight or candles                |       -0.355 |            1.482 |        0.593 |
| First-aid kit                        |        0.227 |            1.524 |        0.44  |
| Emergency food & drink stock         |        0.648 |            1.496 |        0.334 |
| Battery-powered radio                |        0.943 |            1.359 |        0.277 |
| Emergency water (cooking, hygiene)   |        1.055 |            1.531 |        0.241 |
| Key documents copied / stored safely |        1.863 |            0.891 |        0.192 |
| Agreed family contact method         |        3     |            0.499 |        0.194 |
| Invested in home protection          |        3.92  |            0.642 |        0.087 |
| Took part in training or a drill     |        4.002 |            0.604 |        0.093 |
| Grab-bag ready for evacuation        |        4.038 |            0.661 |        0.077 |
| Signed up for official alerts        |        4.804 |            0.446 |        0.112 |
| Discussed protection with neighbours |        5.285 |            0.486 |        0.078 |
| Knows the local emergency plan       |        5.91  |            0.405 |        0.089 |


## Item fit

| label                                |   infit |   outfit | misfitting   |
|:-------------------------------------|--------:|---------:|:-------------|
| Flashlight or candles                |   0.755 |    0.683 | False        |
| First-aid kit                        |   0.781 |    0.687 | False        |
| Emergency water (cooking, hygiene)   |   0.86  |    0.705 | False        |
| Emergency food & drink stock         |   0.822 |    0.713 | False        |
| Battery-powered radio                |   0.878 |    0.734 | False        |
| Key documents copied / stored safely |   0.958 |    0.892 | False        |
| Took part in training or a drill     |   1.004 |    0.962 | False        |
| Invested in home protection          |   1.005 |    0.965 | False        |
| Grab-bag ready for evacuation        |   1.008 |    0.969 | False        |
| Agreed family contact method         |   0.982 |    0.976 | False        |
| Signed up for official alerts        |   1     |    0.979 | False        |
| Discussed protection with neighbours |   1.006 |    0.987 | False        |
| Knows the local emergency plan       |   1.002 |    0.992 | False        |

Productive range 0.5–1.5. **0 of 13 items** fall outside it.

## Face validity

| check                                                            |   b_harder |   b_easier | pass   |
|:-----------------------------------------------------------------|-----------:|-----------:|:-------|
| grab_bag harder than flashlight_candles                          |      4.038 |     -0.355 | True   |
| training_exercise harder than first_aid_kit                      |      4.002 |      0.227 | True   |
| neighbourhood_discussion harder than emergency_food_drink        |      5.285 |      0.648 | True   |
| difficulty ranks inversely with observed frequency (rho < -0.80) |     -0.896 |    nan     | True   |

The frequency-correlation bar is −0.80 rather than −0.90 because 2PL discrimination varies: a flat item can be extreme in difficulty yet middling in frequency. A stricter bar would assert a Rasch property this model does not claim.

## Known limitation — the battery is not unidimensional

| group                       |   n_items |   mean_a |   mean_b | items                                                                                                                                              |
|:----------------------------|----------:|---------:|---------:|:---------------------------------------------------------------------------------------------------------------------------------------------------|
| high discrimination (sharp) |         5 |    1.478 |    0.504 | flashlight_candles, first_aid_kit, emergency_food_drink, battery_radio, emergency_water                                                            |
| low discrimination (flat)   |         8 |    0.579 |    4.103 | documents_safe, family_contact_plan, home_protection, training_exercise, grab_bag, signed_up_alerts, neighbourhood_discussion, knows_official_plan |

Discrimination splits into a sharp group (supplies you buy and store) and a flat group (things you do and arrange). 2PL assumes one trait, so **PRI is dominated by the sharp group**. A two-dimensional model is the principled next step; it is reported here rather than silently applied.

## Transfer validation (Latvia held out)

- calibrated on 23,008 respondents, **excluding Latvia**, then used to score it
- θ correlation against a Latvia-only bank: **0.9935**
- mean |PRI difference|: **2.28 points**

Pooling across Europe is therefore justified — which matters because 1,008 Latvian respondents cannot calibrate 13 items alone.

---

*Generated 2026-08-05 by `scripts/build_model_cards.py` · Python 3.11.7 · source `ZA8841_v1-0-0.sav` (26,405 × 668).*
