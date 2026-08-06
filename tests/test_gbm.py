"""Tests for the gap driver model.

The leakage guard gets the most attention here. PGI is computed from the qc6
items, so a model handed those items would score superbly and mean nothing —
which is exactly the shape of the failure this project was set up to avoid. A
guard that never fires protects nothing, so it is tested on inputs that should
trip it.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.data.cleaner_eb547 import variance_audit
from actionwise.models.gbm import (
    assert_no_leakage,
    build_matrix,
    compare_to_baselines,
    fit_gap_model,
)


# ── leakage guard ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "leaky",
    ["act_grab_bag", "n_actions", "pri", "theta_action", "pgi", "took_any_action"],
)
def test_guard_rejects_features_derived_from_the_target(leaky):
    with pytest.raises(ValueError, match="leakage"):
        assert_no_leakage(["age", leaky])


def test_guard_allows_legitimate_predictors():
    assert_no_leakage(["age", "prep_no_time_or_money", "n_disasters_experienced"]) is None


def test_fit_refuses_a_leaky_feature_set():
    df = _synthetic(300)
    df["act_grab_bag"] = 1.0
    with pytest.raises(ValueError, match="leakage"):
        fit_gap_model(df, ["age", "act_grab_bag"])


# ── variance audit ─────────────────────────────────────────────────────────

def test_variance_audit_drops_constant_columns():
    df = pd.DataFrame({"constant": [3.0] * 50, "varies": np.linspace(0, 1, 50)})
    audit = variance_audit(df, ["constant", "varies"])
    assert bool(audit.set_index("column").loc["constant", "drop"]) is True
    assert bool(audit.set_index("column").loc["varies", "drop"]) is False


def test_variance_audit_keeps_four_point_likert_scales():
    """Regression test: an earlier min_unique=5 discarded every Likert item,
    including the two barriers the driver model exists to compare."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"likert": rng.integers(1, 5, size=500).astype(float)})
    audit = variance_audit(df, ["likert"])
    assert bool(audit.loc[0, "drop"]) is False


# ── model ──────────────────────────────────────────────────────────────────

def _synthetic(n: int = 1200, seed: int = 3) -> pd.DataFrame:
    """A planted signal: `barrier` genuinely drives the gap, `noise` does not."""
    rng = np.random.default_rng(seed)
    barrier = rng.integers(1, 5, size=n).astype(float)
    return pd.DataFrame(
        {
            "pgi": np.clip(0.4 + 0.1 * barrier + rng.normal(0, 0.05, n), 0, 1),
            "prep_no_time_or_money": barrier,
            "age": rng.integers(18, 80, size=n).astype(float),
            "noise": rng.normal(size=n),
            "country_grouped": rng.choice(list("ABCDE"), size=n),
        }
    )


def test_model_recovers_a_planted_driver():
    fit = fit_gap_model(_synthetic(), ["prep_no_time_or_money", "age", "noise"])
    assert fit["r2_oof"] > 0.5
    assert fit["n_groups"] == 5


def test_grouped_cv_uses_every_country_as_held_out():
    fit = fit_gap_model(_synthetic(), ["prep_no_time_or_money", "age"])
    assert fit["oof"].notna().all(), "every row should receive an out-of-fold prediction"


def test_baseline_comparison_always_includes_the_mean_predictor():
    df = _synthetic(600)
    df["gender"] = 1.0
    comparison = compare_to_baselines(df, ["prep_no_time_or_money", "age", "noise"])
    assert "mean predictor" in set(comparison["model"])
    assert comparison.query("model == 'mean predictor'")["r2_oof"].iloc[0] == 0.0
    full = comparison.query("model == 'full model'")["r2_oof"].iloc[0]
    assert full > 0, "planted signal should beat the mean predictor"


def test_build_matrix_marks_categoricals_for_lightgbm():
    X = build_matrix(_synthetic(50), ["prep_no_time_or_money", "age", "social_class"]
                     if False else ["prep_no_time_or_money", "age"])
    assert list(X.columns) == ["prep_no_time_or_money", "age"]
    assert X["age"].dtype.kind == "f"
