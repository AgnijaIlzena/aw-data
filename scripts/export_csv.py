"""Export the survey to CSV — for inspection, and for anyone without SPSS.

Usage:
    python scripts/export_csv.py

The `.sav` stays the source of record: it is the citable artefact (DOI
`10.4232/1.14461`) and it carries the label dictionary that CSV cannot hold. But
"binary" makes the data sound harder to reach than it is, so this writes plain
CSVs that open in Excel, LibreOffice or a text editor.

Three files, because they answer three different questions:

  1. `eb547_raw_full.csv`      all 26,405 x 668 exactly as stored — the archive copy
  2. `eb547_labelled.csv`      the 47 variables the project uses, with every code
                               REPLACED BY ITS MEANING — the one a human reads
  3. `eb547_analysis.csv`      the cleaned analysis table the indices actually run on

File 2 is the interesting one: `qc7_1 = 2` becomes `"2 - 3 days"`. That is the
label dictionary written out in full, which is precisely what is lost if someone
converts the .sav to CSV naively and then wonders why every answer is a number.
"""
from __future__ import annotations

import sys

import pandas as pd

from actionwise import config
from actionwise.data.loader import load_za8841, value_labels_for

EXPORTS = config.ROOT / "data" / "exports"

PROJECT_VARS = (
    config.ID_VARS
    + [config.WEIGHT_NATIONAL, config.WEIGHT_EU]
    + list(config.DEMOGRAPHIC_ITEMS)
    + list(config.QC7_DOMAINS)
    + list(config.QC6_ITEMS) + [config.QC6_OTHER, config.QC6_DK, config.QC6_TOTAL]
    + list(config.QC5_ITEMS)
    + list(config.QC8_ITEMS)
)


def size_of(path) -> str:
    mb = path.stat().st_size / 1e6
    return f"{mb:,.1f} MB" if mb >= 1 else f"{path.stat().st_size / 1e3:,.0f} KB"


def main() -> int:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    raw, meta = load_za8841()

    # ── 1. the archive copy, exactly as stored ─────────────────────────────
    full = EXPORTS / "eb547_raw_full.csv"
    raw.to_csv(full, index=False, encoding="utf-8")
    print(f"  {full.name:26} {raw.shape[0]:,} x {raw.shape[1]:<5} {size_of(full)}")
    print("     every value as stored — numeric codes, no labels")

    # ── 2. the readable one: codes replaced by their meaning ───────────────
    columns = [c for c in PROJECT_VARS if c in raw.columns]
    labelled = raw[columns].copy()
    replaced = 0
    for name in columns:
        labels = value_labels_for(meta, name)
        if not labels:
            continue
        labelled[name] = raw[name].map(labels).fillna(raw[name])
        replaced += 1

    # Human-readable headers, e.g. qc7_1 -> "qc7_1 — HOW MANY DAYS MEET WATER NEEDS…"
    labelled.columns = [
        f"{c} — {meta.column_names_to_labels.get(c, '')}".strip(" —")
        for c in labelled.columns
    ]
    readable = EXPORTS / "eb547_labelled.csv"
    labelled.to_csv(readable, index=False, encoding="utf-8-sig")   # BOM: Excel + accents
    print(f"  {readable.name:26} {labelled.shape[0]:,} x {labelled.shape[1]:<5} "
          f"{size_of(readable)}")
    print(f"     {replaced} of {len(columns)} columns decoded to text; headers carry "
          "the full question")

    # ── 3. what the analysis actually runs on ──────────────────────────────
    processed = config.DATA_PROCESSED / "eb547_features.parquet"
    if processed.exists():
        features = pd.read_parquet(processed)
        analysis = EXPORTS / "eb547_analysis.csv"
        features.to_csv(analysis, index=False, encoding="utf-8")
        print(f"  {analysis.name:26} {features.shape[0]:,} x {features.shape[1]:<5} "
              f"{size_of(analysis)}")
        print("     the cleaned table: readable names, scales reversed, off-scale "
              "codes nulled")
    else:
        print("  (run scripts/run_pipeline.py first for eb547_analysis.csv)")

    print(f"\nWritten to {EXPORTS.relative_to(config.ROOT)}/")
    print("The .sav remains the source of record — CSV cannot carry the label "
          "dictionary,\nwhich is why file 2 exists and why docs/CODEBOOK-EB547.md is "
          "generated from the .sav.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
