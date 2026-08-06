"""Percentile tables — the benchmark the product actually shows a user.

The line ActionWise wants on screen is *"you are better prepared than 62% of
Latvians aged 35-44"*. That requires a weighted reference distribution per group,
which is what this builds.

Two rules it enforces:

* **Weighted throughout.** An unweighted percentile compares the user to the
  people who happened to answer the phone, not to the country.
* **Small groups are labelled, not hidden.** Latvia contributes ~1,000
  respondents; split six ways by age some cells get thin. A thin cell is a caveat
  to display, not a reason to silently show a number built on 40 people.
"""
from __future__ import annotations

import pandas as pd

from actionwise.weighting import effective_n, weighted_percentile_of, weighted_quantile

DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
MIN_CELL_ROWS = 100


def percentile_table(
    df: pd.DataFrame,
    value_col: str = "pri",
    group_col: str | None = "age_band",
    weight_col: str = "w_national",
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    min_rows: int = MIN_CELL_ROWS,
) -> pd.DataFrame:
    """Weighted quantile breakpoints per group, with a reliability flag."""
    groups = [("all", df)] if group_col is None else list(df.groupby(group_col, dropna=True))
    if group_col is not None:
        groups = [("all", df)] + groups

    rows = []
    for key, sub in groups:
        usable = sub[sub[value_col].notna()]
        row = {
            "group": str(key),
            "n_rows": len(usable),
            "n_eff": round(effective_n(usable, weight_col), 1),
            "thin_cell": len(usable) < min_rows,
        }
        for q in quantiles:
            row[f"p{int(q * 100)}"] = round(
                weighted_quantile(usable[value_col], usable[weight_col], q), 2
            )
        rows.append(row)
    return pd.DataFrame(rows)


def benchmark(
    value: float,
    reference: pd.DataFrame,
    value_col: str = "pri",
    weight_col: str = "w_national",
) -> dict:
    """Where one score sits in a reference population.

    Returns the percentile plus the sentence the product would render, so the
    phrasing lives with the computation rather than being reinvented in the UI.
    """
    pct = weighted_percentile_of(value, reference[value_col], reference[weight_col])
    return {
        "value": value,
        "percentile": round(pct, 1) if pd.notna(pct) else None,
        "n_reference": int(reference[value_col].notna().sum()),
        "sentence": (
            f"better prepared than {pct:.0f}% of the reference group"
            if pd.notna(pct)
            else "not enough reference data"
        ),
    }
