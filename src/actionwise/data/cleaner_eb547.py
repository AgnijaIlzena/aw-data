"""Clean Eurobarometer ZA8841 → analysis-ready table.

Pure transforms: nothing here reads or writes files. `scripts/run_pipeline.py`
owns the I/O and prints the audit trail these functions produce.

Every step returns an audit row (step, rows_in, rows_out, cells_nulled, reason)
because the failure that ruined `virality-code` was 807,013 rows silently nulled
by an uncommented filter. Here, nothing is dropped or nulled without saying so.

Steps
-----
1. Select the working columns and give them readable names.
2. Null the off-scale codes 5/6 on the qc7 horizon scales, keeping a flag that
   distinguishes "does not apply to me" from "don't know".
3. Null off-scale codes on the qc5/qc8 agreement scales, then REVERSE them, so
   that higher means more agreement (the raw file runs the other way).
4. Null the 13 preparedness actions for respondents who answered "don't know"
   to the whole battery — they are unanswered, not zero.
5. Validate our derived action count against the survey's own `qc6t`.
6. Recode demographics.
7. Attach the survey weights and check they are usable.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import (
    CONTEXT_ITEMS,
    DEMOGRAPHIC_ITEMS,
    ID_VARS,
    QC5_ITEMS,
    QC6_DK,
    QC6_ITEMS,
    QC6_OTHER,
    QC6_TOTAL,
    QC6_TOTAL_TOP_BAND,
    QC7_DOMAINS,
    QC8_ITEMS,
    QC_AGREE_MAX,
    QC_OFF_SCALE_CODES,
    WEIGHT_EU,
    WEIGHT_EU27_LEGACY,
    WEIGHT_NATIONAL,
)

# Codes 5 and 6 mean different things and must not be conflated:
#   5 = "Not applicable" / "It depends"  (SPONTANEOUS) — the question does not bind
#   6 = "Don't know"                     (SPONTANEOUS) — the respondent has no answer
CODE_NOT_APPLICABLE = 5
CODE_DONT_KNOW = 6


class Audit:
    """Collects one row per cleaning step so the pipeline can print a trail."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def record(self, step: str, rows_in: int, rows_out: int, cells_nulled: int, reason: str) -> None:
        self.rows.append(
            {
                "step": step,
                "rows_in": rows_in,
                "rows_out": rows_out,
                "rows_lost": rows_in - rows_out,
                "cells_nulled": cells_nulled,
                "reason": reason,
            }
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def clean_eb547(raw: pd.DataFrame, audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Apply all cleaning steps to the raw ZA8841 DataFrame.

    Returns the cleaned frame and the audit trail. No rows are ever dropped:
    unusable answers become nulls so that downstream code decides, per index,
    whether a respondent still contributes.
    """
    audit = audit or Audit()
    n0 = len(raw)

    # ── 1. Select and rename ────────────────────────────────────────────────
    #  keeps 53 of 668 columns, gives them readable names
    keep = (
        [c for c in ID_VARS if c in raw.columns]
        + [WEIGHT_NATIONAL, WEIGHT_EU, WEIGHT_EU27_LEGACY]
        + list(QC6_ITEMS) + [QC6_OTHER, QC6_DK, QC6_TOTAL]
        + list(QC7_DOMAINS)
        + list(QC5_ITEMS)
        + list(QC8_ITEMS)
        + [c for c in CONTEXT_ITEMS if c in raw.columns]
        + [c for c in DEMOGRAPHIC_ITEMS if c in raw.columns]
    )
    missing = [c for c in keep if c not in raw.columns]
    if missing:
        raise KeyError(f"expected columns absent from the source file: {missing}")

    out = raw[keep].copy()
    rename = (
        {k: f"act_{v}" for k, v in QC6_ITEMS.items()}
        | {k: f"days_{v}" for k, v in QC7_DOMAINS.items()}
        | {k: f"info_{v}" for k, v in QC5_ITEMS.items()}
        | {k: f"prep_{v}" for k, v in QC8_ITEMS.items()}
        | dict(CONTEXT_ITEMS)
        | dict(DEMOGRAPHIC_ITEMS)
        | {QC6_OTHER: "act_other", QC6_DK: "actions_dk", QC6_TOTAL: "n_actions_survey_banded"}
    )
    out = out.rename(columns=rename)
    audit.record(
        "1_select_rename", n0, len(out), 0,
        f"kept {len(keep)} of {raw.shape[1]} source columns; renamed to readable names",
    )

    # ── 2. qc7 horizon scales: null off-scale codes, keep the distinction ────
    horizon_cols = [f"days_{v}" for v in QC7_DOMAINS.values()]
    nulled = 0
    for col in horizon_cols:
        na_flag = out[col] == CODE_NOT_APPLICABLE
        dk_flag = out[col] == CODE_DONT_KNOW
        # "Not applicable" is information: for medication it means the respondent
        # takes none, so that domain should be skipped when taking the minimum —
        # not treated as a gap, and not a reason to discard the respondent.
        out[f"{col}_not_applicable"] = na_flag
        out[f"{col}_dont_know"] = dk_flag
        out.loc[na_flag | dk_flag, col] = pd.NA
        nulled += int((na_flag | dk_flag).sum())
    out[horizon_cols] = out[horizon_cols].astype("Float64")
    audit.record(
        "2_qc7_off_scale", len(out), len(out), nulled,
        f"codes {QC_OFF_SCALE_CODES} nulled on {len(horizon_cols)} horizon scales; "
        "left numeric, 'Don't know' (6) would have outranked '>7 days' (4)",
    )

    # ── 3. qc5 / qc8 agreement scales: null off-scale, then reverse ─────────
    agree_cols = [f"info_{v}" for v in QC5_ITEMS.values()] + [f"prep_{v}" for v in QC8_ITEMS.values()]
    nulled = 0
    for col in agree_cols:
        off = out[col].isin(QC_OFF_SCALE_CODES)
        out.loc[off, col] = pd.NA
        nulled += int(off.sum())
        # Source runs 1 = Totally agree … 4 = Totally disagree, so a higher raw
        # value means LESS agreement. Reverse it so the direction is intuitive
        # and so coefficients keep their expected sign.
        out[col] = (QC_AGREE_MAX + 1) - out[col].astype("Float64")
        # Two binaries, because the denominator matters and the choice is not
        # obvious. `_agree` is null for off-scale answers, so its mean is the
        # share among those giving a substantive answer. `_agree_topline` counts
        # off-scale as "did not agree", which is how DG ECHO reports these — and
        # is the only version that reproduces the published figures.
        out[f"{col}_agree"] = (out[col] >= 3).astype("boolean").where(out[col].notna())
        out[f"{col}_agree_topline"] = (out[col] >= 3).fillna(False).astype("int8")
    audit.record(
        "3_agree_scales", len(out), len(out), nulled,
        f"codes {QC_OFF_SCALE_CODES} nulled on {len(agree_cols)} agreement scales, "
        "then reversed so higher = more agreement; added _agree (DK excluded) and "
        "_agree_topline (DK in denominator, matches published figures)",
    )

    # ── 4. qc6 actions: a "don't know" battery is unanswered, not all-zero ──
    action_cols = [f"act_{v}" for v in QC6_ITEMS.values()]
    dk = out["actions_dk"] == 1
    out[action_cols] = out[action_cols].astype("Float64")
    out.loc[dk, action_cols] = pd.NA
    audit.record(
        "4_qc6_dont_know", len(out), len(out), int(dk.sum()) * len(action_cols),
        f"{int(dk.sum())} respondents answered DK to the whole battery; their "
        f"{len(action_cols)} action items nulled rather than counted as zero",
    )

    # ── 5. Derive the action count and reconcile with the survey's own ──────
    # `n_actions` counts only the 13 substantive items — that is what the indices
    # use. Reconciliation against qc6t needs two adjustments, both verified:
    # qc6t also counts "Other", and it is banded at "5 or more".
    out["n_actions"] = out[action_cols].sum(axis=1, min_count=1)
    out["act_other"] = out["act_other"].astype("Float64")
    out.loc[dk, "act_other"] = pd.NA

    reconciled = (out["n_actions"] + out["act_other"]).clip(upper=QC6_TOTAL_TOP_BAND)
    comparable = reconciled.notna() & out["n_actions_survey_banded"].notna() & (~dk)
    mismatches = int((reconciled[comparable] != out.loc[comparable, "n_actions_survey_banded"]).sum())
    audit.record(
        "5_reconcile_count", len(out), len(out), 0,
        f"min(n_actions + other, {QC6_TOTAL_TOP_BAND}) vs survey qc6t: {mismatches} "
        f"mismatches of {int(comparable.sum()):,} comparable rows"
        + ("  ← investigate before trusting the index" if mismatches else "  ✓ exact"),
    )

    # ── 6. Demographics ─────────────────────────────────────────────────────
    if "age" in out.columns:
        out["age"] = pd.to_numeric(out["age"], errors="coerce")
    out["country"] = out["isocntry"].astype(str).str.strip().str.upper()
    # Germany is split East/West in Eurobarometer; collapse for country-level work
    # while keeping the original for anyone who needs the distinction.
    out["country_grouped"] = out["country"].replace({"DE-W": "DE", "DE-E": "DE"})
    audit.record(
        "6_demographics", len(out), len(out), 0,
        "age coerced numeric; country normalised; DE-W/DE-E collapsed into "
        "country_grouped (original kept in country)",
    )

    # ── 7. Weights ──────────────────────────────────────────────────────────
    bad_nat = int((out[WEIGHT_NATIONAL].isna() | (out[WEIGHT_NATIONAL] <= 0)).sum())
    bad_eu = int((out[WEIGHT_EU].isna() | (out[WEIGHT_EU] <= 0)).sum())
    bad_legacy = int((out[WEIGHT_EU27_LEGACY].isna() | (out[WEIGHT_EU27_LEGACY] <= 0)).sum())
    out = out.rename(
        columns={
            WEIGHT_NATIONAL: "w_national",
            WEIGHT_EU: "w_eu",
            WEIGHT_EU27_LEGACY: "w_eu27_legacy",
        }
    )
    audit.record(
        "7_weights", len(out), len(out), 0,
        f"w1→w_national ({bad_nat} unusable), w92→w_eu ({bad_eu} unusable), "
        f"w22→w_eu27_legacy ({bad_legacy} unusable — this is the pre-2013 EU27 and "
        "drops all of Croatia, so it is kept only for reference)",
    )

    return out.reset_index(drop=True), audit


def build_features(clean: pd.DataFrame, audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Derive the analysis columns the indices consume.

    Kept separate from `clean_eb547` so that cleaning (which is about fidelity to
    the source) and feature construction (which is about our design) can be
    reviewed and tested independently.
    """
    audit = audit or Audit()
    out = clean.copy()

    # The awareness side of the knowing-doing gap. qc5_1 asks whether the
    # respondent read, saw or heard information about disaster risks in the last
    # 12 months; after reversal, 3 or 4 means they agreed that they did.
    out["saw_info"] = out["info_saw_info_last_12m_agree"]

    action_cols = [f"act_{v}" for v in QC6_ITEMS.values()]
    out["n_actions"] = out[action_cols].sum(axis=1, min_count=1)
    out["took_any_action"] = (out["n_actions"] > 0).astype("boolean").where(out["n_actions"].notna())

    horizon_cols = [f"days_{v}" for v in QC7_DOMAINS.values()]
    out["n_horizon_answered"] = out[horizon_cols].notna().sum(axis=1)

    audit.record(
        "8_features", len(clean), len(out), 0,
        "derived saw_info (awareness side), n_actions, took_any_action, "
        "n_horizon_answered (how many of the 5 domains are usable for RHI)",
    )
    return out, audit


def variance_audit(df: pd.DataFrame, cols: list[str], min_unique: int = 2,
                   min_std: float = 0.01) -> pd.DataFrame:
    """Flag columns with too little variance to carry information.

    `virality-code` fed a model two features whose standard deviation was exactly
    zero and reported their importance as a finding. Run this before any fit and
    log what it drops.

    The thresholds target *constant* columns, not merely coarse ones. An earlier
    version used `min_unique=5`, which duly dropped every 4-point Likert item in
    the survey — including the capability and information barriers the driver
    model exists to compare. A guardrail that discards the analysis is not a
    guardrail. Ordinal scales are legitimately coarse; what is never legitimate
    is a column that does not vary at all.
    """
    rows = []
    for c in cols:
        s = pd.to_numeric(df[c], errors="coerce")
        nunique, std = int(s.nunique(dropna=True)), float(s.std(skipna=True) or 0.0)
        rows.append(
            {
                "column": c,
                "n_unique": nunique,
                "std": round(std, 6),
                "null_pct": round(float(s.isna().mean()) * 100, 2),
                "drop": nunique < min_unique or std < min_std,
            }
        )
    return pd.DataFrame(rows).sort_values(["drop", "std"], ascending=[False, True])
