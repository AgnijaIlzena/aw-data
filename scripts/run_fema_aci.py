"""Phase 11 (optional) — ACI from the FEMA National Household Survey.

Usage:
    python scripts/run_fema_aci.py

Prints clear instructions and exits 0 if the data has not been downloaded yet, so
this can sit in the run order without breaking a fresh checkout.

Writes fema_* tables to DuckDB. Delete those tables and the src/actionwise/fema/
package to remove this phase entirely — see docs/PHASE11-FEMA.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.db.duckdb_client import get_connection, write_table
from actionwise.fema import config as fcfg
from actionwise.fema.aci import aci_by_year, aci_table, compare_with_eb547, stage_distribution
from actionwise.fema.loader import FemaDataMissing, discover_columns, find_weight, load_all

CROSSWALK = Path(__file__).resolve().parents[1] / "src" / "actionwise" / "fema" / "crosswalk.csv"


def _pct(v) -> str:
    return "—" if pd.isna(v) else f"{v * 100:.1f}%"


def main() -> int:
    print("=" * 100)
    print("PHASE 11 (optional) — FEMA National Household Survey, item-level conversion")
    print("=" * 100)

    try:
        df, discovery = load_all()
    except FemaDataMissing as exc:
        print(f"\n{exc}\n")
        print("Phase 11 skipped. Everything else in the project is unaffected.")
        return 0

    print(f"\nLoaded {len(df):,} responses across years "
          f"{sorted(df['survey_year'].unique())}\n")

    # ── Column discovery — say what matched before trusting anything ────────
    print("=" * 100)
    print("COLUMN DISCOVERY — the paired A3/PREPB structure this phase depends on")
    print("=" * 100)
    latest = discovery[discovery["survey_year"] == discovery["survey_year"].max()]
    print(latest[["item", "label", "awareness_col", "action_col", "paired"]].to_string(index=False))

    n_paired = int(latest["paired"].sum())
    print(f"\n  {n_paired} of {len(latest)} items have BOTH an awareness and an action column")
    if n_paired == 0:
        print("\n  ⚠ No paired items found. The column names in this release differ from the")
        print("    2022 instrument. Open the codebook inside the ZIP and set the mapping")
        print("    explicitly — do not proceed on a guess.")
        return 1
    if n_paired < len(latest) / 2:
        print("  ⚠ Fewer than half the items paired — check the codebook before reading on.")

    weight_col = find_weight(df)
    print(f"  weight column: {weight_col or 'NONE FOUND — figures will be unweighted'}")

    # ── ACI ────────────────────────────────────────────────────────────────
    table = aci_table(df, discovery, weight_col)
    print("\n" + "=" * 100)
    print("ACI — of those who heard about THIS measure, how many did it")
    print("=" * 100)
    show = table[["label", "aci", "p_did_if_unaware", "lift", "share_aware", "n_rows"]].copy()
    for c in ("aci", "p_did_if_unaware", "share_aware"):
        show[c] = table[c].map(_pct)
    show["lift"] = table["lift"].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}×")
    print(show.to_string(index=False))

    # ── Stage of change ────────────────────────────────────────────────────
    stages = pd.DataFrame()
    if fcfg.STAGE_VAR in df.columns:
        stages = stage_distribution(df, fcfg.STAGE_VAR, weight_col)
        print("\n" + "=" * 100)
        print("STAGE OF CHANGE — the validated ladder EB547 has no equivalent for")
        print("=" * 100)
        print(stages.assign(share=stages["share"].map(_pct)).to_string(index=False))
        print("\n  This is the empirical grounding for the avatar's progression.")
    else:
        print(f"\n  note: {fcfg.STAGE_VAR} not present in this release — stage ladder skipped.")

    # ── Side by side with Europe ───────────────────────────────────────────
    comparison = pd.DataFrame()
    eu_path = DATA_PROCESSED / "eb547_features.parquet"
    con = get_connection(read_only=True)
    try:
        has_eu = not con.execute(
            "SELECT 1 FROM duckdb_tables() WHERE table_name = 'gap_table_eu' LIMIT 1"
        ).fetchdf().empty
        eu_gap = con.execute("SELECT * FROM gap_table_eu").fetchdf() if has_eu else None
    finally:
        con.close()

    if eu_gap is not None and CROSSWALK.exists():
        crosswalk = pd.read_csv(CROSSWALK).dropna(subset=["eb547_item", "fema_item"])
        comparison = compare_with_eb547(table, eu_gap, crosswalk)
        print("\n" + "=" * 100)
        print("EUROPE vs UNITED STATES — comparison only, never pooled")
        print("=" * 100)
        print("  FEMA measures a 12-month flow; EB547 measures a lifetime stock.")
        print("  Compare directions, not levels.\n")
        c = comparison.copy()
        c["aci"] = comparison["aci"].map(_pct)
        c["conversion"] = comparison["conversion"].map(_pct)
        c["conversion_gap_pp"] = comparison["conversion_gap_pp"].map(
            lambda v: "—" if pd.isna(v) else f"{v:+.1f}pp"
        )
        print(c[["eb547_item", "fema_item", "match_quality", "aci", "conversion",
                 "conversion_gap_pp"]].to_string(index=False))
    elif eu_gap is None:
        print("\n  note: gap_table_eu not in DuckDB — run scripts/run_gap_table.py to compare.")

    # ── Persist ────────────────────────────────────────────────────────────
    write_table(table, "fema_aci")
    write_table(discovery, "fema_column_discovery")
    if not stages.empty:
        write_table(stages, "fema_stage_of_change")
    if not comparison.empty:
        write_table(comparison, "fema_eu_comparison")
    by_year = aci_by_year(df, discovery, weight_col)
    if not by_year.empty:
        write_table(by_year, "fema_aci_by_year")
        print("\n  Trend written. Note: repeated cross-section — different people each "
              "year, so these are aggregate trends, not individual transitions.")

    print("\nWrote fema_aci, fema_column_discovery"
          + (", fema_stage_of_change" if not stages.empty else "")
          + (", fema_eu_comparison" if not comparison.empty else "")
          + (", fema_aci_by_year" if not by_year.empty else "")
          + " to DuckDB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
