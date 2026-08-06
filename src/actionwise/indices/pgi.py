"""PGI — Preparedness Gap Index, and the descriptive gap table beneath it.

The project's central question is whether people who have *seen* preparedness
information actually *act* on it. Each respondent gives an awareness answer
(`saw_info`, from qc5_1) and thirteen action answers (qc6.1–13), so every
person × item lands in one of four cells:

    aware=0 act=0   Unreached    never told, never did
    aware=1 act=0   THE GAP      told, did not act        <- the addressable market
    aware=1 act=1   Converted    told, and did
    aware=0 act=1   Intrinsic    did it without prompting

Two things come out of that:

* per item, a **conversion rate** P(act | aware) — which actions information
  actually turns into behaviour, and which it does not. This is what should
  order the product roadmap: build the modules where information alone fails.
* per person, **PGI** — the share of the actions they were aware of but had not
  taken, so a high PGI marks someone already convinced and worth nudging.

Everything here is a pure transform. No file I/O, no plotting.

Note on causality: this is cross-sectional and self-reported. A high conversion
rate means awareness and action co-occur, not that the information caused the
action — people who act may simply be the sort who also seek information out.
Reported as association throughout; see the limitations section of the brief.
"""
from __future__ import annotations

import pandas as pd

from actionwise.config import QC6_ITEMS, QC6_LABELS
from actionwise.weighting import effective_n, share_ci, weighted_share

ACTION_COLS = [f"act_{name}" for name in QC6_ITEMS.values()]

CELL_NAMES = {
    (False, False): "unreached",
    (True, False): "gap",
    (True, True): "converted",
    (False, True): "intrinsic",
}


def gap_table(df: pd.DataFrame, weight: str = "w_eu",
              aware_col: str = "saw_info") -> pd.DataFrame:
    """One row per action item: how often it is done, and how that varies by awareness.

    Respondents who gave no usable awareness answer are excluded from the
    by-awareness columns (they cannot be placed on either side of the contrast)
    but still count towards `pct_did_overall`.
    """
    aware = df[aware_col].astype("boolean")
    seen = df[aware.fillna(False)]
    unseen = df[(~aware).fillna(False)]

    rows = []
    for col in ACTION_COLS:
        name = col.removeprefix("act_")
        p_all = weighted_share(df, col, weight)
        p_aware = weighted_share(seen, col, weight)
        p_unaware = weighted_share(unseen, col, weight)

        n_eff_aware = effective_n(seen, weight, subset=seen[col].notna())
        lo, hi = share_ci(p_aware, n_eff_aware)

        rows.append(
            {
                "item": name,
                "label": QC6_LABELS.get(name, name),
                "pct_did_overall": p_all,
                "pct_did_if_aware": p_aware,
                "pct_did_if_not_aware": p_unaware,
                # Conversion: of those who saw information, how many acted.
                "conversion": p_aware,
                # The gap: saw information and did NOT act. The addressable share.
                "gap": 1 - p_aware if pd.notna(p_aware) else float("nan"),
                # Lift: how many times more likely to have acted, if aware.
                "lift": (p_aware / p_unaware) if p_unaware else float("nan"),
                "ci_low": lo,
                "ci_high": hi,
                "n_aware_rows": int(seen[col].notna().sum()),
                "n_unaware_rows": int(unseen[col].notna().sum()),
            }
        )

    return (
        pd.DataFrame(rows)
        .sort_values("conversion", ascending=False)
        .reset_index(drop=True)
    )


def gap_cells(df: pd.DataFrame, weight: str = "w_eu",
              aware_col: str = "saw_info") -> pd.DataFrame:
    """The four-cell awareness x action matrix, pooled over all 13 items.

    Weighted shares of all person-item observations where both answers exist.
    """
    aware = df[aware_col].astype("boolean")
    w = pd.to_numeric(df[weight], errors="coerce")

    totals = {k: 0.0 for k in CELL_NAMES.values()}
    for col in ACTION_COLS:
        act = df[col].astype("boolean")
        usable = aware.notna() & act.notna() & w.notna() & (w > 0)
        for (a, d), cell in CELL_NAMES.items():
            mask = usable & (aware == a) & (act == d)
            totals[cell] += float(w[mask].sum())

    grand = sum(totals.values())
    return pd.DataFrame(
        [
            {
                "cell": cell,
                "meaning": meaning,
                "weighted_share": (totals[cell] / grand) if grand else float("nan"),
            }
            for cell, meaning in [
                ("converted", "aware and acted"),
                ("gap", "aware but did NOT act  <- addressable"),
                ("intrinsic", "acted without being aware"),
                ("unreached", "neither aware nor acted"),
            ]
        ]
    )


def person_pgi(df: pd.DataFrame, difficulty: dict[str, float] | None = None) -> pd.Series:
    """Per-respondent Preparedness Gap Index in [0, 1].

    Share of the actions a person was aware of that they had not taken. Optionally
    weighted by item difficulty (from the IRT item bank in Phase 5) so that
    skipping a hard action counts for less than skipping an easy one.

    Null for respondents with no usable awareness answer, or who report awareness
    of nothing — there is no gap to measure, and imputing zero would look like
    perfect readiness.
    """
    aware = df["saw_info"].astype("boolean")
    weights = {c: 1.0 for c in ACTION_COLS}
    if difficulty:
        for c in ACTION_COLS:
            weights[c] = float(difficulty.get(c.removeprefix("act_"), 1.0))

    acted = df[ACTION_COLS].astype("Float64")
    w = pd.Series(weights)

    answered = acted.notna()
    denom = (answered * w).sum(axis=1)
    not_done = ((acted == 0) * w).sum(axis=1)

    pgi = (not_done / denom).where(denom > 0)
    return pgi.where(aware.fillna(False)).astype("Float64")
