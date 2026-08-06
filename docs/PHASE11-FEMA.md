# Phase 11 (optional) — FEMA National Household Survey

**Status: built and tested, awaiting data.** The code is complete and passes 15 tests on
synthetic fixtures; the data files have to be fetched by hand because FEMA blocks scripted
access.

Phase 11 is **entirely optional** and designed to be removed in one step. Nothing in
Phases 0–9 depends on it.

---

## Why it exists

One thing, and it is the only thing Europe cannot give you.

EB547 asks awareness **once** — `qc5_1`, *"have you seen any preparedness information in the
last 12 months"* — against thirteen actions. So when Phase 3 reports that the grab-bag
converts at 9.3%, it means *"of people who saw preparedness information in general"*, which
lumps together someone who saw a water-storage poster and someone who saw a neighbour-
coordination campaign.

FEMA asks `A3` (heard about item *i*) and `PREPB` (did item *i*) over **the same twelve
items**, so conversion is computable per message:

```
ACI_i = P(did item i | was aware of item i)
```

Two further things come free with it:

- **`ST_STG1`, a validated five-level intention→action ladder** — the empirical grounding for
  the avatar's progression, which currently runs on invented rules. EB547 has no equivalent.
- **A replication test.** Phase 6's headline — capability (rank 2) beats information
  (rank 13) — currently rests on one survey, one wave, one continent. FEMA carries the same
  constructs across ~55,000 respondents and 11 waves.

## What it will not do

- **It does not add prediction.** FEMA NHS is a *repeated cross-section*: ~5,000 different
  people each year, not a panel. There is nobody to follow from aware to acted, so no
  individual transition model is possible. Trends are aggregate trends.
- **It does not make the data Latvian.** Every finding needs a transfer caveat.
- **It cannot be pooled with EB547.** See the recall-window note below.

---

## Getting the data

FEMA, DataLumos and openICPSR all return **403 to scripted requests** — bot protection, not
authentication. There is no API: the NHS is absent from the OpenFEMA dataset registry
entirely (verified by querying it). So:

1. Open <https://www.fema.gov/about/openfema/data-sets/national-household-survey> in a browser
2. Download the yearly packages — **start with 2022 and 2023**
3. Put the ZIPs in **`../dati/fema_nhs/`** with the year in the filename, e.g.
   `fema_nhs_2023.zip`
4. Run `python scripts/run_fema_aci.py`

No registration or API key is required. Each ZIP contains the raw data, the survey
instrument, a codebook and a weighting overview.

Citable mirror: DataLumos/ICPSR, DOI `10.3886/E218642V1`.

## Verify the column mapping before believing anything

FEMA ships *"unedited raw data"* and header names vary by year. The item names in
`fema/config.py` come from reading the **2022 instrument** (39 pages) — the released **data
file headers have not been verified**.

So the loader *discovers* columns rather than assuming them, and `run_fema_aci.py` prints
what it matched before computing anything:

```
COLUMN DISCOVERY — the paired A3/PREPB structure this phase depends on
item          awareness_col   action_col    paired
alerts        A3_alerts       PREPB_alerts  True
...
  11 of 12 items have BOTH an awareness and an action column
```

If few or no items pair, open the codebook inside the ZIP and set the mapping explicitly.
**Do not proceed on a guess** — the failure mode is not a crash but an ACI table full of
nulls that still looks like a result.

## The recall-window mismatch

Load-bearing, and recorded per row in `crosswalk.csv`:

| | Question | Quantity |
|---|---|---|
| FEMA `PREPB` | *"what have you done **in the last year**"* | 12-month **flow** |
| EB547 `qc6` | *"which have you **already adopted**"* | lifetime **stock** |

**Compare directions, never levels.** Any code that averages the two is combining different
quantities. `compare_with_eb547` carries the warning in the returned frame's `attrs`.

## The crosswalk

`src/actionwise/fema/crosswalk.csv` — 6 exact matches, 6 partial, and the honest gaps:

- **EB547 splits supplies into five items** (food, water, flashlight, radio, first-aid kit);
  FEMA has one. Comparable only in aggregate.
- **The grab-bag has no US equivalent.** ActionWise's Sac 72h is a Europe-only item, so its
  conversion rate cannot be replicated here.
- Four FEMA items have no EB547 counterpart: make a plan, save for a rainy day, get involved
  in the community, insure property.

---

## Removing Phase 11 entirely

Everything lives in one package plus three files. To drop it:

```bash
rm -r src/actionwise/fema/       # config, loader, aci, crosswalk
rm scripts/run_fema_aci.py
rm tests/test_fema.py
rm docs/PHASE11-FEMA.md
```

Then remove `page_fema` and the three-line conditional block in `dashboard/app.py` that
registers it, and drop the tables:

```sql
DROP TABLE IF EXISTS fema_aci;
DROP TABLE IF EXISTS fema_aci_by_year;
DROP TABLE IF EXISTS fema_column_discovery;
DROP TABLE IF EXISTS fema_stage_of_change;
DROP TABLE IF EXISTS fema_eu_comparison;
```

`pytest` should still show every other test passing. Nothing in Phases 0–9 imports from
`actionwise.fema`, and the dashboard page is registered conditionally — if the tables are
gone the page never appears, so removal cannot half-break the UI.
