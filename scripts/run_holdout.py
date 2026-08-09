"""Phase 7 — hold each focus country out, then build the percentile tables.

Usage:
    python scripts/run_holdout.py

Runs once per country in `config.FOCUS_COUNTRIES`, writing holdout_transfer,
holdout_difficulty_compare and pri_percentiles_<iso> for each, plus
pri_percentiles_eu once.

The transfer test is the one that licenses the whole design. Each country
contributes ~1,000 respondents — too few to calibrate 13 items stably alone — so
the item bank is pooled across Europe. That is only legitimate if the pooled
parameters actually transfer, which is what this measures, per country, and
reports whether it passes or fails.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import COUNTRY_NAMES, DATA_PROCESSED, FOCUS_COUNTRIES, country_suffix
from actionwise.db.duckdb_client import write_table
from actionwise.indices.percentiles import benchmark, percentile_table
from actionwise.models.irt import fit_2pl, holdout_transfer, score_ability, theta_to_pri

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"

# Above this, a bank calibrated elsewhere ranks people essentially as their own
# bank would. Below it, the items behave differently and pooling is unsafe.
TRANSFER_THRESHOLD = 0.95


def run_country(df: pd.DataFrame, target: str) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Transfer test, difficulty comparison and percentile table for one country."""
    name = COUNTRY_NAMES.get(target, target)

    print("\n" + "=" * 100)
    print(f"HOLD-OUT TRANSFER — calibrate on EU without {target}, then score {target}")
    print("=" * 100)
    t = holdout_transfer(df, target)

    print(f"  target rows                : {t['n_target']:,}")
    print(f"  pooled calibration sample  : {t['n_calibration_pooled']:,} (EU excluding {target})")
    print(f"  native calibration sample  : {t['n_calibration_native']:,} ({target} only)")
    print()
    print(f"  theta correlation          : {t['theta_correlation']:.4f}")
    print(f"  theta rank correlation     : {t['theta_rank_correlation']:.4f}")
    print(f"  item difficulty correlation: {t['difficulty_correlation']:.4f}")
    print(f"  mean |PRI difference|      : {t['mean_abs_pri_difference']:.2f} points (0-100 scale)")

    if t["theta_correlation"] > TRANSFER_THRESHOLD:
        print(f"\n  Pooling is safe: a bank calibrated without {name} ranks its")
        print(f"  respondents essentially as their own bank would.")
    else:
        print("\n  ⚠ Pooled and native scores diverge — the items do not behave the same")
        print(f"  way in {name}, and the pooled bank should not be used there unexamined.")

    compare = (
        t["pooled_bank"][["item", "label", "difficulty"]]
        .rename(columns={"difficulty": "b_pooled"})
        .merge(
            t["native_bank"][["item", "difficulty"]].rename(columns={"difficulty": "b_native"}),
            on="item",
        )
        .assign(delta=lambda d: d["b_native"] - d["b_pooled"], country=target)
        .sort_values("delta")
    )
    print(f"\n  Item difficulty, pooled vs {name}-native (negative = easier in {name}):")
    print(
        compare.assign(
            b_pooled=compare["b_pooled"].map("{:+.2f}".format),
            b_native=compare["b_native"].map("{:+.2f}".format),
            delta=compare["delta"].map("{:+.2f}".format),
        )[["label", "b_pooled", "b_native", "delta"]].to_string(index=False)
    )

    # Score this country on a bank that never saw it.
    bank = fit_2pl(df[df["country_grouped"] != target])
    scored = df.assign(pri_holdout=theta_to_pri(score_ability(df, bank)))
    subset = scored[scored["country_grouped"] == target]

    print("\n" + "=" * 100)
    print(f"PRI PERCENTILES — {name}, by age band (weighted; thin cells flagged)")
    print("=" * 100)
    table = percentile_table(subset, "pri_holdout", "age_band", "w_national")
    print(table.to_string(index=False))

    print(f"\n  Benchmark sentences the product renders ({name}):")
    for score in (25.0, 50.0, 75.0):
        b = benchmark(score, subset, "pri_holdout", "w_national")
        print(f"    PRI {score:5.1f}  ->  {b['sentence']} (n={b['n_reference']:,})")

    thin = int(table["thin_cell"].sum())
    if thin:
        print(f"\n  {thin} {name} age band(s) fall below the reliability threshold — "
              "show the national figure there rather than the band.")

    summary = {k: v for k, v in t.items() if not isinstance(v, pd.DataFrame)}
    summary["passes_transfer"] = bool(t["theta_correlation"] > TRANSFER_THRESHOLD)
    return summary, compare, table.assign(country=target)


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    print(f"Loaded {len(df):,} respondents")
    print(f"Focus countries: {', '.join(f'{c} ({COUNTRY_NAMES.get(c, c)})' for c in FOCUS_COUNTRIES)}")

    summaries, comparisons = [], []
    for target in FOCUS_COUNTRIES:
        summary, compare, table = run_country(df, target)
        summaries.append(summary)
        comparisons.append(compare)
        write_table(table, f"pri_percentiles_{country_suffix(target)}")

    # EU reference, scored on the full pooled bank — the denominator for
    # "better prepared than X% of Europeans".
    eu_bank = fit_2pl(df)
    eu_scored = df.assign(pri_holdout=theta_to_pri(score_ability(df, eu_bank)))
    eu_pct = percentile_table(eu_scored, "pri_holdout", "age_band", "w_eu")
    print("\n" + "=" * 100)
    print("PRI PERCENTILES — EU, by age band")
    print("=" * 100)
    print(eu_pct.to_string(index=False))

    transfer = pd.DataFrame(summaries)
    print("\n" + "=" * 100)
    print("TRANSFER TEST — every focus country beside the same threshold")
    print("=" * 100)
    print(transfer[["country", "n_target", "theta_correlation", "theta_rank_correlation",
                    "difficulty_correlation", "mean_abs_pri_difference",
                    "passes_transfer"]].round(4).to_string(index=False))

    write_table(transfer, "holdout_transfer")
    write_table(pd.concat(comparisons, ignore_index=True), "holdout_difficulty_compare")
    write_table(eu_pct, "pri_percentiles_eu")
    suffixes = "/".join(country_suffix(c) for c in FOCUS_COUNTRIES)
    print(f"\nWrote holdout_transfer, holdout_difficulty_compare, "
          f"pri_percentiles_{suffixes}/eu.")


if __name__ == "__main__":
    main()
