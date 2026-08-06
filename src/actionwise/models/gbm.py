"""What predicts the knowing-doing gap.

The product question this answers is not "how big is the gap" (Phase 3 did that)
but *why* someone sits in it. Two candidate explanations are measured separately
by the survey, which is unusually convenient:

    qc8_3  "no time or financial resources to prepare"   -> capability barrier
    qc8_5  "need more information to prepare"            -> information barrier

Those imply opposite products. If the gap is mostly informational, a better
guide closes it. If it is mostly capability, no amount of content will, and the
answer is cheaper kit, reminders, or community provision.

Leakage
-------
PGI is computed from the qc6 action items, so any feature derived from those —
`act_*`, `n_actions`, `pri`, `theta_action` — is the target in disguise. A model
fed those would score beautifully and mean nothing, which is precisely how
`virality-code` produced a "finding" from noise. `assert_no_leakage` runs before
every fit and raises rather than warns.

Baselines
---------
Reported next to every model: the mean predictor (R² = 0 by construction) and a
demographics-only model. An R² alone says nothing about whether the interesting
features are doing any work.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import GroupKFold

# Anything computed from the qc6 battery. PGI is built from these, so they can
# never appear on the right-hand side.
LEAKY_PREFIXES = ("act_", "n_actions", "pri", "theta_", "pgi", "took_any_action")

BARRIER_FEATURES = [
    "prep_no_time_or_money",       # capability barrier
    "prep_needs_more_info",        # information barrier
    "prep_prep_helps_cope",        # response efficacy
    "prep_knows_what_to_do",       # self-efficacy
    "prep_knows_alert_channel",
    "prep_prep_info_easy",
    "prep_employer_encourages",
    "prep_services_encourage",
    "prep_feels_well_prepared",
]
INFO_FEATURES = [
    "info_feels_informed",
    "info_trusts_official_info",
    "info_info_easy_to_find",
    "info_knows_where_abroad",
]
CONTEXT_FEATURES = [
    "no_disaster_experience",
    "n_disasters_experienced",
    "top_personal_risk",
    "trusts_emergency_services",
    "volunteers_for_responders",
]
DEMOGRAPHIC_FEATURES = ["age", "gender", "community_type", "bill_difficulties", "social_class"]

CATEGORICAL = {"gender", "community_type", "social_class", "top_personal_risk", "country_grouped"}


def assert_no_leakage(features: list[str]) -> None:
    """Raise if any feature is derived from the same items as the target."""
    leaks = [f for f in features if f.startswith(LEAKY_PREFIXES)]
    if leaks:
        raise ValueError(
            f"these features are derived from the qc6 battery that PGI is computed "
            f"from, so including them would be target leakage: {leaks}"
        )


def build_matrix(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Numeric design matrix, categoricals as pandas `category` for LightGBM."""
    assert_no_leakage(features)
    X = df[features].copy()
    for col in features:
        if col in CATEGORICAL:
            X[col] = X[col].astype("float64").astype("Int64").astype("category")
        else:
            X[col] = pd.to_numeric(X[col], errors="coerce")
    return X


def fit_gap_model(
    df: pd.DataFrame,
    features: list[str],
    target: str = "pgi",
    group_col: str = "country_grouped",
    seed: int = 42,
) -> dict:
    """Gradient-boosted regression on the gap, grouped-CV by country.

    Splitting by country rather than at random is deliberate: rows from the same
    country share sampling design and national context, so a random split would
    let the model memorise country effects and report an optimistic score.
    """
    import lightgbm as lgb

    assert_no_leakage(features)

    frame = df[df[target].notna()].copy()
    X = build_matrix(frame, features)
    y = pd.to_numeric(frame[target], errors="coerce")
    groups = frame[group_col].astype(str)

    ok = y.notna()
    X, y, groups = X[ok], y[ok], groups[ok]

    n_splits = min(5, groups.nunique())
    cv = GroupKFold(n_splits=n_splits)
    oof = pd.Series(np.nan, index=y.index, dtype=float)

    for train_idx, test_idx in cv.split(X, y, groups):
        model = lgb.LGBMRegressor(
            n_estimators=400, learning_rate=0.05, num_leaves=31,
            min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
            random_state=seed, verbose=-1,
        )
        model.fit(X.iloc[train_idx], y.iloc[train_idx])
        oof.iloc[test_idx] = model.predict(X.iloc[test_idx])

    final = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=40, subsample=0.8, colsample_bytree=0.8,
        random_state=seed, verbose=-1,
    ).fit(X, y)

    return {
        "model": final,
        "X": X,
        "y": y,
        "oof": oof,
        "features": features,
        "n": int(len(y)),
        "r2_oof": float(r2_score(y, oof)),
        "mae_oof": float(mean_absolute_error(y, oof)),
        # The mean predictor is the honest floor: R^2 = 0 by construction.
        "mae_baseline_mean": float(mean_absolute_error(y, np.full(len(y), y.mean()))),
        "n_groups": int(groups.nunique()),
    }


def compare_to_baselines(df: pd.DataFrame, full_features: list[str],
                         target: str = "pgi") -> pd.DataFrame:
    """Full model vs demographics-only vs the mean predictor.

    A number without its baseline is not a result.
    """
    rows = []
    specs = [
        ("mean predictor", []),
        ("demographics only", [f for f in DEMOGRAPHIC_FEATURES if f in df.columns]),
        ("full model", full_features),
    ]
    for name, feats in specs:
        if not feats:
            y = pd.to_numeric(df[target], errors="coerce").dropna()
            rows.append({"model": name, "n_features": 0, "r2_oof": 0.0,
                         "mae_oof": float(mean_absolute_error(y, np.full(len(y), y.mean())))})
            continue
        fit = fit_gap_model(df, feats, target=target)
        rows.append({"model": name, "n_features": len(feats),
                     "r2_oof": round(fit["r2_oof"], 4), "mae_oof": round(fit["mae_oof"], 4)})
    return pd.DataFrame(rows)


def shap_importance(fit: dict, max_rows: int = 4000, seed: int = 42) -> pd.DataFrame:
    """Mean absolute SHAP value per feature, plus the mean signed effect.

    The signed column is what answers the capability-versus-information question:
    it says which direction a feature pushes the gap, not merely that it matters.
    """
    import shap

    X = fit["X"]
    sample = X.sample(min(max_rows, len(X)), random_state=seed)
    explainer = shap.TreeExplainer(fit["model"])
    values = explainer.shap_values(sample)

    return (
        pd.DataFrame(
            {
                "feature": X.columns,
                "mean_abs_shap": np.abs(values).mean(axis=0),
                "mean_shap": values.mean(axis=0),
            }
        )
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
