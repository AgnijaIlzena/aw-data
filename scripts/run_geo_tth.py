"""Phase 3 — Time-to-Help from the 87 VUGD depots.

Usage:
    python scripts/run_geo_tth.py [--factor 1.0]

Takes a few minutes: the OSM parse alone is ~75 s, and the graph build and
Dijkstra follow. Writes geo_tth, geo_tth_coverage, geo_tth_baseline,
geo_speed_provenance to DuckDB.

Run the sanity gate first — everything here inherits that geography.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import pandas as pd

from actionwise.db.duckdb_client import write_table
from actionwise_geo.config import EMERGENCY_SPEED_FACTORS, OSM_PBF, OSM_SNAPSHOT_DATE
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.popgrid import load_population_grid
from actionwise_geo.indices.tth import (
    baseline_comparison,
    cell_travel_times,
    coverage_summary,
    distance_from_nearest_depot,
    time_from_nearest_depot,
)
from actionwise_geo.network.graph import build_graph, connected_report
from actionwise_geo.network.snap import snap_points, snap_quality


def _log(message: str, started: float) -> None:
    print(f"[{time.time() - started:6.1f}s] {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factor", type=float, default=None,
                        help="emergency speed uplift; default runs the whole range")
    args = parser.parse_args()
    factors = [args.factor] if args.factor else list(EMERGENCY_SPEED_FACTORS)

    started = time.time()
    print("=" * 100)
    print(f"PHASE 3 — TIME-TO-HELP   (OSM snapshot {OSM_SNAPSHOT_DATE})")
    print("=" * 100)

    import pyrosm

    depots, audit = load_depots()
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()
    _log(f"{len(depots)} depots, {len(cells):,} populated cells", started)

    osm = pyrosm.OSM(str(OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    _log(f"OSM parsed: {len(nodes):,} nodes, {len(edges):,} edges", started)

    results, coverages, baselines, provenances = [], [], [], []

    for factor in factors:
        print("\n" + "=" * 100)
        print(f"SPEED FACTOR {factor}x"
              + ("  (posted legal limits)" if factor == 1.0
                 else "  (emergency-vehicle uplift)"))
        print("=" * 100)

        graph, audit = build_graph(nodes, edges, speed_factor=factor, audit=audit)
        _log(f"graph: {graph.n_nodes:,} nodes, {graph.n_edges:,} arcs", started)

        depot_snap, audit = snap_points(depots, graph, audit=audit)
        cell_snap, audit = snap_points(cells, graph, audit=audit)

        node_minutes = time_from_nearest_depot(graph, depot_snap["node_index"])
        node_metres = distance_from_nearest_depot(graph, depot_snap["node_index"])
        _log(f"dijkstra done; {np.isinf(node_minutes).sum():,} nodes unreachable",
             started)

        travel, audit = cell_travel_times(cells, cell_snap, node_minutes,
                                          depots=depots, node_metres=node_metres,
                                          audit=audit)

        coverage = coverage_summary(cells, travel)
        baseline = baseline_comparison(travel, cells["T"])

        print("\nCOVERAGE — population by response time (travel + 1.5 min turnout)")
        print("-" * 100)
        print(coverage.assign(
            population=lambda d: d["population"].map("{:,}".format),
            share=lambda d: d["share"].map("{:.1%}".format),
        ).to_string(index=False))

        print("\nNETWORK vs STRAIGHT LINE — decomposed")
        print("-" * 100)
        print("  time_ratio mixes the road detour with the baseline's assumed speed;")
        print("  detour is metres-over-metres, so it has no speed in it at all.\n")
        print(baseline.round(3).to_string(index=False))

        print("\nSPEED PROVENANCE — share of network LENGTH by source")
        print("-" * 100)
        print(graph.provenance.assign(
            length_km=lambda d: d["length_km"].map("{:,.0f}".format),
            share_of_length=lambda d: d["share_of_length"].map("{:.1%}".format),
        ).to_string(index=False))

        quality = snap_quality(cell_snap, cells["T"])
        print(f"\nSNAPPING — median {quality['median_m']:.0f} m, p99 "
              f"{quality['p99_m']:.0f} m, max {quality['max_m']:.0f} m; "
              f"{quality['suspect']} suspect cell(s) holding "
              f"{quality['population_suspect']:,.0f} people")

        results.append(travel.assign(grd_id=cells["grd_id"].to_numpy(),
                                     population=cells["T"].to_numpy(),
                                     speed_factor=factor))
        coverages.append(coverage.assign(speed_factor=factor))
        baselines.append(baseline.assign(speed_factor=factor))
        provenances.append(graph.provenance.assign(speed_factor=factor))

        if factor == factors[0]:
            components = connected_report(graph)
            largest = components["share"].iloc[0]
            print(f"\nCONNECTIVITY — largest component holds {largest:.1%} of nodes; "
                  f"{len(components)} components shown of many")

    write_table(pd.concat(results, ignore_index=True), "geo_tth")
    write_table(pd.concat(coverages, ignore_index=True), "geo_tth_coverage")
    write_table(pd.concat(baselines, ignore_index=True), "geo_tth_baseline")
    write_table(pd.concat(provenances, ignore_index=True), "geo_speed_provenance")
    write_table(audit.to_frame(), "geo_audit_tth")

    print("\nWrote geo_tth, geo_tth_coverage, geo_tth_baseline, geo_speed_provenance, "
          "geo_audit_tth to DuckDB.")
    _log("done", started)
    return 0


if __name__ == "__main__":
    sys.exit(main())
