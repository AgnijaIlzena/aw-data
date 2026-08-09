# ActionWise Data Science

Two projects in one repository, joined at the end.

> **#1 — the knowing–doing gap.** Europeans know what to do to prepare for a crisis.
> Most still haven't done it. Who doesn't act, and what moves them?
>
> **#2 — time-to-help.** How long you are on your own before rescue arrives, and
> whether that meets the target Latvian law actually sets.

Project #1 measures how many **days** a household can last; project #2 measures how
many **minutes** until help arrives. Neither says much alone.

Specs: `../ACTIONWISE/DATA_PROJECT_BRIEF.md` · `../ACTIONWISE/DATA_PROJECT_ONEPAGER.md`
· `../ACTIONWISE/DATA_PROJECT_2_ONEPAGER.md`

---

## Status

| | Project #1 — survey indices | | Project #2 — time-to-help | |
|---|---|---|---|---|
| 0 | Scaffold, config, DuckDB client | ✅ | Scaffold + routing install gate | ✅ |
| 1 | Loader, cleaner, audit trail | ✅ | Reference geography readers | ✅ |
| 2 | **Sanity gate — 7/7 published figures** | ✅ | **Geography gate — 12/12 checks** | ✅ |
| 3 | Descriptive gap table | ✅ | Road network + TTH | ✅ |
| 4 | RHI — Resilience Horizon Index | ✅ | CCI — legal compliance | ✅ |
| 5 | PRI — 2PL IRT | ✅ | Traffic adjustment | ✅ |
| 6 | PGI drivers (LightGBM + SHAP) | ✅ | External validation | ✅ |
| 7 | Latvia hold-out, percentiles | ✅ | Join to project #1 | ✅ |
| 8 | Streamlit dashboard | ✅ | Dashboard pages | ✅ |
| 9 | Tests, model cards, docs | ✅ | Tests, model cards, docs | ✅ |
| 11 | FEMA / ACI *(optional, data-pending)* | ⏸ | | |

**298 tests passing** (plus 10 marked `slow`, which parse the 133 MB OSM extract).

## Headline findings

**Project #1 — preparedness**

| | |
|---|---|
| Aware but hasn't acted | **47.0%** of all person × measure pairs |
| Conversion rate | only **23%** of awareness becomes action |
| Weakest lifeline | **water** binds 58% of households; food under 2% |
| Households below 72h | EU 64.5% certainly · Latvia **54.9%** (4th best in EU) |
| What predicts the gap | **capability** (rank 2 of 23) far above **information** (rank 13) |
| Latvia hold-out | θ correlation **0.9935** — pooling across Europe is justified |

**Project #2 — response**

| | |
|---|---|
| Coverage Compliance Index | **92.3%** reach help within the target that applies where they live |
| Mean response | **7.5 min**, against VUGD's published **9.2 min** — the validation that passes |
| Worst municipality | **Ventspils nov. 79.8%**; then **Rīga 83.3%**, because 99% of it is held to 8 minutes |
| Over-65s | 91.7% — but on 35% of cells, so an **upper bound** |
| Traffic | **no effect** (+0.01 min): the median secondary road carries 11 vehicles in the peak hour |
| NMPD rank check | **null** (ρ = −0.18, CI −0.49…+0.16) — compliance is not geographic at this scale |

**The join**

The two axes run in **opposite** directions. Rural Latvia is slower to reach
(11.9 min) *and better stocked* (42–68% under three days); the cities are quick
(5.3 min) *and least prepared* (65–92%). Remoteness and unpreparedness do not
compound here — they partly cancel, so one national message cannot serve both.

## Data

**Project #1 — Eurobarometer 101.1, GESIS study `ZA8841`**, published as *Special
Eurobarometer 547: Disaster risk awareness and preparedness of the EU population*.
DOI `10.4232/1.14461`. Fieldwork 7 Feb – 3 Mar 2024 · 26,405 respondents ·
27 Member States · **Latvia n = 1,008**.

**Project #2 — seven open datasets, all CC0**

| | Source | Verified state |
|---|---|---|
| VUGD depots | data.gov.lv | **87**, already EPSG:3059 |
| Road network | OpenStreetMap, Geofabrik | 1.35 M nodes / 1.38 M edges, **dated snapshot** |
| Population grid | Eurostat Census 2021 V3 | 64,636 LV cells, 1,888,613 people |
| Traffic intensity | LVC, 2 workbooks × 3 sheets | 1,335 roads, 2012–2023 |
| Kilometre markers | LVC | 20,789 usable — the bridge from traffic to map |
| Boundaries | VARAM/VZD | 42 territories (Varakļānu nov. absent) |
| NMPD response | NMPD, 2022–2025 | 37 rows/yr; 7 cities in one aggregate |

