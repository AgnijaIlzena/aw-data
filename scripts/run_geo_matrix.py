"""Phase 7 — the Preparedness–Proximity matrix.

Usage:
    python scripts/run_geo_matrix.py

Joins project #2's travel times to project #1's resilience horizon on community
type, and reports both axes side by side. Requires project #1's `rhi_respondents`
table — run `scripts/run_rhi.py` first.

Writes geo_matrix, geo_matrix_degurba, geo_riga_contrast, geo_class_calibration.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pyreadstat

from actionwise.config import EB547_SAV, RESILIENCE_TARGET_DAYS, WEIGHT_NATIONAL
from actionwise.db.duckdb_client import get_connection, write_table
from actionwise_geo.config import OSM_PBF
from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.popgrid import load_population_grid
from actionwise_geo.indices.matrix import (
    D25_TO_CLASS,
    calibrate_density_thresholds,
    classify_cells,
    preparedness_by_class,
    proximity_by_class,
    proximity_matrix,
    riga_contrast,
    survey_class_shares,
)
from actionwise_geo.indices.tth import cell_travel_times, time_from_nearest_depot
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points


def load_survey() -> pd.DataFrame:
    """RHI per respondent, joined to the community type and region from the .sav."""
    con = get_connection(read_only=True)
    try:
        rhi = con.execute(
            "SELECT uniqid, rhi_days, rhi_band, w_national "
            "FROM rhi_respondents WHERE country_grouped = 'LV'"
        ).fetchdf()
    finally:
        con.close()

    raw, _ = pyreadstat.read_sav(
        str(EB547_SAV), usecols=["uniqid", "isocntry", "d25", "region_latvia"]
    )
    lv = raw[raw["isocntry"] == "LV"]
    survey = rhi.merge(lv[["uniqid", "d25", "region_latvia"]], on="uniqid", how="left")
    survey["community_class"] = survey["d25"].map(D25_TO_CLASS)
    return survey


def pct(v) -> str:
    return "—" if pd.isna(v) else f"{v:.1%}"


def main() -> int:
    print("=" * 100)
    print("PHASE 7 — PREPAREDNESS x PROXIMITY")
    print("=" * 100)
    print("  project #1: how many DAYS a household lasts   (RHI, EB547)")
    print("  project #2: how many MINUTES until help       (TTH, road network)")

    import pyrosm

    survey = load_survey()
    matched = survey["community_class"].notna().sum()
    print(f"\n  survey: {len(survey)} Latvian respondents, {matched} with a "
          f"community type, {survey['rhi_days'].notna().sum()} with an RHI")

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
        audit=audit,
    )

    # ── calibrate the classes so both sides describe the same people ───────
    shares = survey_class_shares(survey)
    thresholds = calibrate_density_thresholds(cells, shares)

    calibration = pd.DataFrame([{
        "survey_rural": shares.get("rural"),
        "survey_urban_cluster": shares.get("urban_cluster"),
        "survey_urban_centre": shares.get("urban_centre"),
        "calibrated_cluster_min_per_km2": thresholds["urban_cluster_min"],
        "calibrated_centre_min_per_km2": thresholds["urban_centre_min"],
    }])
    print("\n" + "=" * 100)
    print("CLASS CALIBRATION — matching measured density to the survey's own split")
    print("=" * 100)
    print("  Density and self-report disagree about where a town begins, so the")
    print("  cutoffs are set to reproduce the survey's population shares. Without")
    print("  this the two axes describe different groups of people.\n")
    print(calibration.round(1).to_string(index=False))

    classes = classify_cells(cells, thresholds)
    degurba_classes = classify_cells(cells, None)

    # ── the matrix ─────────────────────────────────────────────────────────
    proximity = proximity_by_class(cells, travel, classes)
    preparedness = preparedness_by_class(survey)
    matrix = proximity_matrix(proximity, preparedness)

    print("\n" + "=" * 100)
    print("THE MATRIX — two axes, deliberately not combined")
    print("=" * 100)
    shown = matrix.assign(
        population=lambda d: d["population"].map("{:,}".format),
        mean_response_min=lambda d: d["mean_response_min"].map("{:.1f}".format),
        share_beyond_23min=lambda d: d["share_beyond_23min"].map(pct),
        mean_rhi_days=lambda d: d["mean_rhi_days"].map("{:.2f}".format),
        under_3d=lambda d: d.apply(
            lambda r: f"{r['share_under_target_certain']:.0%}-"
                      f"{r['share_under_target_upper']:.0%}", axis=1),
    )
    print(shown[["community_class", "population", "mean_response_min",
                 "share_beyond_23min", "n", "n_effective", "mean_rhi_days",
                 "under_3d", "thin_cell"]].to_string(index=False))
    print("\n  under_3d is a BRACKET, not a point: band 2 is literally '2-3 days',")
    print("  so whether those households clear a 3-day target is unknowable.")
    print(f"\n  ⚠ {matrix.attrs['warning']}")

    # the sentence the pair exists to produce
    rural = matrix[matrix["community_class"] == "rural"].iloc[0]
    centre = matrix[matrix["community_class"] == "urban_centre"].iloc[0]
    print("\n  " + "-" * 96)
    print(f"  RURAL   help takes {rural['mean_response_min']:5.1f} min  |  "
          f"{rural['share_under_target_certain']:.0%}-"
          f"{rural['share_under_target_upper']:.0%} of households could NOT last "
          f"{RESILIENCE_TARGET_DAYS:.0f} days")
    print(f"  CITIES  help takes {centre['mean_response_min']:5.1f} min  |  "
          f"{centre['share_under_target_certain']:.0%}-"
          f"{centre['share_under_target_upper']:.0%} could NOT")
    print("  " + "-" * 96)
    print("  The two axes run OPPOSITE ways: the countryside is slower to reach and")
    print("  better stocked; the cities are quick to reach and least prepared.")

    # ── the same table on uncalibrated DEGURBA classes ─────────────────────
    degurba = proximity_matrix(
        proximity_by_class(cells, travel, degurba_classes), preparedness
    )
    print("\n" + "=" * 100)
    print("SAME TABLE ON UNCALIBRATED DEGURBA CLASSES — the definitional gap")
    print("=" * 100)
    print(degurba[["community_class", "population", "mean_response_min"]]
          .assign(population=lambda d: d["population"].map("{:,}".format),
                  mean_response_min=lambda d: d["mean_response_min"].map("{:.1f}".format))
          .to_string(index=False))

    # ── the one unambiguous NUTS3 contrast ─────────────────────────────────
    placed, audit = assign_municipality(cells, boundaries, audit=audit)
    municipality = pd.Series(placed["municipality"].to_numpy(), index=cells.index)
    riga = riga_contrast(cells, travel, municipality, survey)

    print("\n" + "=" * 100)
    print("RĪGA vs THE REST — the only NUTS3 comparison with no crosswalk needed")
    print("=" * 100)
    print(riga.assign(
        population=lambda d: d["population"].map("{:,}".format),
        mean_response_min=lambda d: d["mean_response_min"].map("{:.1f}".format),
        mean_rhi_days=lambda d: d["mean_rhi_days"].map("{:.2f}".format),
    ).to_string(index=False))
    print("\n  The other five NUTS3 regions are not reported: no verified "
          "municipality-to-NUTS3\n  crosswalk exists in dati/, and inventing one "
          "for 35 novadi would put a guess\n  underneath the headline.")

    write_table(matrix, "geo_matrix")
    write_table(degurba, "geo_matrix_degurba")
    write_table(riga, "geo_riga_contrast")
    write_table(calibration, "geo_class_calibration")
    write_table(audit.to_frame(), "geo_audit_matrix")
    print("\nWrote geo_matrix, geo_matrix_degurba, geo_riga_contrast, "
          "geo_class_calibration, geo_audit_matrix.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
