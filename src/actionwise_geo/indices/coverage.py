"""CCI — Coverage Compliance: population reaching help within its *own* legal target.

The distinction that makes this index worth having. Reporting one national
"share within 8 minutes" judges rural Latvia against a standard the law does not
apply to it; reporting "share within 23 minutes" flatters the cities. MK 297
sets two targets and assigns each place one of them, so compliance has to be
measured cell by cell against the target that actually binds there.

    CCI = population whose response time <= its applicable target
          ------------------------------------------------------
                     mappable population

Response time, not travel time: the regulation's clock starts at dispatch, and
90 seconds of turnout (p. 5) belongs inside it.

Pure transforms. No I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from actionwise_geo.config import (
    ARRIVAL_TARGET_SERVED_MIN,
    ARRIVAL_TARGET_UNSERVED_MIN,
    POPGRID_AGE_BANDS,
)


def compliance(cells: pd.DataFrame, travel: pd.DataFrame, target: pd.Series,
               population_col: str = "T") -> pd.DataFrame:
    """National compliance, split by which target applies.

    Returns one row per target plus a total. `population` is the mappable
    population — the unallocated row has no location and cannot be routed to.
    """
    population = cells[population_col].reindex(travel.index).fillna(0)
    response = travel["response_minutes"]
    within = (response <= target.reindex(travel.index)).fillna(False)

    rows = []
    for label, minutes in (
        ("served settlement", ARRIVAL_TARGET_SERVED_MIN),
        ("elsewhere", ARRIVAL_TARGET_UNSERVED_MIN),
    ):
        group = target.reindex(travel.index) == minutes
        base = float(population[group].sum())
        met = float(population[group & within].sum())
        rows.append({
            "applies_to": label,
            "target_min": minutes,
            "population": int(base),
            "within_target": int(met),
            "compliance": met / base if base else np.nan,
        })

    total = float(population.sum())
    met = float(population[within].sum())
    rows.append({
        "applies_to": "ALL (CCI)",
        "target_min": np.nan,
        "population": int(total),
        "within_target": int(met),
        "compliance": met / total if total else np.nan,
    })
    return pd.DataFrame(rows)


def compliance_by_group(cells: pd.DataFrame, travel: pd.DataFrame,
                        target: pd.Series, group: pd.Series,
                        population_col: str = "T",
                        min_population: int = 500) -> pd.DataFrame:
    """Compliance per municipality (or any other grouping).

    Groups below `min_population` are flagged rather than dropped — the same
    `thin_cell` convention project #1 uses in `indices/percentiles.py`, so a
    percentage computed on a handful of people cannot be quoted as if it were
    solid.
    """
    population = cells[population_col].reindex(travel.index).fillna(0)
    within = (travel["response_minutes"] <= target.reindex(travel.index)).fillna(False)

    frame = pd.DataFrame({
        "group": group.reindex(travel.index),
        "population": population,
        "within": population.where(within, 0.0),
        "response": travel["response_minutes"],
        "target": target.reindex(travel.index),
    }).dropna(subset=["group"])

    grouped = frame.groupby("group", observed=True)
    out = pd.DataFrame({
        "population": grouped["population"].sum(),
        "within_target": grouped["within"].sum(),
        "mean_response_min": grouped.apply(
            lambda d: (d["response"] * d["population"]).sum() / d["population"].sum()
            if d["population"].sum() else np.nan,
            include_groups=False,
        ),
        "share_on_8min_standard": grouped.apply(
            lambda d: (d["population"][d["target"] == ARRIVAL_TARGET_SERVED_MIN].sum()
                       / d["population"].sum()) if d["population"].sum() else np.nan,
            include_groups=False,
        ),
    })
    out["compliance"] = out["within_target"] / out["population"]
    out["thin_cell"] = out["population"] < min_population
    return out.sort_values("compliance").reset_index()


def elderly_compliance(cells: pd.DataFrame, travel: pd.DataFrame,
                       target: pd.Series, band: str = "Y_GE65") -> pd.DataFrame:
    """The same figure for over-65s — with its coverage stated, not assumed.

    This is the sharpest version of the headline and the most fragile. The age
    bands are suppressed in 65% of populated cells, and suppression concentrates
    in **sparse** cells, which are exactly the remote ones with the longest
    response times. So the elderly figure is computed on the cells that have age
    detail, and it under-represents precisely the places where the answer would
    be worst.

    Reported as a row of its own rather than folded into a footnote: the
    `coverage` column is the share of the band's national total that this
    calculation could actually see.
    """
    if band not in cells:
        raise ValueError(f"{band} not in cells; expected one of {POPGRID_AGE_BANDS}")

    people = cells[band].reindex(travel.index)
    known = people.notna()
    response = travel["response_minutes"]
    within = (response <= target.reindex(travel.index)).fillna(False)

    total_known = float(people[known].sum())
    rows = [{
        "band": band,
        "population_with_age_detail": int(total_known),
        "within_target": int(float(people[known & within].sum())),
        "compliance": float(people[known & within].sum()) / total_known
        if total_known else np.nan,
        "cells_with_detail": int(known.sum()),
        "cells_suppressed": int((~known).sum()),
        "coverage": float(known.sum() / len(known)) if len(known) else np.nan,
    }]
    out = pd.DataFrame(rows)
    out.attrs["caveat"] = (
        "Age bands are suppressed in sparse cells, which are the remote ones with "
        "the longest response times. This figure therefore under-represents the "
        "worst-served over-65s; treat it as an upper bound on compliance."
    )
    return out


def floor_sensitivity(cells: pd.DataFrame, travel: pd.DataFrame, depots,
                      floors, population_col: str = "T",
                      within: pd.Series | None = None) -> pd.DataFrame:
    """CCI recomputed across settlement density floors.

    Where a settlement ends is a judgement, and it moves which cells are held to
    8 minutes rather than 23. Rather than defend one floor, the index is reported
    across the range and the spread stated — the same reasoning as the emergency
    speed factor.
    """
    from actionwise_geo.indices.settlements import (
        applicable_target,
        lattice_clusters,
        served_settlements,
    )

    rows = []
    for floor in floors:
        labels = lattice_clusters(cells, min_density=floor, within=within)
        served, _ = served_settlements(cells, labels, depots)
        target = applicable_target(served)
        national = compliance(cells, travel, target, population_col)
        overall = national[national["applies_to"] == "ALL (CCI)"].iloc[0]
        on_eight = national[national["applies_to"] == "served settlement"].iloc[0]
        rows.append({
            "density_floor": floor,
            "settlements_served": int(labels[served].nunique()),
            "population_on_8min": int(on_eight["population"]),
            "share_on_8min": on_eight["population"] / overall["population"]
            if overall["population"] else np.nan,
            "cci": overall["compliance"],
        })
    return pd.DataFrame(rows)
