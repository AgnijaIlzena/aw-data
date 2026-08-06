"""Ordered probit on the resilience-horizon bands.

`indices/rhi.py` describes what households report. This asks what predicts it:
given age, financial strain, community type and country, how long is a household
likely to last?

An ordered model is the right tool because the outcome is ordered but its
spacing is unknown — the step from "1 day" to "2-3 days" is not the same size as
the step from "4-7 days" to "more than 7". Treating the bands as 1/2/3/4 in a
linear regression would assert equal spacing that the instrument never measured.

Every fit is reported next to a baseline. A pseudo-R² with nothing to compare it
against is the mistake that let `virality-code` present chance-level accuracy as
a result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.miscmodels.ordinal_model import OrderedModel

DEFAULT_PREDICTORS = ["age", "bill_difficulties", "community_type", "social_class", "gender"]


def _design(df: pd.DataFrame, predictors: list[str]) -> pd.DataFrame:
    """Numeric design matrix; categoricals become dummies, first level dropped."""
    X = df[predictors].copy()
    for col in predictors:
        X[col] = pd.to_numeric(X[col], errors="coerce")
    # Community type and social class are categorical codes, not quantities.
    for col in ("community_type", "social_class", "gender"):
        if col in X.columns:
            dummies = pd.get_dummies(X[col].astype("Int64"), prefix=col, drop_first=True, dtype=float)
            X = X.drop(columns=[col]).join(dummies)
    return X


def fit_horizon_model(
    df: pd.DataFrame,
    domain: str,
    predictors: list[str] | None = None,
    weight: str | None = None,
) -> dict:
    """Fit an ordered probit for one lifeline's band, with a baseline for comparison.

    Returns a dict carrying the fitted result, the coefficient table, and the
    accuracy of both the model and a majority-band baseline.

    Weights are reported but not applied to the likelihood: statsmodels'
    OrderedModel has no survey-design support, so a weighted fit here would give
    correct point estimates with wrong standard errors — worse than an honest
    unweighted fit with the limitation stated. Population *shares* elsewhere in
    the project are always weighted.
    """
    predictors = predictors or [p for p in DEFAULT_PREDICTORS if p in df.columns]
    y_col = f"days_{domain}"

    frame = df[[y_col] + predictors].copy()
    X = _design(frame, predictors)
    y = pd.to_numeric(frame[y_col], errors="coerce")

    ok = y.notna() & X.notna().all(axis=1)
    X, y = X[ok], y[ok].astype(int)
    if y.nunique() < 3 or len(y) < 200:
        raise ValueError(f"{domain}: not enough usable variation ({len(y)} rows, {y.nunique()} bands)")

    model = OrderedModel(y, X, distr="probit")
    res = model.fit(method="bfgs", disp=False, maxiter=200)

    pred = res.model.predict(res.params, exog=X)
    predicted_band = np.argmax(pred, axis=1) + int(y.min())
    accuracy = float((predicted_band == y.values).mean())
    baseline = float((y == y.mode().iloc[0]).mean())

    coefs = (
        pd.DataFrame({"coef": res.params, "std_err": res.bse, "pvalue": res.pvalues})
        .loc[X.columns]
        .assign(significant=lambda d: d["pvalue"] < 0.05)
        .sort_values("coef")
    )

    return {
        "domain": domain,
        "n": int(len(y)),
        "result": res,
        "coefficients": coefs,
        "accuracy": accuracy,
        "baseline_majority": baseline,
        "lift_over_baseline": accuracy - baseline,
        "pseudo_r2": float(res.prsquared) if hasattr(res, "prsquared") else float("nan"),
        "weight_note": (
            f"unweighted fit; population shares use {weight}" if weight else "unweighted fit"
        ),
    }


def summarise_fits(fits: list[dict]) -> pd.DataFrame:
    """Model-vs-baseline table across domains. Never report one without the other."""
    return pd.DataFrame(
        [
            {
                "domain": f["domain"],
                "n": f["n"],
                "accuracy": round(f["accuracy"], 4),
                "baseline": round(f["baseline_majority"], 4),
                "lift": round(f["lift_over_baseline"], 4),
                "pseudo_r2": round(f["pseudo_r2"], 4),
                "beats_baseline": f["lift_over_baseline"] > 0,
            }
            for f in fits
        ]
    )