Raw data is **not in this repo**. It lives in `../dati/` and is read-only —
`config.DATA_RAW` points there. This keeps large files out of git and makes
immutable-raw structural rather than a convention.

The OSM extract is **pinned to a dated file**, never `latvia-latest.osm.pbf`: that
URL points at a different file every day, and results built on it cannot be
reproduced or explained.

## Setup

Requires **Python 3.11** — not the system 3.14, whose wheel coverage for
`shap`/`numba` and `girth` is incomplete.

```bash
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1        # PowerShell
pip install -r requirements.txt
pip install -e .
```

**Project #2 additionally needs the `[geo]` extra**, kept optional on purpose so a
broken geospatial wheel can never stop project #1:

```bash
pip install -e ".[geo]"
```

On Windows this fails the first time — `cykhash` (a pyrosm dependency) ships no
wheels for any platform and pip's build isolation cannot see MSVC even when it is
installed. Run pip from inside an initialised MSVC environment once and the wheel
is cached thereafter:

```powershell
$vc = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat"
cmd /c "`"$vc`" x64 >nul && .\.venv\Scripts\python.exe -m pip install -e `".[geo]`""
```

No compiler at all? `pip install -e ".[geo-osmium]"` is the fallback — see
`docs/PHASE0-ROUTING.md`.

## Reproduce from scratch

Each step depends on the tables the previous one writes.

```bash
# ── project #1 — survey indices ────────────────────────────────────────────
python scripts/run_pipeline.py          # raw -> DuckDB, prints the audit trail  (~30s)
python scripts/run_sanity_gate.py       # THE GATE — stop here if it fails        (~5s)
python scripts/run_gap_table.py         # gap tables + PGI                       (~10s)
python scripts/run_rhi.py               # resilience horizon                     (~60s)
python scripts/run_irt.py               # item bank + PRI                        (~90s)
python scripts/run_gap_drivers.py       # LightGBM + SHAP                        (~60s)
python scripts/run_holdout.py           # Latvia hold-out + percentiles          (~90s)
python scripts/build_model_cards.py     # regenerate docs/model-cards/            (~2s)

# ── project #2 — time-to-help ──────────────────────────────────────────────
python scripts/run_geo_sanity_gate.py   # THE GEOGRAPHY GATE — stop if it fails  (~30s)
python scripts/run_geo_tth.py           # travel times, both speed factors       (~65s)
python scripts/run_geo_coverage.py      # settlements + legal compliance         (~90s)
python scripts/run_geo_traffic.py       # traffic adjustment                    (~100s)
python scripts/run_geo_validate.py      # external validation                    (~70s)
python scripts/run_geo_matrix.py        # the join to project #1                 (~70s)
python scripts/build_geo_model_cards.py # regenerate cards 10–15                  (~2s)

