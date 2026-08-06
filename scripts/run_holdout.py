"""Phase 7 — hold Latvia out, then build the percentile tables the product shows.

Usage:
    python scripts/run_holdout.py

Writes holdout_transfer, holdout_difficulty_compare, pri_percentiles_lv and
pri_percentiles_eu to DuckDB.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.db.duckdb_client import write_table
from actionwise.indices.percentiles import benchmark, percentile_table
from actionwise.models.irt import fit_2pl, holdout_transfer, score_ability, theta_to_pri

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"
TARGET = "LV"


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    print(f"Loaded {len(df):,} respondents\n")

    # ── Transfer test ───────────────────────────────────────────────────────
    print("=" * 100)
    print(f"HOLD-OUT TRANSFER — calibrate on EU without {TARGET}, then score {TARGET}")
    print("=" * 100)
    t = holdout_transfer(df, TARGET)

    print(f"  target rows                : {t['n_target']:,}")
    print(f"  pooled calibration sample  : {t['n_calibration_pooled']:,} (EU excluding {TARGET})")
    print(f"  native calibration sample  : {t['n_calibration_native']:,} ({TARGET} only)")
    print()
    print(f"  theta correlation          : {t['theta_correlation']:.4f}")
    print(f"  theta rank correlation     : {t['theta_rank_correlation']:.4f}")
    print(f"  item difficulty correlation: {t['difficulty_correlation']:.4f}")
    print(f"  mean |PRI difference|      : {t['mean_abs_pri_difference']:.2f} points (0-100 scale)")

    if t["theta_correlation"] > 0.95:
        print("\n  Pooling is safe: a bank calibrated without Latvia ranks Latvians")
        print("  essentially as their own bank would.")
    else:
        print("\n  ⚠ Pooled and native scores diverge — the items do not behave the same")
        print("  way in Latvia, and the pooled bank should not be used there unexamined.")

    compare = (
        t["pooled_bank"][["item", "label", "difficulty"]]
        .rename(columns={"difficulty": "b_pooled"})
        .merge(
            t["native_bank"][["item", "difficulty"]].rename(columns={"difficulty": "b_native"}),
            on="item",
        )
        .assign(delta=lambda d: d["b_native"] - d["b_pooled"])
        .sort_values("delta")
    )
    print("\n  Item difficulty, pooled vs Latvia-native (negative = easier in Latvia):")
    print(
        compare.assign(
            b_pooled=compare["b_pooled"].map("{:+.2f}".format),
            b_native=compare["b_native"].map("{:+.2f}".format),
            delta=compare["delta"].map("{:+.2f}".format),
        )[["label", "b_pooled", "b_native", "delta"]].to_string(index=False)
    )

    # ── Score everyone on the pooled-minus-Latvia bank ─────────────────────
    bank = fit_2pl(df[df["country_grouped"] != TARGET])
    theta = score_ability(df, bank)
    df = df.assign(theta_holdout=theta, pri_holdout=theta_to_pri(theta))

    # ── Percentile tables ───────────────────────────────────────────────────
    lv = df[df["country_grouped"] == TARGET]
    print("\n" + "=" * 100)
    print(f"PRI PERCENTILES — {TARGET}, by age band (weighted; thin cells flagged)")
    print("=" * 100)
    lv_pct = percentile_table(lv, "pri_holdout", "age_band", "w_national")
    print(lv_pct.to_string(index=False))

    print("\n" + "=" * 100)
    print("PRI PERCENTILES — EU, by age band")
    print("=" * 100)
    eu_pct = percentile_table(df, "pri_holdout", "age_band", "w_eu")
    print(eu_pct.to_string(index=False))

    # ── The product sentence ────────────────────────────────────────────────
    print("\n" + "=" * 100)
    print("BENCHMARK — the line the product renders")
    print("=" * 100)
    for score in (25.0, 50.0, 75.0):
        b = benchmark(score, lv, "pri_holdout", "w_national")
        print(f"  PRI {score:5.1f}  ->  {b['sentence']} (Latvia, n={b['n_reference']:,})")

    thin = int(lv_pct["thin_cell"].sum())
    if thin:
        print(f"\n  {thin} Latvian age band(s) fall below the reliability threshold — "
              "show the national figure there rather than the band.")

    write_table(
        pd.DataFrame([{k: v for k, v in t.items() if not isinstance(v, pd.DataFrame)}]),
        "holdout_transfer",
    )
    write_table(compare, "holdout_difficulty_compare")
    write_table(lv_pct, "pri_percentiles_lv")
    write_table(eu_pct, "pri_percentiles_eu")
    print("\nWrote holdout_transfer, holdout_difficulty_compare, pri_percentiles_lv/eu.")


if __name__ == "__main__":
    main()
