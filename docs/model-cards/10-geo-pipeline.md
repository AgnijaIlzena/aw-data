# Model card — geography pipeline and its sanity gate

**What it is.** The reference geography every travel time is built on: 87 VUGD depots, 42 administrative territories, and 64,636 census grid cells, all in EPSG:3059 (LKS-92 / Latvia TM).

**Why a gate at all.** A survey recoding error usually shows up as an implausible percentage. A CRS or join error produces a *map*, and maps are persuasive. Everything downstream inherits the geography silently, so it is checked against things outside this pipeline before anything is built on it.

## The gate — 12/12 checks

| check                              | expected                           | observed                           | pass   | note                                                             |
|:-----------------------------------|:-----------------------------------|:-----------------------------------|:-------|:-----------------------------------------------------------------|
| CRS of depots                      | EPSG:3059                          | EPSG:3059                          | True   | metres, not degrees                                              |
| CRS of boundaries                  | EPSG:3059                          | EPSG:3059                          | True   | metres, not degrees                                              |
| CRS of grid                        | EPSG:3059                          | EPSG:3059                          | True   | metres, not degrees                                              |
| grid population vs census 2021     | 1,893,223                          | 1,888,613                          | True   | 0.24% apart, tolerance 3%                                        |
| grid cell count                    | 64,636                             | 64,636                             | True   | Latvia only                                                      |
| depot count                        | 87                                 | 87                                 | True   |                                                                  |
| depots per region                  | Rīg=20 Vid=19 Lat=18 Zem=17 Kur=13 | Rīg=20 Vid=19 Lat=18 Zem=17 Kur=13 | True   | the register states its own expected answer                      |
| depots inside a municipality       | 87/87                              | 87/87                              | True   | a miss means the layers disagree about where Latvia is           |
| population conserved by the join   | 1,883,769                          | 1,880,034 + 3,735                  | True   | an identity — it cannot hold by accident                         |
| population outside every territory | < 1%                               | 0.20%                              | True   | 100 cells                                                        |
| unplaced cells are coastal         | all within 1000 m                  | max 558 m, median 144 m            | True   | 1 km centroids landing just offshore where the coast cuts a cell |
| Rīga's share of the population     | 30%-35%                            | 32.4%                              | True   | 611,301 people; CSP: 'every third resident'                      |

## The traps in this data, all measured rather than assumed

1. **A mislabelled CRS.** `valsts_ugunsdzesibas_un_glabsanas_dienests.xlsx` declares LKS-92 in its portal metadata and holds WGS84 degrees. It is also the property register, not the depot list. The authoritative file is `vugd_depo_adreses.csv` (87 rows).
2. **`-9999` is a confidentiality sentinel** on the census age bands, never on the total. Summed naively `Y_GE65` totals **-211,308,180**. Suppression hits 19,139 of 29,587 populated cells — the *sparse* ones, which are the remote ones this project is about.
3. **`LAND_SURFACE` is a fraction, not an area.** Density needs it as a divisor or every coastal and riverside cell is understated.
4. **`GRD_ID` names the cell corner**, not its centre. The 500 m offset is invisible nationally and enough to cross an isochrone boundary.
5. **4,844 people have no location.** The `LV_unallocated` row is census population that could not be placed. It is kept and flagged, because the national total (reconciling to the census) and the mappable total (the only correct coverage denominator) differ by it.
6. **42 territories is not all of Latvia** — Varakļānu nov. is absent from the 2026 boundaries.

## Denominators

- national (reconciles to census): **1,888,613**
- unallocated, no grid square: **4,844**
- **mappable** (used for every share): **1,883,769**

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
