"""Phase 5 — calibrate the item bank and score PRI.

Usage:
    python scripts/run_irt.py

Writes item_bank, item_fit and pri_respondents to DuckDB.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import DATA_PROCESSED
from actionwise.db.duckdb_client import write_table
from actionwise.models.irt import (
    diagnose_dimensionality,
    face_validity,
    fit_2pl,
    item_fit,
    score_ability,
    theta_to_pri,
)
from actionwise.weighting import weighted_mean

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"


def main() -> None:
    df = pd.read_parquet(PROCESSED_PATH)
    print(f"Loaded {len(df):,} respondents\n")

    # ── Calibrate ───────────────────────────────────────────────────────────
    print("=" * 98)
    print("ITEM BANK — 2PL, calibrated on the pooled EU sample (easiest first)")
    print("=" * 98)
    bank = fit_2pl(df)
    show = bank.assign(
        discrimination=bank["discrimination"].map("{:.3f}".format),
        difficulty=bank["difficulty"].map("{:+.3f}".format),
        p_observed=(bank["p_observed"] * 100).map("{:.1f}%".format),
    )[["label", "difficulty", "discrimination", "p_observed"]]
    print(show.to_string(index=False))
    print(f"\ncalibrated on {int(bank['n_calibration'].iloc[0]):,} complete response patterns")

    # ── Face validity — the check that outranks the diagnostics ─────────────
    print("\n" + "=" * 98)
    print("FACE VALIDITY — does the difficulty ordering match what we already know?")
    print("=" * 98)
    fv = face_validity(bank)
    print(fv.assign(**{"pass": fv["pass"].map({True: "PASS", False: "FAIL"})}).to_string(index=False))
    if not bool(fv["pass"].all()):
        print("\n  ⚠ FACE VALIDITY FAILED — do not use this bank. The numbers may be "
              "internally consistent and still describe something that is not preparedness.")

    # ── Dimensionality — reported, not silently corrected ──────────────────
    print("\n" + "=" * 98)
    print("DIMENSIONALITY — does the battery measure one construct, or two?")
    print("=" * 98)
    dims = diagnose_dimensionality(bank)
    with pd.option_context("display.max_colwidth", 68):
        print(dims.to_string(index=False))
    if dims["n_items"].min() >= 3:
        print("\n  Note: discrimination splits into two clear groups. 2PL assumes a single")
        print("  latent trait, so PRI should be read as dominated by the sharp group.")
        print("  A two-dimensional model is the principled next step — see the model card.")

    # ── Score ───────────────────────────────────────────────────────────────
    theta = score_ability(df, bank)
    df = df.assign(theta_action=theta, pri=theta_to_pri(theta))
    scored = int(df["pri"].notna().sum())
    print("\n" + "=" * 98)
    print("PRI — latent preparedness, rescaled to 0-100")
    print("=" * 98)
    print(f"  scored           : {scored:,} of {len(df):,} ({scored / len(df):.0%})")
    print(f"  EU mean PRI      : {weighted_mean(df, 'pri', 'w_eu'):.1f}")
    lv = df[df["country_grouped"] == "LV"]
    print(f"  Latvia mean PRI  : {weighted_mean(lv, 'pri', 'w_national'):.1f}")
    print(f"  theta range      : {df['theta_action'].min():.2f} to {df['theta_action'].max():.2f}")

    # ── Item fit ────────────────────────────────────────────────────────────
    print("\n" + "=" * 98)
    print("ITEM FIT — infit/outfit mean-square, productive range 0.5-1.5")
    print("=" * 98)
    fit = item_fit(df, bank, theta)
    fit_show = fit.merge(bank[["item", "label"]], on="item")
    print(
        fit_show.assign(
            infit=fit_show["infit"].map("{:.3f}".format),
            outfit=fit_show["outfit"].map("{:.3f}".format),
            misfitting=fit_show["misfitting"].map({True: "  <-- MISFIT", False: ""}),
        )[["label", "infit", "outfit", "misfitting"]].to_string(index=False)
    )
    n_bad = int(fit["misfitting"].sum())
    print(f"\n  {n_bad} of {len(fit)} items outside the productive range")

    # ── Country ranking on PRI ──────────────────────────────────────────────
    rows = [
        {"country": iso, "mean_pri": weighted_mean(sub, "pri", "w_national"), "n": len(sub)}
        for iso, sub in df.groupby("country_grouped")
    ]
    ranking = pd.DataFrame(rows).sort_values("mean_pri", ascending=False).reset_index(drop=True)
    print("\n" + "=" * 98)
    print("MEAN PRI BY COUNTRY (Latvia marked)")
    print("=" * 98)
    print(
        ranking.assign(
            mean_pri=ranking["mean_pri"].map("{:.1f}".format),
            country=ranking["country"].map(lambda c: f"{c}  <--" if c == "LV" else c),
        ).to_string(index=False)
    )

    # ── Persist ─────────────────────────────────────────────────────────────
    write_table(bank, "item_bank")
    write_table(fit, "item_fit")
    write_table(fv, "item_face_validity")
    write_table(dims, "item_dimensionality")
    write_table(ranking, "pri_by_country")
    write_table(
        df[["uniqid", "country_grouped", "theta_action", "pri", "w_national", "w_eu"]],
        "pri_respondents",
    )
    print("\nWrote item_bank, item_fit, item_face_validity, pri_by_country, pri_respondents.")


if __name__ == "__main__":
    main()
