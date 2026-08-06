"""Tests for the cleaning step.

This module is where the three traps in this dataset are neutralised, so it is
where a silent regression would do the most damage:

  * off-scale codes 5/6 left as numerics ("Don't know" outranking ">7 days")
  * agreement scales not reversed (higher raw value means *less* agreement)
  * a "don't know" battery counted as thirteen zeros rather than unanswered

Until now these were only covered indirectly, through the sanity gate. The gate
would catch a regression, but it would not say which of the three broke.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.config import (
    QC5_ITEMS,
    QC6_ITEMS,
    QC7_DOMAINS,
    QC8_ITEMS,
)
from actionwise.data.cleaner_eb547 import Audit, build_features, clean_eb547


def raw_frame(n: int = 6) -> pd.DataFrame:
    """A minimal frame with the real column names and plausible codes."""
    rng = np.random.default_rng(0)
    data = {
        "uniqid": np.arange(n, dtype=float),
        "serialid": np.arange(n, dtype=float),
        # cycled so the helper works for any n
        "isocntry": [["LV", "DE-W", "DE-E", "FR", "MT", "LV"][i % 6] for i in range(n)],
        "w1": np.ones(n),
        "w92": np.ones(n),
        "w22": np.ones(n),
        "qc6.14": np.zeros(n),
        "qc6.15": np.zeros(n),
        "qc6t": np.ones(n),
        "qc3.15": np.zeros(n),
        "qc3t": np.zeros(n),
        "qc2a": np.ones(n),
        "qc1a": np.ones(n),
        "qc10": np.ones(n),
        "qc11": np.ones(n),
        "d10": np.ones(n),
        "d11": np.full(n, 40.0),
        "d11r2": np.ones(n),
        "d25": np.ones(n),
        "d60": np.ones(n),
        "d63": np.ones(n),
    }
    for col in QC6_ITEMS:
        data[col] = rng.integers(0, 2, n).astype(float)
    for col in QC7_DOMAINS:
        data[col] = np.full(n, 3.0)
    for col in list(QC5_ITEMS) + list(QC8_ITEMS):
        data[col] = np.full(n, 2.0)   # "Tend to agree"
    return pd.DataFrame(data)


# ── the three traps ────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [5, 6])
def test_off_scale_horizon_codes_become_null(code):
    """Left numeric, 'Don't know' (6) would rank above 'More than 7 days' (4)."""
    raw = raw_frame()
    raw.loc[0, "qc7_1"] = float(code)
    out, _ = clean_eb547(raw)
    assert pd.isna(out.loc[0, "days_water"])
    assert out.loc[1, "days_water"] == 3


def test_not_applicable_and_dont_know_are_distinguished():
    """Both are nulled, but only one means 'this lifeline does not bind for me'."""
    raw = raw_frame()
    raw.loc[0, "qc7_5"] = 5.0   # not applicable — takes no medication
    raw.loc[1, "qc7_5"] = 6.0   # genuinely doesn't know
    out, _ = clean_eb547(raw)
    assert bool(out.loc[0, "days_medication_not_applicable"]) is True
    assert bool(out.loc[0, "days_medication_dont_know"]) is False
    assert bool(out.loc[1, "days_medication_not_applicable"]) is False
    assert bool(out.loc[1, "days_medication_dont_know"]) is True


def test_agreement_scales_are_reversed():
    """Source runs 1 = Totally agree .. 4 = Totally disagree; we want the opposite."""
    raw = raw_frame()
    raw.loc[0, "qc8_2"] = 1.0   # totally agree
    raw.loc[1, "qc8_2"] = 4.0   # totally disagree
    out, _ = clean_eb547(raw)
    assert out.loc[0, "prep_feels_well_prepared"] == 4
    assert out.loc[1, "prep_feels_well_prepared"] == 1
    assert bool(out.loc[0, "prep_feels_well_prepared_agree"]) is True
    assert bool(out.loc[1, "prep_feels_well_prepared_agree"]) is False


