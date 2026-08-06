"""Phase 2 gate — run after the pipeline, before trusting anything downstream.

Usage:
    python scripts/run_sanity_gate.py

Exits non-zero if any published figure fails to reproduce, so it can be wired
into CI or a pre-commit hook later.
"""
from __future__ import annotations

import sys

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.sanity import format_gate, run_gate

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"


def main() -> int:
    if not PROCESSED_PATH.exists():
        print(f"{PROCESSED_PATH} not found — run scripts/run_pipeline.py first.")
        return 2

    df = pd.read_parquet(PROCESSED_PATH)
    print(f"Loaded {len(df):,} respondents from {PROCESSED_PATH.name}\n")
    print("=" * 110)
    print("SANITY GATE — our pipeline vs the figures DG ECHO published from this same survey")
    print("=" * 110)

    result = run_gate(df)
    print(format_gate(result))
    print("=" * 110)

    return 0 if bool(result["pass"].all()) else 1


if __name__ == "__main__":
    sys.exit(main())
