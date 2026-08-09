"""Phase 4 — legal compliance against MK 297.

Usage:
    python scripts/run_geo_coverage.py [--factor 1.0]

Delineates settlements by contiguity, applies the 8-minute standard where a
settlement holds a depot and 23 minutes elsewhere, and reports compliance
nationally, per municipality, and for over-65s.

Writes geo_compliance, geo_compliance_by_municipality, geo_settlements,
geo_elderly_compliance, geo_floor_sensitivity to DuckDB.
"""
from __future__ import annotations

import argparse
import sys
import time

import numpy as np
import pandas as pd

from actionwise.db.duckdb_client import write_table
from actionwise_geo.config import (
    EMERGENCY_SPEED_FACTORS,
    OSM_PBF,
    SETTLEMENT_DENSITY_FLOOR,
    SETTLEMENT_FLOOR_SENSITIVITY,
)
from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.popgrid import load_population_grid
from actionwise_geo.indices.coverage import (
    compliance,
    compliance_by_group,
    elderly_compliance,
    floor_sensitivity,
)
from actionwise_geo.indices.settlements import (
    applicable_target,
    lattice_clusters,
    served_settlements,
    settlement_summary,
)
from actionwise_geo.indices.tth import (
    cell_travel_times,
    distance_from_nearest_depot,
    time_from_nearest_depot,
)
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points


def pct(value) -> str:
    return "—" if pd.isna(value) else f"{value:.1%}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factor", type=float, default=EMERGENCY_SPEED_FACTORS[0])
    args = parser.parse_args()
    started = time.time()

    print("=" * 100)
    print("PHASE 4 — COVERAGE COMPLIANCE (MK noteikumi Nr. 297)")
    print("=" * 100)
    print("  p. 6.1  8 min  in a pilsēta/ciems/mazciems holding a VUGD unit")
    print("  p. 6.2 23 min  everywhere else")
    print("  p. 5   +90 s   turnout, inside both")

    import pyrosm

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()

    osm = pyrosm.OSM(str(OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    graph, audit = build_graph(nodes, edges, speed_factor=args.factor, audit=audit)

    depot_snap, audit = snap_points(depots, graph, audit=audit)
    cell_snap, audit = snap_points(cells, graph, audit=audit)
    travel, audit = cell_travel_times(
        cells, cell_snap,
        time_from_nearest_depot(graph, depot_snap["node_index"]),
        depots=depots,
        node_metres=distance_from_nearest_depot(graph, depot_snap["node_index"]),
        audit=audit,
    )
    print(f"\n[{time.time() - started:.0f}s] routed at speed factor {args.factor}x")

    # ── settlements ────────────────────────────────────────────────────────
    # A settlement may not cross a municipality boundary. Without that, the
    # built-up corridors fuse Salaspils, Mārupe and Ropaži into Rīga, and those
    # towns inherit the 8-minute standard from depots they do not have.
    placed, audit = assign_municipality(cells, boundaries, audit=audit)
    municipality = pd.Series(placed["municipality"].to_numpy(), index=cells.index)

    labels = lattice_clusters(cells, min_density=SETTLEMENT_DENSITY_FLOOR,
                              within=municipality)
    served, audit = served_settlements(cells, labels, depots, audit=audit)
    target = applicable_target(served)

    summary = settlement_summary(cells, labels, served)
    print("\n" + "=" * 100)
    print(f"SETTLEMENTS  (density floor {SETTLEMENT_DENSITY_FLOOR}/km², "
          "grown by contiguity on the census grid)")
    print("=" * 100)
    print(summary.assign(
        population=lambda d: d["population"].map("{:,}".format),
        share=lambda d: d["share"].map(pct),
    ).to_string(index=False))

    # ── compliance ─────────────────────────────────────────────────────────
    national = compliance(cells, travel, target)
    print("\n" + "=" * 100)
    print("CCI — share reaching help within the target that applies THERE")
    print("=" * 100)
    print(national.assign(
        population=lambda d: d["population"].map("{:,}".format),
        within_target=lambda d: d["within_target"].map("{:,}".format),
        compliance=lambda d: d["compliance"].map(pct),
    ).to_string(index=False))

    # ── over-65s ───────────────────────────────────────────────────────────
    elderly = elderly_compliance(cells, travel, target)
    print("\n" + "=" * 100)
    print("OVER-65s — the sharpest version, and the most fragile")
    print("=" * 100)
    print(elderly.assign(
        population_with_age_detail=lambda d: d["population_with_age_detail"].map("{:,}".format),
        within_target=lambda d: d["within_target"].map("{:,}".format),
        compliance=lambda d: d["compliance"].map(pct),
        coverage=lambda d: d["coverage"].map(pct),
    ).to_string(index=False))
    print(f"\n  ⚠ {elderly.attrs['caveat']}")

    # ── municipalities ─────────────────────────────────────────────────────
    by_municipality = compliance_by_group(cells, travel, target, municipality)
    print("\n" + "=" * 100)
    print("WORST-SERVED MUNICIPALITIES")
    print("=" * 100)
    shown = by_municipality.head(10).assign(
        population=lambda d: d["population"].map("{:,.0f}".format),
        compliance=lambda d: d["compliance"].map(pct),
        share_on_8min_standard=lambda d: d["share_on_8min_standard"].map(pct),
        mean_response_min=lambda d: d["mean_response_min"].map("{:.1f}".format),
    )
    print(shown[["group", "population", "mean_response_min",
                 "share_on_8min_standard", "compliance", "thin_cell"]]
          .to_string(index=False))

    # ── where does a settlement end? ───────────────────────────────────────
    sensitivity = floor_sensitivity(cells, travel, depots,
                                    SETTLEMENT_FLOOR_SENSITIVITY,
                                    within=municipality)
    print("\n" + "=" * 100)
    print("SENSITIVITY — where a settlement ends moves who is judged at 8 vs 23 min")
    print("=" * 100)
    print(sensitivity.assign(
        population_on_8min=lambda d: d["population_on_8min"].map("{:,}".format),
        share_on_8min=lambda d: d["share_on_8min"].map(pct),
        cci=lambda d: d["cci"].map(pct),
    ).to_string(index=False))

    write_table(national.assign(speed_factor=args.factor), "geo_compliance")
    write_table(by_municipality.assign(speed_factor=args.factor),
                "geo_compliance_by_municipality")
    write_table(summary.assign(speed_factor=args.factor), "geo_settlements")
    write_table(elderly.assign(speed_factor=args.factor), "geo_elderly_compliance")
    write_table(sensitivity.assign(speed_factor=args.factor), "geo_floor_sensitivity")
    write_table(audit.to_frame(), "geo_audit_coverage")

    print("\nWrote geo_compliance, geo_compliance_by_municipality, geo_settlements, "
          "geo_elderly_compliance, geo_floor_sensitivity, geo_audit_coverage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
