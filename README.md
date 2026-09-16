# ActionWise Data Science

> **The knowing–doing gap.** Europeans know what to do to prepare for a crisis.
> Most still haven't done it. Who doesn't act, and what moves them?

Specs: `../ACTIONWISE/DATA_PROJECT_BRIEF.md` · `../ACTIONWISE/DATA_PROJECT_ONEPAGER.md`

A second project (time-to-help — minutes until rescue arrives, against the target
Latvian law sets) was built and then dropped: it modelled a single-incident,
business-as-usual response, which doesn't speak to the compound-crisis scenarios
(flood, conflict, infrastructure attack) ActionWise is actually about. Its code is
no longer in this repository; see git history (`project 2 implemented - geo block`)
if it needs revisiting.

---

## Status

| | | |
|---|---|---|
| 0 | Scaffold, config, DuckDB client | ✅ |
| 1 | Loader, cleaner, audit trail | ✅ |
| 2 | **Sanity gate — 7/7 published figures** | ✅ |
| 3 | Descriptive gap table | ✅ |
| 4 | RHI — Resilience Horizon Index | ✅ |
| 5 | PRI — 2PL IRT | ✅ |
| 6 | PGI drivers (LightGBM + SHAP) | ✅ |
| 7 | Latvia hold-out, percentiles | ✅ |
| 8 | Streamlit dashboard | ✅ |
| 9 | Tests, model cards, docs | ✅ |
| 11 | FEMA / ACI *(optional, data-pending)* | ⏸ |

**114 tests passing.**

## Headline findings

| | |
|---|---|
| Aware but hasn't acted | **47.0%** of all person × measure pairs |
| Conversion rate | only **23%** of awareness becomes action |
| Weakest lifeline | **water** binds 58% of households; food under 2% |
| Households below 72h | EU 64.5% certainly · Latvia **54.9%** (4th best in EU) |
| What predicts the gap | **capability** (rank 2 of 23) far above **information** (rank 13) |
| Latvia hold-out | θ correlation **0.9935** — pooling across Europe is justified |

## Data

**Eurobarometer 101.1, GESIS study `ZA8841`**, published as *Special Eurobarometer
547: Disaster risk awareness and preparedness of the EU population*. DOI
`10.4232/1.14461`. Fieldwork 7 Feb – 3 Mar 2024 · 26,405 respondents ·
27 Member States · **Latvia n = 1,008**.

Raw data is **not in this repo**. It lives in `../dati/` and is read-only —
`config.DATA_RAW` points there. This keeps large files out of git and makes
immutable-raw structural rather than a convention.

## Setup

Requires **Python 3.11** — not the system 3.14, whose wheel coverage for
`shap`/`numba` and `girth` is incomplete.

```bash
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell
pip install -r requirements-dev.txt
pip install -e .
```

Two dependency files, on purpose:

| File | Holds | Installed by |
|---|---|---|
| `requirements.txt` | dashboard runtime only — duckdb, pandas, plotly, streamlit | Streamlit Community Cloud |
| `requirements-dev.txt` | the above **plus** the modelling stack (scikit-learn, lightgbm, shap, statsmodels, girth, pyreadstat, jupyter) | you, locally |

## Reproduce from scratch

Each step depends on the tables the previous one writes.

```bash
python scripts/run_pipeline.py          # raw -> DuckDB, prints the audit trail  (~30s)
python scripts/run_sanity_gate.py       # THE GATE — stop here if it fails        (~5s)
python scripts/run_gap_table.py         # gap tables + PGI                       (~10s)
python scripts/run_rhi.py               # resilience horizon                     (~60s)
python scripts/run_irt.py               # item bank + PRI                        (~90s)
python scripts/run_gap_drivers.py       # LightGBM + SHAP                        (~60s)
python scripts/run_holdout.py           # Latvia hold-out + percentiles          (~90s)
python scripts/build_model_cards.py     # regenerate docs/model-cards/            (~2s)

pytest                                  # (~35s)
streamlit run dashboard/app.py          # 8 pages
```

The pipeline prints an **audit trail** — every step's rows in, rows out, cells
nulled, and why. Nothing is dropped silently.

The gate exits non-zero on failure, so it can be wired into CI.

## Deployment

The dashboard is deployed on Streamlit Community Cloud from `main`, main module
`dashboard/app.py`. It runs against `data/db/actionwise-public.duckdb` — the
same schema as the full base, without the microdata — which is the one data file
this repo versions; `dashboard/_db.py` falls back to it when the full base built
by the pipeline is absent, which is always the case on the host.

**The host installs `requirements.txt`, not `requirements-dev.txt`, and that is
the point.** Community Cloud fixes the Python version at deploy time and it
cannot be changed afterwards — changing it means deleting the app and
redeploying. This app landed on **Python 3.14**, and one line in the old
single-file setup was fatal there:

```
numpy>=1.26,<2.1
```

