"""2PL item response theory on the thirteen preparedness measures.

Why a latent-trait model rather than "count the boxes ticked": a simple count
says owning a flashlight and keeping a 72-hour grab-bag are worth the same. They
are not. 53.5% of Europeans have the flashlight and 8.6% have the grab-bag, so
the grab-bag carries far more information about how prepared someone actually is.
IRT estimates that weighting from the data instead of asserting it.

The model, for person j and item i:

    P(acted) = 1 / (1 + exp(-a_i * (theta_j - b_i)))

    a_i  discrimination — how sharply the item separates prepared from unprepared
    b_i  difficulty     — how far along the trait you must be before it is likely
    theta_j             — the person's latent preparedness, scaled to PRI

This is a **measurement** model, not a predictive one. It makes no claim to
forecast anything, so there is no accuracy figure to compare against a baseline —
the relevant checks are item fit and face validity, both reported below.

Estimation uses `girth.twopl_mml` (marginal maximum likelihood). Infit and outfit
are implemented here rather than taken from a library, both because girth does
not expose them and because a statistic this central to defending the model
should be legible in the repository.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from actionwise.config import QC6_ITEMS, QC6_LABELS

ITEM_COLS = [f"act_{name}" for name in QC6_ITEMS.values()]

# Conventional bounds for "productive for measurement" in Rasch/IRT practice.
FIT_LOW, FIT_HIGH = 0.5, 1.5


def response_matrix(df: pd.DataFrame, items: list[str] | None = None) -> tuple[np.ndarray, pd.Index]:
    """Complete-case [persons x items] matrix of 0/1 responses.

    Respondents who answered "don't know" to the whole battery were nulled during
    cleaning and drop out here — they carry no information about the trait, and
    imputing zeros would read as "maximally unprepared".
    """
    items = items or ITEM_COLS
    block = df[items].apply(pd.to_numeric, errors="coerce")
    complete = block.notna().all(axis=1)
    # girth indexes its probability tables with the response values, so the
    # matrix must be integer — float or bool raises deep inside the library.
    return block[complete].to_numpy(dtype=int), df.index[complete]


def fit_2pl(df: pd.DataFrame, items: list[str] | None = None, seed: int = 42) -> pd.DataFrame:
    """Estimate the item bank on the pooled sample.

    Returns one row per item with discrimination, difficulty, the observed
    proportion, and the human label — sorted from easiest to hardest.
    """
    import girth

    items = items or ITEM_COLS
    matrix, _ = response_matrix(df, items)
    if len(matrix) < 500:
        raise ValueError(f"only {len(matrix)} complete cases — too few to calibrate")

    np.random.seed(seed)
    # girth wants [items x participants].
    estimates = girth.twopl_mml(matrix.T)

    bank = pd.DataFrame(
        {
            "item": [c.removeprefix("act_") for c in items],
            "discrimination": np.asarray(estimates["Discrimination"], dtype=float),
            "difficulty": np.asarray(estimates["Difficulty"], dtype=float),
            "p_observed": matrix.mean(axis=0),
        }
    )
    bank["label"] = bank["item"].map(QC6_LABELS).fillna(bank["item"])
    bank["n_calibration"] = len(matrix)
    return bank.sort_values("difficulty").reset_index(drop=True)


def score_ability(df: pd.DataFrame, bank: pd.DataFrame,
                  items: list[str] | None = None) -> pd.Series:
    """Expected-a-posteriori theta for each respondent, aligned to `df.index`.

    Null for anyone without a complete response pattern.
    """
    import girth

    items = items or ITEM_COLS
    matrix, index = response_matrix(df, items)

    order = [c.removeprefix("act_") for c in items]
    bank_ordered = bank.set_index("item").loc[order]

    theta = girth.ability_eap(
        matrix.T,
        bank_ordered["difficulty"].to_numpy(dtype=float),
        bank_ordered["discrimination"].to_numpy(dtype=float),
    )
    return pd.Series(np.asarray(theta, dtype=float), index=index).reindex(df.index)


def item_fit(df: pd.DataFrame, bank: pd.DataFrame, theta: pd.Series,
             items: list[str] | None = None) -> pd.DataFrame:
    """Infit and outfit mean-square per item.

    Standardised residual z = (x - P) / sqrt(P(1-P)).
        outfit = mean(z^2)                        — sensitive to wild outliers
        infit  = sum(W z^2) / sum(W), W = P(1-P)  — weighted toward on-target responses

    Both centre on 1.0. Values above ~1.5 mean the item behaves erratically given
    the model; below ~0.5 means it is nearly redundant with the others.
    """
    items = items or ITEM_COLS
    matrix, index = response_matrix(df, items)
    th = theta.reindex(index).to_numpy(dtype=float)

    order = [c.removeprefix("act_") for c in items]
    b = bank.set_index("item").loc[order, "difficulty"].to_numpy(dtype=float)
    a = bank.set_index("item").loc[order, "discrimination"].to_numpy(dtype=float)

    ok = np.isfinite(th)
    th, matrix = th[ok], matrix[ok].astype(float)

    logit = a[None, :] * (th[:, None] - b[None, :])
    p = 1.0 / (1.0 + np.exp(-logit))
    variance = np.clip(p * (1 - p), 1e-9, None)
    z2 = (matrix - p) ** 2 / variance

    outfit = z2.mean(axis=0)
    infit = (variance * z2).sum(axis=0) / variance.sum(axis=0)

    fit = pd.DataFrame(
        {
            "item": order,
            "infit": infit,
            "outfit": outfit,
            "n": int(len(matrix)),
        }
    )
    fit["misfitting"] = ~fit[["infit", "outfit"]].apply(
        lambda s: s.between(FIT_LOW, FIT_HIGH)
    ).all(axis=1)
    return fit


def theta_to_pri(theta: pd.Series) -> pd.Series:
    """Map the latent trait onto a 0-100 PRI.

    Uses the normal CDF, so PRI is directly readable as "more prepared than N% of
    the calibration population" — which is the sentence the product wants to show
    the user, rather than an abstract logit.

    Returns a Series carrying `theta`'s index: scipy would hand back a bare array,
    and assigning that as a column aligns by position instead of by index, which
    silently mismatches rows the moment a caller passes a filtered frame.
    """
    values = pd.to_numeric(theta, errors="coerce")
    return pd.Series(norm.cdf(values) * 100, index=values.index).round(1)


def face_validity(bank: pd.DataFrame) -> pd.DataFrame:
    """Check the difficulty ordering against what we already know is true.

    If the model says a grab-bag is easier than a flashlight, the model is wrong —
    the observed proportions (53.5% vs 8.6%) say otherwise. A model that passes
    every numerical diagnostic and fails this one should still be rejected.
    """
    checks = [
        ("grab_bag harder than flashlight_candles", "grab_bag", "flashlight_candles"),
        ("training_exercise harder than first_aid_kit", "training_exercise", "first_aid_kit"),
        ("neighbourhood_discussion harder than emergency_food_drink",
         "neighbourhood_discussion", "emergency_food_drink"),
    ]
    d = bank.set_index("item")["difficulty"]
    rows = []
    for name, harder, easier in checks:
        if harder in d.index and easier in d.index:
            rows.append(
                {
                    "check": name,
                    "b_harder": round(float(d[harder]), 3),
                    "b_easier": round(float(d[easier]), 3),
                    "pass": bool(d[harder] > d[easier]),
                }
            )
    # Difficulty must rank inversely with how often the item was done — but not
    # perfectly. Under 2PL, discrimination varies, and a low-discrimination item
    # has a flat characteristic curve, so its difficulty can be extreme while its
    # observed proportion stays middling. In this bank "signed up for alerts"
    # (b=+4.80, a=0.45, 11.2% observed) ranks as harder than the grab-bag
    # (b=+4.04, a=0.66, 7.7% observed) for exactly that reason. A threshold of
    # -0.9 would be asserting a 1PL/Rasch property the model does not claim, so
    # the bar is strong-but-not-perfect monotonicity.
    corr = bank["difficulty"].corr(bank["p_observed"], method="spearman")
    rows.append(
        {
            "check": "difficulty ranks inversely with observed frequency (rho < -0.80)",
            "b_harder": round(float(corr), 3),
            "b_easier": float("nan"),
            "pass": bool(corr < -0.80),
        }
    )
    return pd.DataFrame(rows)


def holdout_transfer(df: pd.DataFrame, country: str, country_col: str = "country_grouped",
                     items: list[str] | None = None) -> dict:
    """Does a bank calibrated elsewhere score this country the way its own would?

    Latvia contributes ~1,000 respondents, too few to calibrate 13 items stably on
    its own, so the design pools all of Europe. That is only legitimate if the
    pooled item parameters actually transfer. This fits both ways and compares:

        pooled  — calibrated on every country EXCEPT `country`, then used to score it
        native  — calibrated on `country` alone

    A high correlation between the two sets of scores means pooling is safe. A low
    one means the items behave differently there and the pooled bank is measuring
    something else. Either way the number gets reported, not buried.
    """
    items = items or ITEM_COLS
    others = df[df[country_col] != country]
    target = df[df[country_col] == country]
    if len(target) < 300:
        raise ValueError(f"{country}: {len(target)} rows is too few to calibrate natively")

    pooled_bank = fit_2pl(others, items)
    native_bank = fit_2pl(target, items)

    theta_pooled = score_ability(target, pooled_bank, items)
    theta_native = score_ability(target, native_bank, items)

    both = pd.concat([theta_pooled, theta_native], axis=1, keys=["pooled", "native"]).dropna()
    pri_pooled = theta_to_pri(both["pooled"])
    pri_native = theta_to_pri(both["native"])

    b_pooled = pooled_bank.set_index("item")["difficulty"]
    b_native = native_bank.set_index("item")["difficulty"].reindex(b_pooled.index)

    return {
        "country": country,
        "n_target": int(len(target)),
        "n_calibration_pooled": int(pooled_bank["n_calibration"].iloc[0]),
        "n_calibration_native": int(native_bank["n_calibration"].iloc[0]),
        "theta_correlation": float(both["pooled"].corr(both["native"])),
        "theta_rank_correlation": float(both["pooled"].corr(both["native"], method="spearman")),
        "difficulty_correlation": float(b_pooled.corr(b_native)),
        "mean_abs_pri_difference": float((pri_pooled - pri_native).abs().mean()),
        "pooled_bank": pooled_bank,
        "native_bank": native_bank,
    }


def diagnose_dimensionality(bank: pd.DataFrame, split_at: float = 1.0) -> pd.DataFrame:
    """Flag whether the battery plausibly measures one thing or two.

    2PL assumes a single latent trait. If discrimination splits cleanly into a
    high group and a low group, that assumption is doing work it may not deserve:
    the high-discrimination items are sharply measuring one construct while the
    low ones are weakly measuring something adjacent.

    This is reported rather than corrected. A two-dimensional model is the right
    answer if the split is real, but that is a design decision, not something to
    slip in silently.
    """
    hi = bank[bank["discrimination"] >= split_at]
    lo = bank[bank["discrimination"] < split_at]
    return pd.DataFrame(
        [
            {
                "group": "high discrimination (sharp)",
                "n_items": len(hi),
                "mean_a": round(float(hi["discrimination"].mean()), 3) if len(hi) else float("nan"),
                "mean_b": round(float(hi["difficulty"].mean()), 3) if len(hi) else float("nan"),
                "items": ", ".join(hi["item"]),
            },
            {
                "group": "low discrimination (flat)",
                "n_items": len(lo),
                "mean_a": round(float(lo["discrimination"].mean()), 3) if len(lo) else float("nan"),
                "mean_b": round(float(lo["difficulty"].mean()), 3) if len(lo) else float("nan"),
                "items": ", ".join(lo["item"]),
            },
        ]
    )
