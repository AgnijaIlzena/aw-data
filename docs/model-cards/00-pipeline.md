# Model card — data pipeline and the sanity gate

**Source.** Eurobarometer 101.1, GESIS study `ZA8841` (Special Eurobarometer 547), DOI `10.4232/1.14461`. Fieldwork 7 Feb – 3 Mar 2024, 26,405 respondents, 27 Member States.

## The gate

Nothing downstream is trusted until the pipeline reproduces figures the European Commission published from this same survey. Enforced as a test, so a later change to the cleaner cannot quietly break agreement.

**Rows through the pipeline.** 26,405 in, 26,405 out — none dropped. Unusable answers become nulls; the decision to exclude belongs to each index.

## The three traps in this dataset

1. **Off-scale codes.** Every `qc` scale carries 5 (Not applicable / It depends) and 6 (Don't know). Left numeric, "Don't know" outranks "More than 7 days".
2. **`w22` is not the current EU27.** It is the pre-2013 definition and is null for all 1,001 Croatian respondents — any EU figure computed with it silently drops a Member State. `w92` is the correct EU weight; `w1` is per-country.
3. **The published denominator includes "Don't know".** DG ECHO's 37% is a share of *all* respondents; among substantive answers only it is 39.3%.

## Weights

- `w1` → `w_national` — national, for per-country figures
- `w92` → `w_eu` — EU-wide totals
- `w22` → `w_eu27_legacy` — **do not use**, excludes Croatia

Effective sample sizes use Kish's formula; a weighted sample supports narrower claims than its row count suggests.

---

*Generated 2026-08-05 by `scripts/build_model_cards.py` · Python 3.11.7 · source `ZA8841_v1-0-0.sav` (26,405 × 668).*
