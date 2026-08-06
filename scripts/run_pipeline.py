"""Run the ETL: raw → interim → processed → DuckDB.

Usage:
    python scripts/run_pipeline.py [--source eb547]

Prints an audit table showing, for every step, how many rows went in, how many
came out, how many cells were nulled and why. A step that loses data without
appearing here is a bug.
"""
from __future__ import annotations

import argparse
import time

import pandas as pd

from actionwise.config import DATA_INTERIM, DATA_PROCESSED, EB547_EXPECTED_SHAPE
from actionwise.data.cleaner_eb547 import build_features, clean_eb547
from actionwise.data.loader import load_za8841
from actionwise.db.duckdb_client import get_connection, write_table

INTERIM_PATH = DATA_INTERIM / "eb547_clean.parquet"
PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"
TABLE = "eb547"


def _log(msg: str) -> None:
    print(f"[pipeline] {msg}", flush=True)


def run_eb547() -> None:
    DATA_INTERIM.mkdir(parents=True, exist_ok=True)
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)

    # ── Load ────────────────────────────────────────────────────────────────
    _log("Loading ZA8841 …")
    t0 = time.perf_counter()
    raw, meta = load_za8841()
    _log(f"  {raw.shape[0]:,} rows x {raw.shape[1]} cols in {time.perf_counter() - t0:.1f}s")

    if raw.shape != EB547_EXPECTED_SHAPE:
        raise SystemExit(
            f"source shape {raw.shape} != expected {EB547_EXPECTED_SHAPE}. "
            "This is a different file or a different survey version — stop and check "
            "before trusting anything downstream."
        )

    # ── Clean ───────────────────────────────────────────────────────────────
    _log("Cleaning (raw → interim) …")
    clean, audit = clean_eb547(raw)
    clean.to_parquet(INTERIM_PATH, index=False)
    _log(f"  → {INTERIM_PATH.name}  ({clean.shape[0]:,} x {clean.shape[1]})")

    # ── Features ────────────────────────────────────────────────────────────
    _log("Building features (interim → processed) …")
    feats, audit = build_features(clean, audit)
    feats.to_parquet(PROCESSED_PATH, index=False)
    _log(f"  → {PROCESSED_PATH.name}  ({feats.shape[0]:,} x {feats.shape[1]})")

    # ── DuckDB ──────────────────────────────────────────────────────────────
    _log(f"Writing DuckDB table '{TABLE}' …")
    n = write_table(feats, TABLE)
    _log(f"  {n:,} rows")

    # ── Audit trail ─────────────────────────────────────────────────────────
    trail = audit.to_frame()
    print("\n" + "=" * 100)
    print("AUDIT TRAIL — every row lost or cell nulled is accounted for below")
    print("=" * 100)
    with pd.option_context("display.width", 200, "display.max_colwidth", 70):
        print(trail.to_string(index=False))
    print("=" * 100)
    print(f"rows in: {raw.shape[0]:,}   rows out: {len(feats):,}   "
          f"rows lost: {raw.shape[0] - len(feats):,}   "
          f"cells nulled: {int(trail['cells_nulled'].sum()):,}")
    print("=" * 100)

    _log("Pipeline complete. Next: notebooks/01_sanity.ipynb (the gate).")


def main() -> None:
    p = argparse.ArgumentParser(description="Run the ActionWise ETL pipeline")
    p.add_argument("--source", choices=["eb547"], default="eb547")
    args = p.parse_args()
    if args.source == "eb547":
        run_eb547()


if __name__ == "__main__":
    main()
