"""Survey-weighted estimation helpers.

Every population figure in this project goes through here. Eurobarometer samples
are not self-weighting — Malta contributes 506 interviews and Germany 1,521 — so
an unweighted mean is not an estimate of anything.

Weights also inflate variance, so a naive confidence interval based on the raw
row count is too narrow. `effective_n` implements Kish's effective sample size,
which is what the intervals here are built on.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _aligned(df: pd.DataFrame, value_col: str, weight_col: str) -> tuple[pd.Series, pd.Series]:
    """Numeric values and positive weights, restricted to rows usable for both."""
    w = pd.to_numeric(df[weight_col], errors="coerce")
    v = pd.to_numeric(df[value_col], errors="coerce")
    ok = w.notna() & (w > 0) & v.notna()
    return v[ok], w[ok]


def weighted_mean(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    v, w = _aligned(df, value_col, weight_col)
    if w.empty:
        return float("nan")
    return float((v * w).sum() / w.sum())


def weighted_share(df: pd.DataFrame, flag_col: str, weight_col: str,
                   fillna: bool = False) -> float:
    """Weighted share of rows where `flag_col` is true.

    Args:
        fillna: when True, null answers count as *false* and stay in the
            denominator. That is how DG ECHO reports its toplines; see
            config.TOPLINE_COUNTS_DK_IN_DENOMINATOR. When False, null answers are
            excluded entirely, giving the share among substantive answers.
    """
    w = pd.to_numeric(df[weight_col], errors="coerce")
    v = pd.to_numeric(df[flag_col], errors="coerce")
    if fillna:
        v = v.fillna(0)
        ok = w.notna() & (w > 0)
    else:
        ok = w.notna() & (w > 0) & v.notna()
    if not ok.any():
        return float("nan")
    return float((v[ok] * w[ok]).sum() / w[ok].sum())


def effective_n(df: pd.DataFrame, weight_col: str, subset: pd.Series | None = None) -> float:
    """Kish's effective sample size: (Σw)² / Σw².

    Always ≤ the row count. Using the row count instead would understate every
    confidence interval in the project.
    """
    w = pd.to_numeric(df[weight_col], errors="coerce")
    ok = w.notna() & (w > 0)
    if subset is not None:
        ok &= subset.fillna(False)
    w = w[ok]
    if w.empty:
        return 0.0
    return float(w.sum() ** 2 / (w**2).sum())


def share_ci(share: float, n_eff: float, z: float = 1.96) -> tuple[float, float]:
    """Wald interval on a proportion, using the effective sample size."""
    if not np.isfinite(share) or n_eff <= 0:
        return (float("nan"), float("nan"))
    se = np.sqrt(max(share * (1 - share), 0) / n_eff)
    return (max(0.0, share - z * se), min(1.0, share + z * se))


def weighted_quantile(values: pd.Series, weights: pd.Series, q: float) -> float:
    """Weighted quantile via the linearly interpolated weighted ECDF.

    numpy has no weighted percentile, and using the unweighted one would answer a
    question about the sample rather than about the population.
    """
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    ok = v.notna() & w.notna() & (w > 0)
    if not ok.any():
        return float("nan")

    order = v[ok].sort_values().index
    v_sorted = v[order].to_numpy(dtype=float)
    w_sorted = w[order].to_numpy(dtype=float)

    # Midpoint of each observation's weight block — the standard convention, and
    # the one that makes the median of equal weights match numpy's.
    cum = np.cumsum(w_sorted) - 0.5 * w_sorted
    cum /= w_sorted.sum()
    return float(np.interp(q, cum, v_sorted))


def weighted_percentile_of(value: float, values: pd.Series, weights: pd.Series) -> float:
    """Where `value` falls in a weighted distribution, as a 0-100 percentile.

    This is the number behind "better prepared than 62% of Latvians".
    """
    v = pd.to_numeric(values, errors="coerce")
    w = pd.to_numeric(weights, errors="coerce")
    ok = v.notna() & w.notna() & (w > 0)
    if not ok.any() or not np.isfinite(value):
        return float("nan")
    below = w[ok][v[ok] < value].sum()
    equal = w[ok][v[ok] == value].sum()
    return float((below + 0.5 * equal) / w[ok].sum() * 100)


def share_by_group(df: pd.DataFrame, flag_col: str, group_col: str, weight_col: str,
                   fillna: bool = False, min_n: int = 30) -> pd.DataFrame:
    """Weighted share of `flag_col` per group, with effective n and an interval.

    Groups with fewer than `min_n` raw rows are returned but flagged, rather than
    dropped — a small cell is a caveat, not a reason to hide the estimate.
    """
    rows = []
    for key, sub in df.groupby(group_col, dropna=True):
        share = weighted_share(sub, flag_col, weight_col, fillna=fillna)
        n_eff = effective_n(sub, weight_col)
        lo, hi = share_ci(share, n_eff)
        rows.append(
            {
                group_col: key,
                "share": share,
                "ci_low": lo,
                "ci_high": hi,
                "n_rows": len(sub),
                "n_eff": round(n_eff, 1),
                "small_cell": len(sub) < min_n,
            }
        )
    return pd.DataFrame(rows).sort_values("share", ascending=False).reset_index(drop=True)