pytest                                  # 298 tests (~35s)
pytest -m slow                          # 10 more, parsing the real OSM extract (~3min)
streamlit run dashboard/app.py          # 13 pages
```

Both pipelines print an **audit trail** — every step's rows in, rows out, cells
nulled, and why. Nothing is dropped silently.

Both gates exit non-zero on failure, so either can be wired into CI.

## Model cards

`docs/model-cards/` is **generated from DuckDB**, never hand-written — rerun
`build_model_cards.py` / `build_geo_model_cards.py` and the numbers update
themselves. This is a direct response to `virality-code`, whose README documented a
Random Forest while the code ran Gradient Boosting, because the docs were written
once and the code moved on.

| | |
|---|---|
| `00`–`03` | project #1: pipeline, RHI, PRI, PGI |
| `10`–`15` | project #2: geography, TTH, CCI, traffic, validation, the matrix |

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
| `test_geo_isolation.py` | project #1 never imports project #2; `[geo]` stays optional |
| `test_geo_config.py` | recorded data facts still match the files on disk |
| `test_geo_crs.py` | **the degree/metre guard** — a mislabelled CRS must raise |
| `test_geo_data.py` | the `-9999` sentinel, the unallocated row, the name collision |
| `test_geo_sanity.py` | the geography gate **fails** when geography is broken |
| `test_geo_network.py` | parallel-edge minimum, absent `oneway`, snap flagging |
| `test_geo_tth.py` | routing arithmetic; detour is speed-free, time ratio is not |
| `test_geo_coverage.py` | a settlement may not cross a municipality boundary |
| `test_geo_traffic.py` | the forward-fill, six header spellings, BPR damping |
| `test_geo_validate.py` | the null is bounded — and a planted signal *is* detected |
| `test_geo_matrix.py` | the axes are never combined; RHI stays a bracket |

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

## Five traps in the geospatial data

Each measured, not suspected, and each silent if missed.

1. **A mislabelled CRS.** The VUGD *property register* declares LKS-92 and holds
   WGS84 degrees. A degree/metre mix never raises — it yields a map that looks
   fine with distances wrong by ~100,000×. Every frame is checked against
   Latvia's real extent, not against its declared CRS.
2. **`-9999` is a confidentiality sentinel**, not a population. Summed naively
   `Y_GE65` totals **−211,308,180**. It must become null, *never zero*:
   suppression concentrates in sparse cells, so zeroing understates the elderly
   exactly where response times are longest.
3. **`Ceļa Nr.` is null on 96 of 111 traffic rows.** A null means "same road as
   above". Without a forward-fill every continuation segment loses its road and
   drops out of the join without an error.
4. **`edges.length` is not `edges["length"]`.** The GeoSeries property returns
   geometry length in *degrees* and only warns; the column is metres. The two
   differ by a factor of 100,000 and share a name.
5. **A settlement that crosses a municipality inherits its neighbour's depots.**
   Pure contiguity fuses Salaspils into Rīga and hands it an 8-minute standard it
   has no station for — 95.6% of its people on the strict target instead of 0.0%.

## Layout

```
src/actionwise/                 project #1 — survey indices
  config.py                       paths, survey constants — single source
  weighting.py                    weighted means/quantiles, Kish effective n
  sanity.py                       the Phase 2 gate
  data/ · db/ · indices/ · models/

src/actionwise_geo/             project #2 — time-to-help (sibling, not subpackage)
  config.py                       CRS, legal thresholds, speed defaults
  crs.py                          the degree/metre guard every reader passes through
  data/     depots · boundaries · popgrid · traffic · kmmarkers
  network/  graph · speeds · snap · congestion
  indices/  tth · settlements · coverage · matrix
  validate/ sanity · nmpd

scripts/    run_pipeline · run_sanity_gate · run_gap_table · run_rhi · run_irt
            run_gap_drivers · run_holdout · build_model_cards
            run_geo_sanity_gate · run_geo_tth · run_geo_coverage
            run_geo_traffic · run_geo_validate · run_geo_matrix
            build_geo_model_cards
dashboard/  app.py  _db.py  geo_pages.py     13 pages, DuckDB-only
docs/model-cards/                             generated, not hand-written
tests/                                        298 tests + 10 slow
```

The two projects communicate through **the DuckDB file, not through imports**.
Project #1 never imports project #2 — enforced by `test_geo_isolation.py` — so the
finished half stays independently runnable if the geospatial stack ever breaks.

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

**Project #2**

- **Travel time, not total response time.** The minutes before a call is placed,
  and the dispatch decision, are not modelled. This is why the model sits below
  VUGD's published average rather than matching it.
- **Speeds are mostly inferred.** `maxspeed` is tagged on 18.5% of drivable edges;
  class defaults carry the rest, and coverage is worst on exactly the rural roads
  the 23-minute standard governs. Every figure is reported at 1.0× and 1.2×.
- **The over-65 figure is an upper bound.** It covers 35% of cells, and the
  suppressed ones are the sparse, remote, slowest-served ones.
- **Ambulances are a different service.** The NMPD comparison is a rank check on
  geography, never a calibration — and it returns null.
- **Congestion is modelled at link level only.** Junction and signal delay, which
  is what actually slows a vehicle in Rīga, is not captured by AADT or BPR.
- **Availability is not modelled.** The map says where a crew *can* reach, not
  whether one was free.
- **Full NUTS3 is not attempted.** No verified municipality-to-NUTS3 crosswalk
  exists in `../dati/`; only the Rīga contrast is reported.
- **Snapshots.** OSM at a pinned date; census as at 1 January 2021.
