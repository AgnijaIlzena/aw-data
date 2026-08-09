"""Phase 2 — the geography sanity gate.

Usage:
    python scripts/run_geo_sanity_gate.py

Exits non-zero when a check fails, so it can guard the rest of the pipeline.
Nothing downstream — travel times, coverage, compliance — should be believed
until this passes, because all of it inherits the geography silently.

Writes `geo_sanity_gate` and `geo_density_classes` to DuckDB.
"""
from __future__ import annotations

import sys

import pandas as pd

from actionwise.db.duckdb_client import write_table
from actionwise_geo.data.boundaries import load_boundaries
from actionwise_geo.data.depots import load_depots
from actionwise_geo.data.popgrid import load_population_grid, population_coverage
from actionwise_geo.validate.sanity import (
    density_class_comparison,
    format_gate,
    run_gate,
)


def survey_community_shares() -> dict[str, float] | None:
    """EB547 `d25` for Latvia, weighted — the diagnostic's other half.

    Returns None if the survey file is absent, so the gate still runs on a
    checkout that has only the geospatial data.
    """
    try:
        import pyreadstat

        from actionwise.config import EB547_SAV, WEIGHT_NATIONAL
    except ImportError:
        return None
    if not EB547_SAV.exists():
        return None

    df, _ = pyreadstat.read_sav(
        str(EB547_SAV), usecols=["isocntry", "d25", WEIGHT_NATIONAL]
    )
    lv = df[(df["isocntry"] == "LV") & df["d25"].isin([1, 2, 3])]
    weights = lv.groupby("d25")[WEIGHT_NATIONAL].sum() / lv[WEIGHT_NATIONAL].sum()
    return {
        "rural": float(weights.get(1.0, 0.0)),
        "urban_cluster": float(weights.get(2.0, 0.0)),
        "urban_centre": float(weights.get(3.0, 0.0)),
    }


def main() -> int:
    print("=" * 100)
    print("PHASE 2 — GEOGRAPHY SANITY GATE")
    print("=" * 100)

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)

    print("\nAUDIT TRAIL")
    print("-" * 100)
    with pd.option_context("display.width", 200, "display.max_colwidth", 88):
        print(audit.to_frame()[
            ["step", "rows_in", "rows_out", "cells_nulled", "reason"]
        ].to_string(index=False))

    # ── Coverage, stated before the gate so the denominators are explicit ───
    coverage = population_coverage(grid)
    print("\nPOPULATION DENOMINATORS")
    print("-" * 100)
    print(f"  national (reconciles to census) : {coverage['population']:>10,}")
    print(f"  unallocated, no grid square     : {coverage['unallocated_population']:>10,}")
    print(f"  MAPPABLE (coverage denominator) : {coverage['mappable_population']:>10,}")
    print(f"  with age detail                 : {coverage['population_with_age_detail']:>10,}"
          f"  ({coverage['age_coverage_share']:.1%})")

    # ── The gate ───────────────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("CHECKS")
    print("=" * 100)
    result = run_gate(depots, boundaries, grid)
    print(format_gate(result))

    # ── The diagnostic that is deliberately not a check ────────────────────
    shares = survey_community_shares()
    comparison = pd.DataFrame()
    if shares:
        comparison = density_class_comparison(grid, shares)
        print("\n" + "=" * 100)
        print("DIAGNOSTIC — measured density vs EB547 self-reported community type")
        print("=" * 100)
        print("  Reported, never gated on: these measure different things, and the")
        print("  rank orders genuinely differ. See validate/sanity.py for why.\n")
        shown = comparison.assign(
            grid_share=lambda d: (d["grid_share"] * 100).map("{:.1f}%".format),
            survey_share=lambda d: (d["survey_share"] * 100).map("{:.1f}%".format),
            gap_pp=lambda d: d["gap_pp"].map("{:+.1f}pp".format),
        )
        print(shown.to_string(index=False))
    else:
        print("\n  note: EB547 not available — density diagnostic skipped.")

    # ── Persist ────────────────────────────────────────────────────────────
    write_table(result, "geo_sanity_gate")
    write_table(audit.to_frame(), "geo_audit")
    if not comparison.empty:
        write_table(comparison, "geo_density_classes")
    print("\nWrote geo_sanity_gate, geo_audit"
          + (", geo_density_classes" if not comparison.empty else "")
          + " to DuckDB.")

    return 0 if bool(result["pass"].all()) else 1


if __name__ == "__main__":
    sys.exit(main())
