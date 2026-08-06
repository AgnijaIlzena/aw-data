"""Phase 3 — the descriptive gap table. The central question, answered with no model.

Usage:
    python scripts/run_gap_table.py

Writes `gap_table_eu` / `gap_table_lv` / `gap_cells_eu` to DuckDB for the
dashboard, and prints the tables.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.db.duckdb_client import write_table
from actionwise.indices.pgi import gap_cells, gap_table, person_pgi
from actionwise.weighting import weighted_mean

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"


def _pct(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for c in cols:
        out[c] = (out[c] * 100).map(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    return out


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    lv = df[df["country_grouped"] == "LV"]

    print(f"Loaded {len(df):,} respondents  ·  Latvia n = {len(lv):,}\n")

    # ── The four cells ──────────────────────────────────────────────────────
    cells = gap_cells(df, weight="w_eu")
    print("=" * 96)
    print("AWARENESS x ACTION — all 13 measures pooled, EU-wide, weighted")
    print("=" * 96)
    print(_pct(cells, ["weighted_share"]).to_string(index=False))

    # ── Per-item conversion, EU then Latvia ─────────────────────────────────
    eu = gap_table(df, weight="w_eu")
    lvt = gap_table(lv, weight="w_national")

    show = ["label", "pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware", "gap", "lift"]
    pct_cols = ["pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware", "gap"]

    for title, table in (("EU-WIDE", eu), ("LATVIA", lvt)):
        print("\n" + "=" * 96)
        print(f"{title} — per measure: how many did it, split by whether they had seen information")
        print("=" * 96)
        body = _pct(table[show], pct_cols)
        body["lift"] = table["lift"].map(lambda v: f"{v:.2f}x" if pd.notna(v) else "—")
        print(body.to_string(index=False))

    # ── Person-level PGI ────────────────────────────────────────────────────
    df = df.assign(pgi=person_pgi(df))
    lv = df[df["country_grouped"] == "LV"]
    print("\n" + "=" * 96)
    print("PGI — per-person share of known-but-not-done measures (unweighted item difficulty)")
    print("=" * 96)
    print(f"  EU mean PGI     : {weighted_mean(df, 'pgi', 'w_eu'):.3f}")
    print(f"  Latvia mean PGI : {weighted_mean(lv, 'pgi', 'w_national'):.3f}")
    print(f"  measurable for  : {int(df['pgi'].notna().sum()):,} of {len(df):,} respondents")

    # ── Persist for the dashboard ───────────────────────────────────────────
    write_table(eu, "gap_table_eu")
    write_table(lvt, "gap_table_lv")
    write_table(cells, "gap_cells_eu")
    write_table(
        df[["uniqid", "country_grouped", "pgi", "saw_info", "n_actions", "w_national", "w_eu"]],
        "pgi_respondents",
    )
    print("\nWrote gap_table_eu, gap_table_lv, gap_cells_eu, pgi_respondents to DuckDB.")


if __name__ == "__main__":
    main()