numpy publishes no cp314 wheel below **2.3.2**, so that upper bound — which
exists for a local Windows reason, not an API one, see
[docs/WINDOWS-SMART-APP-CONTROL.md](docs/WINDOWS-SMART-APP-CONTROL.md) — could
not be satisfied by any wheel. uv fell back to compiling numpy 2.0.2 from
source, ground on for 49 minutes, failed, and left the environment empty. The
app then started against the bare base image and died on its first
non-preinstalled import, `import duckdb`, with `ModuleNotFoundError` — which
points at duckdb only because duckdb is imported first, not because duckdb was
ever the problem.

It was the one real blocker: every other pin in the stack, `lightgbm` and
`shap` and `girth` included, does resolve to a wheel on 3.14.

numpy is a *pipeline* dependency; the dashboard never imports it. Confining it —
and the rest of the modelling stack — to `requirements-dev.txt` keeps the cap
where it is useful and out of the deploy. The runtime file resolves to **40
packages, all wheels**, against 145 before, and installs in seconds. `pandas`
keeps its `<3.0` bound in both files: unlike numpy, pandas ships cp314 wheels
from 2.3.3, so the deployed dashboard runs the same pandas the pipeline is
tested on.

Verify before pushing a dependency change — this resolves the runtime exactly as
the host would, and fails loudly if anything would need a source build:

```bash
pip install --dry-run --ignore-installed --only-binary=:all:     --python-version 3.14 --target /tmp/probe -r requirements.txt
```

## Model cards

`docs/model-cards/` is **generated from DuckDB**, never hand-written — rerun
`build_model_cards.py` and the numbers update themselves. This is a direct
response to `virality-code`, whose README documented a Random Forest while the
code ran Gradient Boosting, because the docs were written once and the code
moved on.

`00`–`03`: pipeline, RHI, PRI, PGI.

## Tests

| File | Covers |
|---|---|
| `test_smoke.py` | environment, source file shape, every config-named variable exists |
| `test_cleaner.py` | the three traps, both denominators, the audit trail |
| `test_sanity_gate.py` | agreement with the published figures, permanently |
| `test_indices.py` · `test_rhi.py` · `test_irt.py` · `test_percentiles.py` | index maths on data with known answers |
| `test_gbm.py` | **the leakage guard**, variance audit, planted-signal recovery |
| `test_dashboard_isolation.py` | the dashboard cannot import index code or read files |
| `test_dashboard_renders.py` | every page renders; the sliders actually re-rank |

## The gate

`scripts/run_sanity_gate.py` reproduces figures the European Commission published from
this same survey. Current state — all seven within ±0.6pp:

| Check | Published | Computed |
|---|---|---|
| Feel well prepared (EU) | 37.0% | 37.3% |
| Need more information (EU) | 65.0% | 64.7% |
| Medication >7 days | 34.0% | 33.9% |
| Food >7 days | 29.0% | 28.9% |
| Cooking/heating >7 days | 20.0% | 20.5% |
| Feel prepared — Slovenia | 65.0% | 64.4% |
| Feel prepared — Malta | 25.0% | 25.3% |

Nothing downstream is trusted until this passes. It exists because the predecessor
project (`../virality-code`) shipped a model that scored *below* its own baseline and
nobody noticed — there was no external number to check against.

## Three traps in this dataset

Documented here because each would produce plausible-looking wrong answers.

1. **Off-scale codes.** Every `qc` scale carries `5` (Not applicable / It depends) and
   `6` (Don't know). Left as numerics, "Don't know" outranks "More than 7 days".
2. **`w22` is not the current EU27.** It is the *pre-2013* definition and is null for all
   1,001 Croatian respondents — any EU figure computed with it silently drops a Member
   State. Use **`w92`** (→ `w_eu`) for EU totals and **`w1`** (→ `w_national`) per country.
3. **The published denominator includes "Don't know".** DG ECHO's 37% is a share of *all*
   respondents. Among substantive answers only it is 39.3%. Columns ending `_agree_topline`
   follow the published convention; `_agree` excludes DK.

## Layout

```
src/actionwise/
  config.py                       paths, survey constants — single source
  weighting.py                    weighted means/quantiles, Kish effective n
  sanity.py                       the Phase 2 gate
  data/ · db/ · indices/ · models/

scripts/    run_pipeline · run_sanity_gate · run_gap_table · run_rhi · run_irt
            run_gap_drivers · run_holdout · build_model_cards
dashboard/  app.py  _db.py       8 pages, DuckDB-only
docs/model-cards/                generated, not hand-written
tests/
```

## Known limitations

Stated here rather than discovered at a viva.

- **Self-reported throughout.** Nobody checked a cupboard. These are *perceived* horizons
  and *claimed* measures.
- **One snapshot** (Feb–Mar 2024). No trend, no causal design — lift is association.
- **Latvia is 1,008 respondents.** Fine nationally, thin by age band; cells under 100 are
  flagged `thin_cell` and the tables always carry an `all` row to fall back on.
- **The action battery has no time window** — a lifetime stock, not a 12-month flow, so it
  is not comparable to FEMA's equivalent without adjustment.
- **The battery is not unidimensional.** Discrimination splits into supplies (sharp) and
  engagement (flat); PRI is dominated by the former. See `docs/model-cards/02-pri.md`.
- **The composite weights on the dashboard are a judgement, not an estimate** — the only
  number here that is not derived from data, which is exactly why they are sliders.
