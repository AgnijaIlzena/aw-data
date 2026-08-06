"""RHI — Resilience Horizon Index: how long a household could actually cope.

The survey asks, for five separate lifelines, how many days the respondent could
manage without it:

    1 = 1 day or less · 2 = 2-3 days · 3 = 4-7 days · 4 = More than 7 days

RHI is the **minimum** across those domains, because a household with a month of
food and one day of water has a one-day horizon. That `min()` is the whole point
of the index: resilience is set by the weakest lifeline, not the average one.

Three things this module is careful about, because each would otherwise produce a
confident wrong number:

**Interval censoring.** The answers are bands, not days. Reporting "2.1 days"
implies a precision the instrument does not have, so every function returns both
an exact ordinal band and a midpoint-based day estimate, and the headline figures
are reported as bounds rather than points (see `target_bounds`).

**"Not applicable" is not missing.** For medication, code 5 means the respondent
takes no regular treatment — that lifeline does not bind for them. It must be
dropped from the minimum, not counted as a failure and not used to discard the
respondent.

**A partial minimum is optimistic.** The minimum over the domains someone
answered is an *upper bound* on their true horizon: an unanswered domain could be
their weakest. Rows built on partial data are flagged, never silently mixed in.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import (
    QC7_DOMAINS,
    QC7_MIDPOINT_DAYS,
    RESILIENCE_TARGET_DAYS,
)

DOMAINS = list(QC7_DOMAINS.values())
DOMAIN_COLS = [f"days_{d}" for d in DOMAINS]

# Bands, in relation to the 72-hour target.
BAND_BELOW_TARGET = 1        # "1 day or less" — certainly under 72h
BAND_STRADDLES_TARGET = 2    # "2-3 days"      — could be either side
MIN_DOMAINS_DEFAULT = 3


def compute_rhi(df: pd.DataFrame, min_domains: int = MIN_DOMAINS_DEFAULT) -> pd.DataFrame:
    """Add the RHI columns. Pure transform — returns a new frame.

    Columns added:
        rhi_band            minimum ordinal band across answered domains (1-4).
                            Exact: no imputation involved.
        rhi_days            midpoint-based estimate in days. For averages only.
        rhi_binding_domain  which lifeline is the weakest — the product-facing
                            "your weakest link is water".
        rhi_n_domains       how many domains contributed.
        rhi_partial         True when some applicable domain was unanswered, so
                            the value is an upper bound on the true horizon.
    """
    out = df.copy()
    bands = out[DOMAIN_COLS].apply(pd.to_numeric, errors="coerce")

    n_answered = bands.notna().sum(axis=1)
    usable = n_answered >= min_domains

    rhi_band = bands.min(axis=1).where(usable)
    out["rhi_band"] = rhi_band.astype("Float64")
    out["rhi_days"] = rhi_band.map(QC7_MIDPOINT_DAYS).astype("Float64")

    # The binding lifeline — first domain achieving the minimum. idxmin raises on
    # all-null rows, so it is only asked about rows that have at least one answer.
    binding = pd.Series(pd.NA, index=bands.index, dtype="string")
    has_any = bands.notna().any(axis=1)
    if has_any.any():
        found = bands[has_any].idxmin(axis=1, skipna=True)
        binding.loc[has_any] = found.str.removeprefix("days_").astype("string")
    out["rhi_binding_domain"] = binding.where(usable)

    out["rhi_n_domains"] = n_answered.astype("Int64")
    # "Not applicable" domains genuinely do not bind, so they are not a gap in
    # coverage. Only a domain that applies but went unanswered makes the minimum
    # an upper bound.
    na_cols = [f"{c}_not_applicable" for c in DOMAIN_COLS if f"{c}_not_applicable" in out.columns]
    n_not_applicable = out[na_cols].sum(axis=1) if na_cols else 0
    out["rhi_partial"] = (
        (n_answered + n_not_applicable) < len(DOMAIN_COLS)
    ).where(usable).astype("boolean")

    return out


def target_bounds(df: pd.DataFrame, weight: str = "w_eu") -> dict[str, float]:
    """Share of households below the 72-hour target, as a bracket not a point.

    Band 1 ("1 day or less") is certainly under target. Band 2 ("2-3 days")
    straddles it — a respondent there could be at 2 days (fails) or 3 (meets).
    Rather than impute, report the range the data actually supports.
    """
    from actionwise.weighting import weighted_share

    d = df.assign(
        _certain=(df["rhi_band"] == BAND_BELOW_TARGET).astype("Float64").where(df["rhi_band"].notna()),
        _upper=(df["rhi_band"] <= BAND_STRADDLES_TARGET).astype("Float64").where(df["rhi_band"].notna()),
    )
    return {
        "below_target_certain": weighted_share(d, "_certain", weight),
        "below_target_upper": weighted_share(d, "_upper", weight),
        "target_days": RESILIENCE_TARGET_DAYS,
    }


def binding_domain_profile(df: pd.DataFrame, weight: str = "w_eu") -> pd.DataFrame:
    """Which lifeline is the weakest link, and how often.

    This is what turns RHI into product copy: the answer is not "you scored 2.4",
    it is "water is what will run out first".
    """
    from actionwise.weighting import weighted_share

    rows = []
    for domain in DOMAINS:
        flag = (df["rhi_binding_domain"] == domain).astype("Float64")
        rows.append(
            {
                "domain": domain,
                "share_binding": weighted_share(df.assign(_f=flag), "_f", weight),
                "median_band": float(
                    pd.to_numeric(df[f"days_{domain}"], errors="coerce").median(skipna=True)
                ),
                "pct_one_day_or_less": weighted_share(
                    df.assign(_f=(pd.to_numeric(df[f"days_{domain}"], errors="coerce") == 1).astype("Float64")),
                    "_f",
                    weight,
                ),
            }
        )
    return pd.DataFrame(rows).sort_values("share_binding", ascending=False).reset_index(drop=True)


def band_distribution(df: pd.DataFrame, weight: str = "w_eu") -> pd.DataFrame:
    """Weighted distribution over the four RHI bands."""
    from actionwise.weighting import weighted_share

    labels = {1: "1 day or less", 2: "2-3 days", 3: "4-7 days", 4: "More than 7 days"}
    rows = []
    for band, label in labels.items():
        flag = (df["rhi_band"] == band).astype("Float64").where(df["rhi_band"].notna())
        rows.append(
            {
                "band": band,
                "label": label,
                "share": weighted_share(df.assign(_f=flag), "_f", weight),
            }
        )
    return pd.DataFrame(rows)
