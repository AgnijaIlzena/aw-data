# Phase 1 — reference geography: implementation handoff

**Status: specified and tested, awaiting implementation.**
Four modules, ten functions, 27 tests. Every test currently fails on
`NotImplementedError` and nothing else — so the moment a body is correct, its test
goes green.

```bash
# the loop
.venv/Scripts/python.exe -m pytest tests/test_geo_crs.py tests/test_geo_data.py -q
```

Suggested order — each one unblocks the next:

| # | Module | Functions | Tests |
|---|---|---|---|
| 1 | `crs.py` | `to_working_crs`, `assert_plausibly_lv`, `points_from_xy` | 10 |
| 2 | `data/depots.py` | `load_depots`, `load_depots_crosscheck`, `compare_depot_sources` | 5 |
| 3 | `data/boundaries.py` | `load_boundaries`, `load_crosswalk`, `assign_municipality` | 5 |
| 4 | `data/popgrid.py` | `decode_grd_id`, `load_population_grid`, `population_coverage` | 7 |

`crs.py` first: the other three call it, and it is the guard the whole project
rests on.

---

## The five things that will bite

Each is measured, not suspected, and each fails **silently** rather than raising.

### 1. `-9999` is a confidentiality sentinel, not a population

On the three age bands only — never on `T`. Summed naively, `Y_GE65` totals
**−211,308,180**.

Replace with **null, never 0**. Zero is quietly wrong in the worst possible
direction: suppression concentrates in sparse cells, so zeroing understates the
elderly in exactly the remote places the 23-minute analysis is about.

> 19,139 of 29,587 populated cells (65%) are suppressed — but they hold only
> 92,106 people (4.9%). Both numbers go in the model card. The first sounds
> disqualifying; the second shows it isn't; the bias direction still needs saying.

### 2. `GRD_ID` names the corner, not the centre

```
CRS3035RES1000mN3731000E5018000  ->  north = 3_731_000,  east = 5_018_000
```

That's the **lower-left corner**. Centroid = corner + 500 m. Skipping the offset
shifts every cell 500 m south-west — invisible on a national map, and easily
enough to move a cell across an 8-minute isochrone boundary.

### 3. `LAND_SURFACE` is a fraction (0.0–1.0), not an area

`density = T / (LAND_SURFACE × 1 km²)`. Using the raw cell area understates
density on every coastal, riverside and lakeside cell — which in Latvia is most
of the larger towns, and density is what selects the legal threshold in Phase 4.

### 4. `POPULATED` disagrees with `T > 0`

2,031 cells are flagged populated with `T == 0`. The reverse never happens.
**Filter on `T`.**

### 5. The age bands don't reconcile per cell

`Y_LT15 + Y_1564 + Y_GE65 == T` holds on only **11%** of usable cells, while
agreeing to within 78 people nationally. That's disclosure perturbation working as
designed. `POPGRID_BANDS_RECONCILE_TO_TOTAL = False` records it so nobody later
"fixes" a reconciliation that was never meant to hold.

---

## Two rules the tests enforce

**Nothing is dropped.** Not an unmatched depot, not a null coordinate, not a grid
cell outside every polygon. Unusable rows keep null values and get counted in the
audit; the caller decides what to do. This is project #1's rule, and the reason it
exists: an unmatched depot means the CRS is wrong, an unmatched grid cell usually
means a coastal centroid just offshore. Same symptom, different problems — and
silently dropping either would enlarge a coverage gap that then looks like a
finding.

**Every reader returns `(frame, audit)`.** Reuse `Audit` from
`actionwise.data.cleaner_eb547` — import it, don't reimplement it. Project #2
importing project #1 is the allowed direction; the reverse is blocked by
`tests/test_geo_isolation.py`.

---

## Reading the grid without extracting it

The archive is 566 MB and holds five renderings of the same data. Only the 76 MB
parquet is needed, and `zipfile` handles are seekable, so it reads in place:

```python
z = zipfile.ZipFile(POPGRID_ZIP)
pf = pq.ParquetFile(z.open(POPGRID_MEMBER))
for i in range(pf.metadata.num_row_groups):          # 5 row groups
    chunk = pf.read_row_group(i, columns=list(POPGRID_COLUMNS)).to_pandas()
    keep.append(chunk[chunk.CNTR_ID == "LV"])        # filter as you go
```

4,595,932 rows EU-wide → **64,636** Latvian cells. Never extract the 1.3 GB
GeoPackage.

---

## What "done" looks like

- 27 new tests green, and the existing **148 still green**
- `python -m pytest -q` stays under ~30 s (the OSM parse is `-m slow`, opt-in)
- `T` sums to **1,888,613** — 0.24% under the census, inside tolerance
- 87 depots, all inside Latvia, regional counts 20/19/18/17/13

Then Phase 2 wires these three into the sanity gate, which is where a mistake in
any of them would surface anyway — but far more expensively.
