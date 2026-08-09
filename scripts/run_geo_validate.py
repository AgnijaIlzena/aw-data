"""Phase 6 — external validation.

Usage:
    python scripts/run_geo_validate.py

Two checks: the model's national mean response against VUGD's published average
(which works), and a rank check against NMPD per-municipality compliance (which
does not, for reasons the output states).

Writes geo_validation_national, geo_validation_ranks, geo_nmpd to DuckDB.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from actionwise.db.duckdb_client import write_table
from actionwise_geo.config import OSM_PBF, TURNOUT_MINUTES
from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.popgrid import load_population_grid
from actionwise_geo.indices.tth import (
    cell_travel_times,
    distance_from_nearest_depot,
    time_from_nearest_depot,
)
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points
from actionwise_geo.validate.nmpd import (
    COMPLIANCE,
    interpret,
    load_nmpd,
    national_check,
    rank_check,
)

YEAR = 2024


def main() -> int:
    print("=" * 100)
    print("PHASE 6 — EXTERNAL VALIDATION")
    print("=" * 100)

    import pyrosm

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()

    osm = pyrosm.OSM(str(OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    graph, audit = build_graph(nodes, edges, speed_factor=1.0, audit=audit)

    depot_snap, audit = snap_points(depots, graph, audit=audit)
    cell_snap, audit = snap_points(cells, graph, audit=audit)
    travel, audit = cell_travel_times(
        cells, cell_snap,
        time_from_nearest_depot(graph, depot_snap["node_index"]),
        depots=depots,
        node_metres=distance_from_nearest_depot(graph, depot_snap["node_index"]),
        audit=audit,
    )

    # ── 1. the check that works ────────────────────────────────────────────
    weights = cells["T"]
    mean_response = float(
        (travel["response_minutes"] * weights).sum() / weights.sum()
    )
    national = national_check(mean_response)
    print("\n" + "=" * 100)
    print("CHECK 1 — model vs VUGD's published national average arrival")
    print("=" * 100)
    print(national.to_string(index=False))
    print(f"\n  {'PASS' if bool(national['pass'].iloc[0]) else 'FAIL'} — "
          "the model should sit below the published figure, which includes "
          "dispatch time and real-world routing.")

    # ── 2. the rank check ──────────────────────────────────────────────────
    placed, audit = assign_municipality(cells, boundaries, audit=audit)
    municipality = pd.Series(placed["municipality"].to_numpy(), index=cells.index)

    frame = pd.DataFrame({
        "municipality": municipality,
        "population": weights.to_numpy(),
        "response": travel["response_minutes"].to_numpy(),
        "baseline": travel["baseline_minutes"].to_numpy() + TURNOUT_MINUTES,
        "density": cells["density"].to_numpy(),
    }).dropna(subset=["municipality"])

    def weighted(group, column):
        return (group[column] * group["population"]).sum() / group["population"].sum()

    model = frame.groupby("municipality").apply(
        lambda g: pd.Series({
            "mean_response_min": weighted(g, "response"),
            "euclidean_baseline_min": weighted(g, "baseline"),
            "mean_density": weighted(g, "density"),
        }),
        include_groups=False,
    )
    depot_place, audit = assign_municipality(depots, boundaries, audit=audit)
    model["depots_per_100k"] = (
        depot_place["municipality"].value_counts().reindex(model.index).fillna(0)
        / frame.groupby("municipality")["population"].sum() * 1e5
    )

    observed, audit = load_nmpd(audit=audit)
    ranks, audit = rank_check(model, observed, year=YEAR, audit=audit)

    print("\n" + "=" * 100)
    print(f"CHECK 2 — rank correlation against NMPD compliance, {YEAR}")
    print("=" * 100)
    print("  NMPD targets (MK 555): 12 min major cities / 15 other cities / 25 rural.")
    print("  All 35 matched municipalities are novadi, so all sit at 25 minutes.\n")
    print(ranks.round(3).to_string(index=False))
    print("\n" + interpret(ranks))

    # ── the caveats, in the output rather than a footnote ──────────────────
    aggregate = observed[observed["is_aggregate"] & (observed["year"] == YEAR)]
    total = observed[observed["year"] == YEAR]["Rez_1_2_prior_izsauk"].sum()
    print("\n" + "=" * 100)
    print("WHAT THIS COMPARISON CANNOT SEE")
    print("=" * 100)
    print(f"  · the 7 valstspilsētas are one aggregate row carrying "
          f"{aggregate['Rez_1_2_prior_izsauk'].iloc[0] / total:.0%} of all "
          "priority 1-2 calls, and cannot be mapped")
    print("  · NMPD ambulance stations are NOT published; the model routes from "
          "VUGD fire depots, a different network")
    print("  · compliance is weighted by calls, the model by residents — the "
          "elderly and rural generate more priority 1-2 calls per capita")
    print("  · 2025 is a partial year and is excluded from the comparison")

    write_table(national, "geo_validation_national")
    write_table(ranks, "geo_validation_ranks")
    write_table(observed, "geo_nmpd")
    write_table(model.reset_index(), "geo_model_by_municipality")
    write_table(audit.to_frame(), "geo_audit_validate")
    print("\nWrote geo_validation_national, geo_validation_ranks, geo_nmpd, "
          "geo_model_by_municipality, geo_audit_validate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
