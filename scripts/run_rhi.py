"""Phase 4 — RHI: how many days a household could actually cope.

Usage:
    python scripts/run_rhi.py [--skip-model]

Writes rhi_by_country, rhi_bands_eu/lv, rhi_binding_eu/lv and the model summary
to DuckDB, and prints the headline figures.
"""
from __future__ import annotations

import argparse

import pandas as pd

from actionwise.config import DATA_PROCESSED, RESILIENCE_TARGET_DAYS
from actionwise.db.duckdb_client import write_table
from actionwise.indices.rhi import (
    DOMAINS,
    band_distribution,
    binding_domain_profile,
    compute_rhi,
    target_bounds,
)
from actionwise.models.ordinal import fit_horizon_model, summarise_fits
from actionwise.weighting import effective_n, weighted_mean

PROCESSED_PATH = DATA_PROCESSED / "eb547_features.parquet"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%" if pd.notna(v) else "—"


def main(skip_model: bool = False) -> None:
    df = compute_rhi(pd.read_parquet(PROCESSED_PATH))
    lv = df[df["country_grouped"] == "LV"]

    print(f"Loaded {len(df):,} respondents  ·  Latvia n = {len(lv):,}")
    print(f"RHI computable for {int(df['rhi_band'].notna().sum()):,} "
          f"({df['rhi_band'].notna().mean():.0%}); "
          f"{int(df['rhi_partial'].fillna(False).sum()):,} are upper bounds (a domain went unanswered)\n")

    # ── Headline: share below the 72-hour target, as a bracket ─────────────
    print("=" * 96)
    print(f"RESILIENCE HORIZON — share below the {RESILIENCE_TARGET_DAYS:.0f}-day target")
    print("=" * 96)
    print(f"{'':10s} {'certainly below':>18s} {'at most':>12s}   (band 2 = '2-3 days' straddles the target)")
    for name, sub, w in (("EU", df, "w_eu"), ("Latvia", lv, "w_national")):
        b = target_bounds(sub, w)
        print(f"{name:10s} {_pct(b['below_target_certain']):>18s} {_pct(b['below_target_upper']):>12s}")

    # ── Band distribution ───────────────────────────────────────────────────
    for name, sub, w in (("EU", df, "w_eu"), ("LATVIA", lv, "w_national")):
        print("\n" + "=" * 96)
        print(f"{name} — distribution of the weakest lifeline")
        print("=" * 96)
        bands = band_distribution(sub, w)
        print(bands.assign(share=bands["share"].map(_pct)).to_string(index=False))

    # ── Which lifeline binds ────────────────────────────────────────────────
    for name, sub, w in (("EU", df, "w_eu"), ("LATVIA", lv, "w_national")):
        print("\n" + "=" * 96)
        print(f"{name} — which lifeline runs out first")
        print("=" * 96)
        prof = binding_domain_profile(sub, w)
        print(
            prof.assign(
                share_binding=prof["share_binding"].map(_pct),
                pct_one_day_or_less=prof["pct_one_day_or_less"].map(_pct),
            ).to_string(index=False)
        )

    # ── Country ranking ─────────────────────────────────────────────────────
    rows = []
    for iso, sub in df.groupby("country_grouped"):
        b = target_bounds(sub, "w_national")
        rows.append(
            {
                "country": iso,
                "mean_days": weighted_mean(sub, "rhi_days", "w_national"),
                "below_target_certain": b["below_target_certain"],
                "below_target_upper": b["below_target_upper"],
                "n_rows": len(sub),
                "n_eff": round(effective_n(sub, "w_national"), 1),
            }
        )
    ranking = pd.DataFrame(rows).sort_values("below_target_certain", ascending=False).reset_index(drop=True)

    print("\n" + "=" * 96)
    print("COUNTRY RANKING — most exposed first (Latvia marked)")
    print("=" * 96)
    show = ranking.assign(
        mean_days=ranking["mean_days"].map("{:.2f}".format),
        below_target_certain=ranking["below_target_certain"].map(_pct),
        below_target_upper=ranking["below_target_upper"].map(_pct),
        country=ranking["country"].map(lambda c: f"{c}  <--" if c == "LV" else c),
    )
    print(show.to_string(index=False))

    # ── Ordered probit ──────────────────────────────────────────────────────
    fits: list[dict] = []
    if not skip_model:
        print("\n" + "=" * 96)
        print("ORDERED PROBIT — what predicts a short horizon (accuracy always beside its baseline)")
        print("=" * 96)
        for domain in DOMAINS:
            try:
                fits.append(fit_horizon_model(df, domain, weight="w_eu"))
            except Exception as exc:  # noqa: BLE001 — report and continue
                print(f"  {domain}: skipped ({exc})")
        if fits:
            print(summarise_fits(fits).to_string(index=False))
            best = max(fits, key=lambda f: f["lift_over_baseline"])
            print(f"\nStrongest domain: {best['domain']}. Significant predictors:")
            sig = best["coefficients"].query("significant")
            print(sig.to_string() if len(sig) else "  (none at p<0.05)")

    # ── Persist ─────────────────────────────────────────────────────────────
    write_table(ranking, "rhi_by_country")
    write_table(band_distribution(df, "w_eu"), "rhi_bands_eu")
    write_table(band_distribution(lv, "w_national"), "rhi_bands_lv")
    write_table(binding_domain_profile(df, "w_eu"), "rhi_binding_eu")
    write_table(binding_domain_profile(lv, "w_national"), "rhi_binding_lv")
    keep = ["uniqid", "country_grouped", "rhi_band", "rhi_days", "rhi_binding_domain",
            "rhi_n_domains", "rhi_partial", "w_national", "w_eu"]
    write_table(df[[c for c in keep if c in df.columns]], "rhi_respondents")
    if fits:
        write_table(summarise_fits(fits), "rhi_model_summary")
    print("\nWrote rhi_by_country, rhi_bands_*, rhi_binding_*, rhi_respondents to DuckDB.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--skip-model", action="store_true", help="descriptive output only")
    main(**vars(p.parse_args()))