def test_dont_know_battery_is_unanswered_not_thirteen_zeros():
    raw = raw_frame()
    raw.loc[0, list(QC6_ITEMS)] = 0.0
    raw.loc[0, "qc6.15"] = 1.0            # DK to the whole battery
    raw.loc[0, "qc6t"] = 6.0
    out, _ = clean_eb547(raw)
    action_cols = [f"act_{v}" for v in QC6_ITEMS.values()]
    assert out.loc[0, action_cols].isna().all()
    assert pd.isna(out.loc[0, "n_actions"]), "a DK respondent has no action count"


# ── the two denominators ───────────────────────────────────────────────────

def test_both_agreement_denominators_are_produced():
    """`_agree` excludes DK; `_agree_topline` keeps it — only the latter matches
    the figures DG ECHO published."""
    raw = raw_frame(4)
    raw.loc[0, "qc8_5"] = 1.0    # agree
    raw.loc[1, "qc8_5"] = 4.0    # disagree
    raw.loc[2, "qc8_5"] = 6.0    # don't know
    raw.loc[3, "qc8_5"] = 2.0    # agree
    out, _ = clean_eb547(raw)
    assert out["prep_needs_more_info_agree"].mean() == pytest.approx(2 / 3)
    assert out["prep_needs_more_info_agree_topline"].mean() == pytest.approx(2 / 4)


# ── structural guarantees ──────────────────────────────────────────────────

def test_cleaning_never_drops_a_row():
    """Unusable answers become nulls; the decision to exclude belongs downstream."""
    raw = raw_frame(6)
    raw.loc[0, list(QC7_DOMAINS)] = 6.0
    raw.loc[1, "qc6.15"] = 1.0
    out, _ = clean_eb547(raw)
    assert len(out) == len(raw)


def test_german_split_is_collapsed_but_preserved():
    out, _ = clean_eb547(raw_frame())
    assert set(out.loc[[1, 2], "country"]) == {"DE-W", "DE-E"}
    assert set(out.loc[[1, 2], "country_grouped"]) == {"DE"}


def test_weights_are_renamed_to_their_meaning():
    out, _ = clean_eb547(raw_frame())
    assert {"w_national", "w_eu", "w_eu27_legacy"} <= set(out.columns)
    assert "w1" not in out.columns and "w92" not in out.columns


# ── the audit trail ────────────────────────────────────────────────────────

def test_audit_records_every_step_with_a_reason():
    _, audit = clean_eb547(raw_frame())
    trail = audit.to_frame()
    assert len(trail) == 7
    assert (trail["reason"].str.len() > 20).all(), "every step must explain itself"
    assert set(trail.columns) == {"step", "rows_in", "rows_out", "rows_lost",
                                  "cells_nulled", "reason"}


def test_audit_counts_the_cells_it_nulls():
    raw = raw_frame()
    raw.loc[0, "qc7_1"] = 6.0
    raw.loc[1, "qc7_2"] = 5.0
    _, audit = clean_eb547(raw)
    step = audit.to_frame().set_index("step").loc["2_qc7_off_scale"]
    assert step["cells_nulled"] == 2


def test_count_reconciliation_is_exact_on_clean_input():
    """min(actions + other, 5) must equal the survey's own banded count."""
    raw = raw_frame(20)
    raw["qc6t"] = np.minimum(raw[list(QC6_ITEMS)].sum(axis=1) + raw["qc6.14"], 5)
    _, audit = clean_eb547(raw)
    reason = audit.to_frame().set_index("step").loc["5_reconcile_count", "reason"]
    assert "0 mismatches" in reason


def test_build_features_adds_the_awareness_side():
    clean, audit = clean_eb547(raw_frame())
    feats, audit = build_features(clean, audit)
    assert "saw_info" in feats.columns
    assert "n_horizon_answered" in feats.columns
    assert len(audit.to_frame()) == 8


def test_missing_source_column_fails_loudly():
    raw = raw_frame().drop(columns=["qc7_1"])
    with pytest.raises(KeyError, match="qc7_1"):
        clean_eb547(raw)


def test_audit_can_be_threaded_through_both_stages():
    audit = Audit()
    clean, audit = clean_eb547(raw_frame(), audit)
    _, audit = build_features(clean, audit)
    assert audit.to_frame()["step"].is_unique
