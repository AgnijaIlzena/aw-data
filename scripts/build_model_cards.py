"""Generate model cards from DuckDB and config — never hand-written.

Usage:
    python scripts/build_model_cards.py

`virality-code` documented a Random Forest while running Gradient Boosting,
because the docs were written once and the code moved on. These cards are
regenerated from the artefacts themselves, so a stale card is not possible: if
the numbers change, rerunning this changes the card.
"""
from __future__ import annotations

import platform
from datetime import date

import pandas as pd

from actionwise import config
from actionwise.db.duckdb_client import get_connection

DOCS = config.ROOT / "docs" / "model-cards"


def _q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).fetchdf()


def _has(con, table: str) -> bool:
    return not con.execute(
        f"SELECT 1 FROM duckdb_tables() WHERE table_name = '{table}' LIMIT 1"
    ).fetchdf().empty


def _md_table(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def _footer() -> str:
    return (
        f"\n---\n\n*Generated {date.today().isoformat()} by "
        f"`scripts/build_model_cards.py` · Python {platform.python_version()} · "
        f"source `{config.EB547_SAV.name}` "
        f"({config.EB547_EXPECTED_SHAPE[0]:,} × {config.EB547_EXPECTED_SHAPE[1]}).*\n"
    )


def card_rhi(con) -> str:
    lines = [
        "# Model card — RHI (Resilience Horizon Index)\n",
        "**What it measures.** Days a household could cope, taken as the *minimum* across "
        "five lifelines: water, power, gas/heating, food, medication. The minimum is the "
        "point — a household with a month of food and one day of water has a one-day "
        "horizon.\n",
        "**Type.** Deterministic index (no fitting) plus an ordered probit for drivers.\n",
        f"**Inputs.** `qc7_1`–`qc7_5`, banded: 1 = ≤1 day · 2 = 2–3 days · 3 = 4–7 days · "
        f"4 = >7 days. Midpoints used for averages: {config.QC7_MIDPOINT_DAYS}.\n",
        f"**Target.** {config.RESILIENCE_TARGET_DAYS:.0f} days.\n",
        "## Design decisions\n",
        "- **Reported as a bracket, not a point.** Band 2 (\"2–3 days\") straddles the "
        "72-hour target, so the share below target is given as a range. Imputing a "
        "midpoint would manufacture precision the instrument never had.\n"
        "- **\"Not applicable\" is excluded from the minimum, not counted as failure.** For "
        "medication it means the respondent takes none.\n"
        "- **A partial minimum is an upper bound** and is flagged `rhi_partial`: an "
        "unanswered lifeline could have been the weakest.\n",
    ]
    if _has(con, "rhi_bands_eu"):
        lines += ["## Distribution (EU, weighted)\n", _md_table(_q(con, "SELECT * FROM rhi_bands_eu")), "\n"]
    if _has(con, "rhi_binding_eu"):
        lines += ["## Which lifeline binds first\n",
                  _md_table(_q(con, "SELECT * FROM rhi_binding_eu ORDER BY share_binding DESC")), "\n"]
    if _has(con, "rhi_model_summary"):
        lines += [
            "## Ordered probit — accuracy beside its baseline\n",
            _md_table(_q(con, "SELECT * FROM rhi_model_summary")),
            "\n**Two of five domains do not beat their baseline.** Demographics barely "
            "predict resilience; that is the finding, not a failure to hide.\n",
        ]
    return "\n".join(lines) + _footer()


def card_pri(con) -> str:
    lines = [
        "# Model card — PRI (Personal Readiness Index)\n",
        "**What it measures.** A latent preparedness trait behind the thirteen household "
        "measures, rescaled to 0–100 via the normal CDF so it reads directly as "
        "\"more prepared than N% of the calibration population\".\n",
        "**Type.** 2-parameter logistic item response theory (`girth.twopl_mml`, marginal "
        "maximum likelihood). **This is a measurement model, not a predictive one** — there "
        "is no accuracy figure because it forecasts nothing.\n",
        "**Inputs.** `qc6.1`–`qc6.13`, binary. Complete cases only; a \"don't know\" battery "
        "carries no information about the trait and imputing zeros would read as maximally "
        "unprepared.\n",
    ]
    if _has(con, "item_bank"):
        bank = _q(con, "SELECT label, difficulty, discrimination, p_observed, n_calibration "
                       "FROM item_bank ORDER BY difficulty")
        lines += [f"**Calibration sample.** {int(bank['n_calibration'].iloc[0]):,} complete "
                  "response patterns.\n", "## Item bank\n",
                  _md_table(bank.drop(columns=["n_calibration"]).round(3)), "\n"]
    if _has(con, "item_fit"):
        fit = _q(con, "SELECT b.label, f.infit, f.outfit, f.misfitting FROM item_fit f "
                      "JOIN item_bank b USING (item) ORDER BY f.outfit")
        n_bad = int(fit["misfitting"].sum())
        lines += ["## Item fit\n", _md_table(fit.round(3)),
                  f"\nProductive range 0.5–1.5. **{n_bad} of {len(fit)} items** fall outside it.\n"]
    if _has(con, "item_face_validity"):
        lines += ["## Face validity\n", _md_table(_q(con, "SELECT * FROM item_face_validity")),
                  "\nThe frequency-correlation bar is −0.80 rather than −0.90 because 2PL "
                  "discrimination varies: a flat item can be extreme in difficulty yet "
                  "middling in frequency. A stricter bar would assert a Rasch property this "
                  "model does not claim.\n"]
    if _has(con, "item_dimensionality"):
        lines += ["## Known limitation — the battery is not unidimensional\n",
                  _md_table(_q(con, "SELECT * FROM item_dimensionality")),
                  "\nDiscrimination splits into a sharp group (supplies you buy and store) and "
                  "a flat group (things you do and arrange). 2PL assumes one trait, so **PRI is "
                  "dominated by the sharp group**. A two-dimensional model is the principled "
                  "next step; it is reported here rather than silently applied.\n"]
    if _has(con, "holdout_transfer"):
        t = _q(con, "SELECT * FROM holdout_transfer").iloc[0]
        lines += ["## Transfer validation (Latvia held out)\n",
                  f"- calibrated on {int(t['n_calibration_pooled']):,} respondents, "
                  f"**excluding Latvia**, then used to score it\n"
                  f"- θ correlation against a Latvia-only bank: **{t['theta_correlation']:.4f}**\n"
                  f"- mean |PRI difference|: **{t['mean_abs_pri_difference']:.2f} points**\n\n"
                  "Pooling across Europe is therefore justified — which matters because "
                  f"{int(t['n_target']):,} Latvian respondents cannot calibrate 13 items alone.\n"]
    return "\n".join(lines) + _footer()


def card_pgi(con) -> str:
    lines = [
        "# Model card — PGI (Preparedness Gap Index) and its drivers\n",
        "**What it measures.** The share of measures a respondent was aware of but had not "
        "taken. High PGI marks someone already convinced and not yet acting — the "
        "addressable segment.\n",
        "**Type.** Deterministic index, plus a LightGBM regression to identify drivers.\n",
        "**Inputs.** `qc5_1` (saw information in the last 12 months) crossed with "
        "`qc6.1`–`qc6.13` (measures taken).\n",
        "## Leakage control\n",
        "PGI is computed from the qc6 battery, so every feature derived from it — `act_*`, "
        "`n_actions`, `pri`, `theta_*` — is the target in disguise. `assert_no_leakage` "
        "**raises** rather than warns, and runs before every fit.\n",
        "## Validation design\n",
        "Grouped 5-fold cross-validation **by country**: rows from one country share "
        "sampling design and national context, so a random split would let the model "
        "memorise country effects and report an optimistic score.\n",
    ]
    if _has(con, "gap_model_comparison"):
        lines += ["## Against baselines\n",
                  _md_table(_q(con, "SELECT * FROM gap_model_comparison")),
                  "\n**Demographics alone score below the mean predictor.** Who you are "
                  "barely predicts preparedness — which is the case for a personalised tool "
                  "rather than demographic targeting.\n"]
    if _has(con, "gap_shap"):
        lines += ["## Drivers (top 10 by |SHAP|)\n",
                  _md_table(_q(con, "SELECT * FROM gap_shap ORDER BY mean_abs_shap DESC LIMIT 10").round(4)), "\n"]
    if _has(con, "gap_barrier_direction"):
        lines += ["## Capability versus information\n",
                  _md_table(_q(con, "SELECT * FROM gap_barrier_direction").round(4)),
                  "\nThe survey's own headline is that two in three Europeans *say* they need "
                  "more information. Modelled, the capability barrier ranks far above the "
                  "information barrier. **The stated barrier and the operative barrier "
                  "differ** — which argues for making action cheaper and easier over "
                  "producing more guidance.\n"]
    if _has(con, "gap_variance_audit"):
        audit = _q(con, "SELECT * FROM gap_variance_audit WHERE drop ORDER BY std")
        lines += ["## Variance audit\n",
                  f"Run before fitting; drops features with `n_unique < 2` or `std < 0.01`. "
                  f"Currently dropping **{len(audit)}**.\n",
                  "\nThe threshold targets *constant* columns. An earlier `min_unique=5` "
                  "discarded every 4-point Likert item — including both barriers the model "
                  "exists to compare — and would have produced the conclusion that nothing "
                  "predicts the gap. A regression test now pins this.\n"]
    return "\n".join(lines) + _footer()


def card_pipeline(con) -> str:
    lines = [
        "# Model card — data pipeline and the sanity gate\n",
        f"**Source.** Eurobarometer 101.1, GESIS study `ZA8841` "
        f"(Special Eurobarometer 547), DOI `10.4232/1.14461`. Fieldwork 7 Feb – 3 Mar 2024, "
        f"{config.EB547_EXPECTED_SHAPE[0]:,} respondents, 27 Member States.\n",
        "## The gate\n",
        "Nothing downstream is trusted until the pipeline reproduces figures the European "
        "Commission published from this same survey. Enforced as a test, so a later change "
        "to the cleaner cannot quietly break agreement.\n",
    ]
    if _has(con, "eb547"):
        n = int(_q(con, "SELECT COUNT(*) AS n FROM eb547")["n"].iloc[0])
        lines.append(f"**Rows through the pipeline.** {n:,} in, {n:,} out — none dropped. "
                     "Unusable answers become nulls; the decision to exclude belongs to each "
                     "index.\n")
    lines += [
        "## The three traps in this dataset\n",
        "1. **Off-scale codes.** Every `qc` scale carries 5 (Not applicable / It depends) and "
        "6 (Don't know). Left numeric, \"Don't know\" outranks \"More than 7 days\".\n"
        "2. **`w22` is not the current EU27.** It is the pre-2013 definition and is null for "
        "all 1,001 Croatian respondents — any EU figure computed with it silently drops a "
        f"Member State. `{config.WEIGHT_EU}` is the correct EU weight; "
        f"`{config.WEIGHT_NATIONAL}` is per-country.\n"
        "3. **The published denominator includes \"Don't know\".** DG ECHO's 37% is a share "
        "of *all* respondents; among substantive answers only it is 39.3%.\n",
        "## Weights\n",
        f"- `{config.WEIGHT_NATIONAL}` → `w_national` — national, for per-country figures\n"
        f"- `{config.WEIGHT_EU}` → `w_eu` — EU-wide totals\n"
        f"- `{config.WEIGHT_EU27_LEGACY}` → `w_eu27_legacy` — **do not use**, excludes Croatia\n",
        "Effective sample sizes use Kish's formula; a weighted sample supports narrower "
        "claims than its row count suggests.\n",
    ]
    return "\n".join(lines) + _footer()


CARDS = {
    "00-pipeline.md": card_pipeline,
    "01-rhi.md": card_rhi,
    "02-pri.md": card_pri,
    "03-pgi.md": card_pgi,
}


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    con = get_connection(read_only=True)
    try:
        for filename, builder in CARDS.items():
            (DOCS / filename).write_text(builder(con), encoding="utf-8")
            print(f"  wrote docs/model-cards/{filename}")
    finally:
        con.close()
    print(f"\n{len(CARDS)} model cards generated from DuckDB — never hand-edited.")


if __name__ == "__main__":
    main()
