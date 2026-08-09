"""Phase 5 — traffic-adjusted Time-to-Help.

Usage:
    python scripts/run_geo_traffic.py

Reports free-flow and traffic-adjusted travel times side by side, across the
emergency-damping range. Never replaces the free-flow figure.

Writes geo_traffic_long, geo_traffic_overlap, geo_congestion_summary,
geo_tth_traffic to DuckDB.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from actionwise.db.duckdb_client import write_table
from actionwise_geo.config import (
    CRS_WORKING,
    EMERGENCY_CONGESTION_DAMPING,
    OSM_PBF,
    SETTLEMENT_DENSITY_FLOOR,
)
from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.kmmarkers import load_km_markers
from actionwise_geo.data.popgrid import load_population_grid
from actionwise_geo.data.traffic import latest_year, load_traffic, overlap_agreement
from actionwise_geo.indices.coverage import compliance
from actionwise_geo.indices.settlements import (
    applicable_target,
    lattice_clusters,
    served_settlements,
)
from actionwise_geo.indices.tth import cell_travel_times, time_from_nearest_depot
from actionwise_geo.network.congestion import (
    apply_congestion,
    attach_aadt,
    congestion_summary,
    edge_chainage,
)
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points


def pct(v) -> str:
    return "—" if pd.isna(v) else f"{v:.1%}"


def main() -> int:
    started = time.time()
    print("=" * 100)
    print("PHASE 5 — TRAFFIC-ADJUSTED TIME-TO-HELP")
    print("=" * 100)

    import pyrosm

    traffic, audit = load_traffic()
    markers, audit = load_km_markers(audit=audit)
    print(f"\n[{time.time()-started:5.0f}s] traffic {len(traffic):,} rows / "
          f"{traffic['road'].nunique():,} roads; markers {len(markers):,}")

    agreement = overlap_agreement(traffic)
    print("\nCROSS-CHECK — do the two publications agree where they overlap?")
    print("-" * 100)
    print(agreement.assign(
        share_identical=lambda d: d["share_identical"].map(pct)
    ).to_string(index=False))

    segments = latest_year(traffic)
    print(f"\n  using {len(segments):,} latest-year segments")

    depots, audit = load_depots(audit=audit)
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()

    osm = pyrosm.OSM(str(OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    edges = edges.to_crs(epsg=CRS_WORKING)
    print(f"[{time.time()-started:5.0f}s] OSM: {len(edges):,} edges reprojected")

    chainage, audit = edge_chainage(edges, markers, audit=audit)
    aadt, audit = attach_aadt(chainage, segments, audit=audit)
    print(f"[{time.time()-started:5.0f}s] {aadt['aadt'].notna().sum():,} edges carry "
          f"an observed vehicle count "
          f"({aadt['aadt'].notna().mean():.1%} of the network)")

    placed, audit = assign_municipality(cells, boundaries, audit=audit)
    municipality = pd.Series(placed["municipality"].to_numpy(), index=cells.index)
    labels = lattice_clusters(cells, min_density=SETTLEMENT_DENSITY_FLOOR,
                              within=municipality)
    served, audit = served_settlements(cells, labels, depots, audit=audit)
    target = applicable_target(served)

    rows = []
    for damping in EMERGENCY_CONGESTION_DAMPING:
        congested, audit = apply_congestion(edges, aadt, damping=damping, audit=audit)
        graph, audit = build_graph(nodes, congested, speed_factor=1.0, audit=audit)

        depot_snap, audit = snap_points(depots, graph, audit=audit)
        cell_snap, audit = snap_points(cells, graph, audit=audit)
        travel, audit = cell_travel_times(
            cells, cell_snap,
            time_from_nearest_depot(graph, depot_snap["node_index"]),
            audit=audit,
        )
        national = compliance(cells, travel, target)
        cci = national.loc[national["applies_to"] == "ALL (CCI)", "compliance"].iloc[0]
        mean_response = float(
            (travel["response_minutes"] * cells["T"]).sum() / cells["T"].sum()
        )
        rows.append({
            "damping": damping,
            "label": {0.0: "unaffected (free-flow)", 0.5: "half a car's delay",
                      1.0: "delayed like a car"}.get(damping, str(damping)),
            "mean_response_min": mean_response,
            "cci": cci,
            "beyond_target": int(
                cells["T"][(travel["response_minutes"] > target).fillna(True)].sum()
            ),
        })
        print(f"[{time.time()-started:5.0f}s] damping {damping}: mean response "
              f"{mean_response:.2f} min, CCI {cci:.1%}")

    result = pd.DataFrame(rows)
    print("\n" + "=" * 100)
    print("FREE-FLOW vs TRAFFIC-ADJUSTED — reported side by side, never replaced")
    print("=" * 100)
    print("  Traffic must yield to a blue-light vehicle, so a fire engine does not")
    print("  sit in the queue BPR describes. Damping 1.0 is the pessimistic bound.\n")
    print(result.assign(
        mean_response_min=lambda d: d["mean_response_min"].map("{:.2f}".format),
        cci=lambda d: d["cci"].map(pct),
        beyond_target=lambda d: d["beyond_target"].map("{:,}".format),
    ).to_string(index=False))

    free = result.loc[result["damping"] == 0.0, "mean_response_min"].iloc[0]
    worst = result["mean_response_min"].max()
    print(f"\n  Congestion costs at most {worst - free:.2f} min on the national "
          f"population-weighted mean ({(worst/free - 1):.1%}).")

    print("\n" + "=" * 100)
    print("WHERE THE ADJUSTMENT BITES — by road class")
    print("=" * 100)
    congested, _ = apply_congestion(edges, aadt, damping=1.0)
    summary = congestion_summary(congested, aadt)
    print(summary.head(10).round(3).to_string(index=False))

    write_table(traffic, "geo_traffic_long")
    write_table(agreement, "geo_traffic_overlap")
    write_table(summary, "geo_congestion_summary")
    write_table(result, "geo_tth_traffic")
    write_table(audit.to_frame(), "geo_audit_traffic")
    print("\nWrote geo_traffic_long, geo_traffic_overlap, geo_congestion_summary, "
          "geo_tth_traffic, geo_audit_traffic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
