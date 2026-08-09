# Model card — TTH (Time-to-Help)

**What it measures.** Minutes from the nearest of 87 VUGD depots to every populated 1 km cell, along the drivable road network. Response time adds the **1.5 min turnout** required by MK 297 p. 5; travel and response are separate columns so neither is ever reported as the other.

**Method.** Multi-source Dijkstra (`scipy.sparse.csgraph`, `min_only=True`) over a CSR graph of 1,346,594 nodes and 1,380,480 edges built from a dated OSM extract. One pass treats all 87 depots as a single source set.

**Data version.** OSM `latvia-260804.osm.pbf`, snapshot 2026-08-04. Pinned deliberately: `latvia-latest.osm.pbf` points at a different file every day and results built on it cannot be reproduced.

## Coverage

|   speed_factor | threshold                         |   population |      share |
|---------------:|:----------------------------------|-------------:|-----------:|
|            1   | within 8 min (served settlements) |      1251095 | 0.664145   |
|            1   | within 23 min (elsewhere)         |      1861311 | 0.988078   |
|            1   | beyond 23 min or unreachable      |        22458 | 0.0119218  |
|            1.2 | within 8 min (served settlements) |      1378624 | 0.731843   |
|            1.2 | within 23 min (elsewhere)         |      1877754 | 0.996807   |
|            1.2 | beyond 23 min or unreachable      |         6015 | 0.00319307 |

## Parameters

- speed factors reported: **1x, 1.2x** — rescue vehicles lawfully exceed posted limits and the margin is not knowable from OSM, so both ends are given rather than one chosen
- snap radius: **2000 m**; beyond it a cell is flagged, not dropped
- `access=no` excluded; `access=private` and `destination` **kept**, because those restrictions do not bind emergency services on a call

## The dominant uncertainty is the speed model, not the routing

| speed_source   |   edges |    length_km |   share_of_length |
|:---------------|--------:|-------------:|------------------:|
| class_default  | 1125368 | 61351.1      |       0.839237    |
| tagged         |  255106 | 11752.3      |       0.160762    |
| global_default |       6 |     0.099891 |       1.36643e-06 |

`maxspeed` is tagged on only **18.5%** of drivable edges, so class defaults carry the rest — and coverage is thinnest on exactly the rural roads the 23-minute standard governs.

## Baseline

|   network_mean_min |   baseline_mean_min |   median_time_ratio |   cells |   median_detour |   p90_detour |   speed_factor |
|-------------------:|--------------------:|--------------------:|--------:|----------------:|-------------:|---------------:|
|              6.009 |               4.766 |               1.004 |   29394 |           1.227 |        1.541 |              1 |

**Two ratios, and reading only the first gives the wrong answer.** `median_time_ratio` compares network minutes against crow-flies minutes at an assumed 60 km/h; it lands near 1.00 and reads as *'the routing added nothing'*. `median_detour` is metres over metres — no speed in it at all — and shows the roads genuinely winding. The time ratio is confounded because the detour and the assumed baseline speed cancel.

---

*Generated 2026-08-07 by `scripts/build_geo_model_cards.py` · Python 3.11.7 · OSM snapshot `2026-08-04` · census 2021 · boundaries `administrativas_teritorijas_2026.gpkg`.*
