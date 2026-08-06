"""Phase 6 — what predicts the knowing-doing gap: capability or information?

Usage:
    python scripts/run_gap_drivers.py

Writes gap_variance_audit, gap_model_comparison and gap_shap to DuckDB.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.data.cleaner_eb547 import variance_audit
from actionwise.db.duckdb_client import write_table
from actionwise.indices.pgi import person_pgi
from actionwise.models.gbm import (
    BARRIER_FEATURES,
    CONTEXT_FEATURES,
    DEMOGRAPHIC_FEATURES,
    INFO_FEATURES,
    compare_to_baselines,
    fit_gap_model,
    shap_importance,
)

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    df = df.assign(pgi=person_pgi(df))
    scored = int(df["pgi"].notna().sum())
    print(f"Loaded {len(df):,} respondents · PGI measurable for {scored:,}\n")

    candidates = [
        f for f in BARRIER_FEATURES + INFO_FEATURES + CONTEXT_FEATURES + DEMOGRAPHIC_FEATURES
        if f in df.columns
    ]

    # ── Variance audit — before any fit, per the guardrail ──────────────────
    print("=" * 100)
    print("VARIANCE AUDIT — features with too little variation are dropped and logged")
    print("=" * 100)
    audit = variance_audit(df[df["pgi"].notna()], candidates)
    print(audit.to_string(index=False))
    dropped = audit.loc[audit["drop"], "column"].tolist()
    features = [f for f in candidates if f not in dropped]
    print(f"\n  dropped {len(dropped)}: {dropped or 'none'}")
    print(f"  kept {len(features)} features")

    # ── Model vs baselines ─────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("MODEL vs BASELINES — grouped 5-fold CV by country (out-of-fold scores)")
    print("=" * 100)
    comparison = compare_to_baselines(df, features)
    print(comparison.to_string(index=False))

    full = comparison.query("model == 'full model'").iloc[0]
    demo = comparison.query("model == 'demographics only'").iloc[0]
    print(f"\n  full model explains {full['r2_oof']:.1%} of gap variance out-of-fold")
    print(f"  demographics alone : {demo['r2_oof']:.1%}")
    if full["r2_oof"] <= demo["r2_oof"]:
        print("  ⚠ the attitude features add nothing over demographics — report that plainly")

    # ── SHAP ───────────────────────────────────────────────────────────────
    fit = fit_gap_model(df, features)
    shap_tbl = shap_importance(fit)
    print("\n" + "=" * 100)
    print("SHAP — what moves the gap (positive mean_shap = pushes the gap UP)")
    print("=" * 100)
    print(
        shap_tbl.assign(
            mean_abs_shap=shap_tbl["mean_abs_shap"].map("{:.4f}".format),
            mean_shap=shap_tbl["mean_shap"].map("{:+.4f}".format),
        ).head(15).to_string(index=False)
    )

    # ── The question the phase exists to answer ────────────────────────────
    print("\n" + "=" * 100)
    print("CAPABILITY vs INFORMATION")
    print("=" * 100)
    idx = shap_tbl.set_index("feature")
    for label, feat in (
        ("capability barrier  (no time / money)", "prep_no_time_or_money"),
        ("information barrier (needs more info)", "prep_needs_more_info"),
    ):
        if feat in idx.index:
            row = idx.loc[feat]
            rank = int(shap_tbl.index[shap_tbl["feature"] == feat][0]) + 1
            print(f"  {label}: |SHAP| {row['mean_abs_shap']:.4f}  (rank {rank} of {len(shap_tbl)})")

    # ── Direction, read off the data rather than off mean SHAP ─────────────
    # Signed mean SHAP is near zero by construction (contributions sum out), so
    # it says little about direction. Mean PGI by response level says it plainly.
    print("\n" + "=" * 100)
    print("DIRECTION — mean gap by how strongly the barrier is endorsed")
    print("       (scales reversed in cleaning: 4 = totally agree, 1 = totally disagree)")
    print("=" * 100)
    direction_rows = []
    for label, feat in (
        ("capability  (no time / money)", "prep_no_time_or_money"),
        ("information (needs more info)", "prep_needs_more_info"),
    ):
        sub = df[df["pgi"].notna() & df[feat].notna()]
        by_level = sub.groupby(feat)["pgi"].agg(["mean", "size"])
        spread = float(by_level["mean"].iloc[-1] - by_level["mean"].iloc[0])
        levels = "  ".join(
            f"{int(lv)}:{row['mean']:.3f}(n={int(row['size']):,})" for lv, row in by_level.iterrows()
        )
        print(f"  {label}\n    {levels}\n    agree - disagree = {spread:+.3f}")
        direction_rows.append({"barrier": label, "feature": feat, "spread_agree_minus_disagree": spread})
    write_table(pd.DataFrame(direction_rows), "gap_barrier_direction")

    write_table(audit, "gap_variance_audit")
    write_table(comparison, "gap_model_comparison")
    write_table(shap_tbl, "gap_shap")
    print("\nWrote gap_variance_audit, gap_model_comparison, gap_shap to DuckDB.")


if __name__ == "__main__":
    main()
