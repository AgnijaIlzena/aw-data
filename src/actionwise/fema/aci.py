"""ACI — Action Conversion Index: does hearing about a measure make people do it?

This is the one index EB547 cannot produce. Europe asks awareness **once**
(`qc5_1`, "have you seen any preparedness information in the last 12 months"),
so its per-item conversion figures conflate "saw a poster about water storage"
with "saw a campaign about neighbour coordination". FEMA asks awareness and
action over the *same twelve items*, so conversion can be computed per message:

    ACI_i = P(did item i | was aware of item i)

The four cells, exactly as in `indices/pgi.py` but now genuinely item-specific:

    aware=0 act=0   unreached
    aware=1 act=0   THE GAP      heard about *this*, did not do *this*
    aware=1 act=1   converted
    aware=0 act=1   intrinsic    did it without having heard about it

Pure transforms. No I/O.

Two cautions carried in the outputs rather than left to the reader:

* **Not poolable with EB547.** FEMA measures a 12-month flow, EB547 a lifetime
  stock. Directions are comparable; levels are not.
* **Repeated cross-section, not a panel.** Stacking eleven years gives eleven
  independent samples, not people followed over time. Trends here are aggregate
  trends; nothing supports an individual transition model.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from actionwise.fema.config import EB547_RECALL_WINDOW, FEMA_RECALL_WINDOW, ITEMS
from actionwise.weighting import effective_n, share_ci


def _binary(series: pd.Series) -> pd.Series:
    """Coerce FEMA's yes/no coding to 1/0, leaving anything else null.

    Years differ: some code 1/0, some 1/2, some use strings. Values outside the
    known vocabularies become null rather than being guessed at.
    """
    s = series.copy()
    # Test for "not numeric" rather than "is object": modern pandas infers a
    # dedicated string dtype, so `dtype == object` misses text columns entirely
    # and sends "Yes"/"No" down the numeric path, where they silently become null.
    if not pd.api.types.is_numeric_dtype(s):
        text = s.astype("string").str.strip().str.lower()
        mapped = text.map({"yes": 1.0, "no": 0.0, "y": 1.0, "n": 0.0,
                           "true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0, "2": 0.0})
        return mapped.astype("Float64")
    num = pd.to_numeric(s, errors="coerce")
    # 1/2 coding (1 = yes, 2 = no) is common in CATI files.
    if num.dropna().isin([1, 2]).all() and (num == 2).any():
        return num.map({1: 1.0, 2: 0.0}).astype("Float64")
    return num.where(num.isin([0, 1])).astype("Float64")


def aci_table(
    df: pd.DataFrame,
    mapping: pd.DataFrame,
    weight_col: str | None = None,
) -> pd.DataFrame:
    """Per-item conversion, gap, lift and the four cells.

    Args:
        df: stacked FEMA responses.
        mapping: output of `loader.discover_columns` — item -> (awareness, action).
        weight_col: design weight; unweighted if None, and said so in the output.
    """
    weights = (
        pd.to_numeric(df[weight_col], errors="coerce")
        if weight_col and weight_col in df.columns
        else pd.Series(1.0, index=df.index)
    )

    rows = []
    for _, m in mapping.drop_duplicates("item").iterrows():
        if not m["paired"]:
            continue
        aware = _binary(df[m["awareness_col"]])
        acted = _binary(df[m["action_col"]])

        usable = aware.notna() & acted.notna() & weights.notna() & (weights > 0)
        a, d, w = aware[usable], acted[usable], weights[usable]
        if w.sum() == 0:
            continue

        cells = {
            "converted": float(w[(a == 1) & (d == 1)].sum()),
            "gap": float(w[(a == 1) & (d == 0)].sum()),
            "intrinsic": float(w[(a == 0) & (d == 1)].sum()),
            "unreached": float(w[(a == 0) & (d == 0)].sum()),
        }
        total = sum(cells.values())
        aware_mass = cells["converted"] + cells["gap"]
        unaware_mass = cells["intrinsic"] + cells["unreached"]

        p_aware = cells["converted"] / aware_mass if aware_mass else np.nan
        p_unaware = cells["intrinsic"] / unaware_mass if unaware_mass else np.nan
        n_eff = effective_n(pd.DataFrame({"w": w}), "w")
        lo, hi = share_ci(p_aware, n_eff)

        rows.append(
            {
                "item": m["item"],
                "label": ITEMS.get(m["item"], m["item"]),
                "aci": p_aware,                      # P(did | aware of this item)
                "gap": 1 - p_aware if pd.notna(p_aware) else np.nan,
                "p_did_if_unaware": p_unaware,
                "lift": (p_aware / p_unaware) if p_unaware else np.nan,
                "ci_low": lo,
                "ci_high": hi,
                "share_aware": aware_mass / total if total else np.nan,
                "n_rows": int(usable.sum()),
                "n_eff": round(n_eff, 1),
                "weighted": weight_col is not None,
            }
        )

    return pd.DataFrame(rows).sort_values("aci", ascending=False).reset_index(drop=True)


def aci_by_year(df: pd.DataFrame, mapping: pd.DataFrame,
                weight_col: str | None = None) -> pd.DataFrame:
    """Conversion per item per year — aggregate trend, not individual change."""
    frames = []
    for year, sub in df.groupby("survey_year"):
        year_map = mapping[mapping["survey_year"] == year] if "survey_year" in mapping else mapping
        table = aci_table(sub, year_map, weight_col)
        if not table.empty:
            frames.append(table.assign(survey_year=year))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out.attrs["caveat"] = (
        "Repeated cross-section: each year samples different people. These are "
        "aggregate trends, not individual transitions."
    )
    return out


def compare_with_eb547(fema: pd.DataFrame, eu_gap_table: pd.DataFrame,
                       crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Put the two surveys side by side — as a comparison, never a pooled average.

    `crosswalk` maps EB547 item names to FEMA item names. Only rows the crosswalk
    marks as a clean 1:1 match are compared; partial matches are carried through
    with their note so the reader can see why a pair is not strictly equivalent.
    """
    merged = (
        crosswalk.merge(fema[["item", "aci", "lift"]], left_on="fema_item", right_on="item",
                        how="inner", suffixes=("", "_f"))
        .merge(eu_gap_table[["item", "conversion", "lift"]], left_on="eb547_item",
               right_on="item", how="inner", suffixes=("_fema", "_eu"))
    )
    merged["conversion_gap_pp"] = (merged["aci"] - merged["conversion"]) * 100
    merged["recall_windows_differ"] = True
    merged.attrs["warning"] = (
        f"FEMA measures a {FEMA_RECALL_WINDOW} flow; EB547 measures a "
        f"{EB547_RECALL_WINDOW} stock. Compare directions, never levels."
    )
    return merged[
        ["eb547_item", "fema_item", "match_quality", "aci", "conversion",
         "conversion_gap_pp", "lift_fema", "lift_eu", "note"]
    ]


def stage_distribution(df: pd.DataFrame, stage_col: str,
                       weight_col: str | None = None) -> pd.DataFrame:
    """The stage-of-change ladder — the second reason this phase exists.

    A validated five-level intention->action scale with no EB547 equivalent, and
    the empirical grounding for a gamified progression that currently runs on
    invented rules.
    """
    from actionwise.fema.config import STAGE_LABELS

    weights = (
        pd.to_numeric(df[weight_col], errors="coerce")
        if weight_col and weight_col in df.columns
        else pd.Series(1.0, index=df.index)
    )
    stage = pd.to_numeric(df[stage_col], errors="coerce")
    usable = stage.isin(STAGE_LABELS) & weights.notna() & (weights > 0)
    total = float(weights[usable].sum())

    return pd.DataFrame(
        [
            {
                "stage": level,
                "label": label,
                "share": float(weights[usable & (stage == level)].sum()) / total if total else np.nan,
                "n_rows": int((usable & (stage == level)).sum()),
            }
            for level, label in STAGE_LABELS.items()
        ]
    )
