# Model card — CCI (Coverage Compliance Index)

**What it measures.** The share of people who can be reached within *the legal target that applies where they live*.

**Why not one national threshold.** MK noteikumi Nr. 297 (17.05.2016, in force 20.05.2016) sets two:

- **p. 6.1 — 8 min** in a *pilsēta, ciems* or *mazciems* holding a VUGD unit
- **p. 6.2 — 23 min** everywhere else
- **p. 5 — 1.5 min** turnout, inside both

A single national *'% within 8 minutes'* would judge rural Latvia against a standard the law does not apply to it; *'% within 23 minutes'* would flatter the cities.

## Settlement delineation

The 8-minute rule attaches to the **settlement**, not the municipality. Settlements are grown by contiguity on the census grid (8-connectivity on the EPSG:3035 lattice) above a density floor of **50/km²**, and **may not cross a municipality boundary**.

That last rule is load-bearing. Without it the built-up corridors fuse Salaspils, Mārupe and Ropaži into Rīga, and those towns inherit the 8-minute standard from depots they do not have — Salaspils goes from 95.6% of its population on the strict standard to 0.0%, which is the correct answer.

The floor is 50, not DEGURBA's 300, because the regulation names *ciems* and *mazciems* explicitly and at 300/km² only 66 of 87 depots sit in a qualifying cell.

## Result

| applies_to        |   target_min |   population |   within_target |   compliance |   speed_factor |
|:------------------|-------------:|-------------:|----------------:|-------------:|---------------:|
| served settlement |            8 |      1277853 |         1154557 |     0.903513 |              1 |
| elsewhere         |           23 |       605916 |          584722 |     0.965022 |              1 |
| ALL (CCI)         |          nan |      1883769 |         1739279 |     0.923297 |              1 |

## Sensitivity to where a settlement ends

|   density_floor |   settlements_served |   population_on_8min |   share_on_8min |      cci |   speed_factor |
|----------------:|---------------------:|---------------------:|----------------:|---------:|---------------:|
|              50 |                   74 |          1.27785e+06 |        0.678349 | 0.923297 |              1 |
|             100 |                   79 |          1.25162e+06 |        0.664425 | 0.929156 |              1 |
|             300 |                   75 |          1.1853e+06  |        0.629215 | 0.935223 |              1 |

## Over-65s — an upper bound, not an estimate

| band   |   population_with_age_detail |   within_target |   compliance |   cells_with_detail |   cells_suppressed |   coverage |   speed_factor |
|:-------|-----------------------------:|----------------:|-------------:|--------------------:|-------------------:|-----------:|---------------:|
| Y_GE65 |                       369546 |          338939 |     0.917177 |               10447 |              19139 |   0.353106 |              1 |

Age bands are suppressed in sparse cells, which are the remote ones with the longest response times. This figure therefore under-represents the worst-served over-65s and should be read as an **upper bound** on compliance. The `coverage` column is the share of cells it could see.

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
