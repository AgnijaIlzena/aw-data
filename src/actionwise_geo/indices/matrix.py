"""The Preparedness–Proximity matrix — where project #1 and project #2 meet.

Project #1 measures how many days a household can last (RHI, from EB547).
Project #2 measures how many minutes until help arrives (TTH, from the road
network). The pair is the reason both exist.

**Deliberately two axes, never one number.** RHI measures endurance through a
prolonged utility disruption; TTH measures arrival for an acute incident. They
are different scenarios, and dividing one by the other would produce a tidy
index that means nothing — exactly the unjustified leap `virality-code` made when
it modelled a target derived from its own features. So the output is a table with
both columns per community type, and the reader does the joining.

The join runs on community type, not geography
----------------------------------------------
EB547 carries `d25` (self-reported community type, Latvia n=1,007 across three
categories) and `region_latvia` (NUTS3, six regions). The grid carries measured
density.

`d25` is the better bridge and the one used here: every category holds n>=262,
and it maps onto the same rural/town/city distinction the density classes
describe. The NUTS3 route is **not** attempted for the full six regions, because
no verified municipality-to-NUTS3 crosswalk is available in `dati/` and inventing
one for 35 novadi would put a guess underneath the headline. Rīga (LV006) is the
one unambiguous case — it is exactly the city — so it is reported on its own.

The classes have to be calibrated before they can be compared
-------------------------------------------------------------
Measured density and self-reported community type do not agree on how Latvia
splits (52.9/21.7/25.4 against 38.9/32.1/29.1), because a resident of a dense
Rīga suburb may reasonably answer "small or middle sized town". Comparing
DEGURBA classes to `d25` classes directly would compare two different partitions.

`calibrate_density_thresholds` therefore finds the density cutoffs that reproduce
the survey's own population split, so the two sides describe the same three
groups of people. The uncalibrated DEGURBA version is reported alongside, and the
gap between them is part of the result.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# The 3-day target is a project-wide fact and lives in project #1's config.
# Imported rather than duplicated: two copies of a headline constant is how the
# dossier ends up quoting two different numbers.
from actionwise.config import RESILIENCE_TARGET_DAYS
from actionwise.weighting import effective_n, share_ci, weighted_mean
from actionwise_geo.config import DEGURBA_URBAN_CENTRE_MIN, DEGURBA_URBAN_CLUSTER_MIN

CLASSES = ("rural", "urban_cluster", "urban_centre")
D25_TO_CLASS = {1.0: "rural", 2.0: "urban_cluster", 3.0: "urban_centre"}

# Below this many effective observations a class figure is flagged rather than
# quoted — the same convention as `actionwise.indices.percentiles`.
MIN_EFFECTIVE_N = 100


def survey_class_shares(survey: pd.DataFrame, weight: str = "w_national"
                        ) -> pd.Series:
    """Weighted population share per community type, from `d25`."""
    usable = survey[survey["community_class"].notna() & survey[weight].notna()]
    grouped = usable.groupby("community_class", observed=True)[weight].sum()
    return (grouped / grouped.sum()).reindex(CLASSES)


def calibrate_density_thresholds(cells: pd.DataFrame, target_shares: pd.Series,
                                 population_col: str = "T") -> dict[str, float]:
    """Density cutoffs that reproduce the survey's own population split.

    Without this the two sides of the matrix partition Latvia differently and the
    comparison is between incomparable groups. With it, "rural" means the same
    share of people on both sides by construction, and the remaining difference
    is about response time and preparedness rather than about definitions.

    Returns:
        `{"urban_cluster_min": x, "urban_centre_min": y}` in people per km².
    """
    usable = cells[(cells[population_col] > 0) & cells["density"].notna()]
    order = usable.sort_values("density")
    cumulative = order[population_col].cumsum() / order[population_col].sum()

    rural = float(target_shares.get("rural", np.nan))
    cluster = float(target_shares.get("urban_cluster", np.nan))

    def cutoff(at: float) -> float:
        position = cumulative.searchsorted(at)
        position = min(position, len(order) - 1)
        return float(order["density"].iloc[position])

    return {
        "urban_cluster_min": cutoff(rural),
        "urban_centre_min": cutoff(rural + cluster),
    }


def classify_cells(cells: pd.DataFrame, thresholds: dict[str, float] | None = None
                   ) -> pd.Series:
    """Assign each cell a community class from its measured density."""
    cluster_min = (thresholds or {}).get("urban_cluster_min", DEGURBA_URBAN_CLUSTER_MIN)
    centre_min = (thresholds or {}).get("urban_centre_min", DEGURBA_URBAN_CENTRE_MIN)

    density = cells["density"]
    return pd.Series(
        np.select(
            [density >= centre_min, density >= cluster_min],
            ["urban_centre", "urban_cluster"],
            default="rural",
        ),
        index=cells.index,
        dtype="object",
    ).where(density.notna())


def proximity_by_class(cells: pd.DataFrame, travel: pd.DataFrame,
                       classes: pd.Series, population_col: str = "T"
                       ) -> pd.DataFrame:
    """The TTH side: response time per community class, population-weighted."""
    frame = pd.DataFrame({
        "community_class": classes.reindex(travel.index),
        "population": cells[population_col].reindex(travel.index),
        "response": travel["response_minutes"],
    }).dropna(subset=["community_class"])

    rows = []
    for name in CLASSES:
        group = frame[frame["community_class"] == name]
        weights = group["population"]
        usable = group["response"].notna() & (weights > 0)
        total = float(weights[usable].sum())
        rows.append({
            "community_class": name,
            "population": int(weights.sum()),
            "mean_response_min": float(
                (group.loc[usable, "response"] * weights[usable]).sum() / total
            ) if total else np.nan,
            "share_beyond_23min": float(
                weights[usable & (group["response"] > 23)].sum() / total
            ) if total else np.nan,
            "cells": int(len(group)),
        })
    return pd.DataFrame(rows)


def preparedness_by_class(survey: pd.DataFrame, weight: str = "w_national",
                          target_days: float = RESILIENCE_TARGET_DAYS
                          ) -> pd.DataFrame:
    """The RHI side: household endurance per community class, with intervals.

    Confidence intervals use Kish's effective sample size, not the raw row count —
    Eurobarometer weights inflate variance, so an interval built on n would be
    too narrow. `thin_cell` flags a class whose effective n falls below
    `MIN_EFFECTIVE_N`, mirroring `actionwise.indices.percentiles`.
    """
    rows = []
    for name in CLASSES:
        group = survey[(survey["community_class"] == name) & survey[weight].notna()]
        usable = group[group["rhi_days"].notna()]
        n_eff = effective_n(usable, weight) if len(usable) else 0.0

        if len(usable):
            # RHI is interval-censored, and project #1 reports it as a bracket
            # rather than a point for a reason: band 2 is literally "2-3 days", so
            # whether such a household clears a 3-day target is unknowable from
            # the answer. Collapsing to a midpoint would quietly turn the upper
            # bound into an estimate. Both bounds are carried through here.
            certain = usable.assign(_flag=(usable["rhi_band"] == 1).astype(float))
            upper = usable.assign(
                _flag=(usable["rhi_days"] < target_days).astype(float)
            )
            share_certain = weighted_mean(certain, "_flag", weight)
            share_upper = weighted_mean(upper, "_flag", weight)
            low, high = share_ci(share_upper, n_eff)
            mean_days = weighted_mean(usable, "rhi_days", weight)
        else:
            share_certain = share_upper = low = high = mean_days = np.nan

        rows.append({
            "community_class": name,
            "n": int(len(usable)),
            "n_effective": round(n_eff, 1),
            "mean_rhi_days": mean_days,
            "share_under_target_certain": share_certain,
            "share_under_target_upper": share_upper,
            "ci_low": low,
            "ci_high": high,
            "thin_cell": n_eff < MIN_EFFECTIVE_N,
        })
    return pd.DataFrame(rows)


def proximity_matrix(proximity: pd.DataFrame, preparedness: pd.DataFrame,
                     target_days: float = RESILIENCE_TARGET_DAYS
                     ) -> pd.DataFrame:
    """Both axes side by side — the deliverable neither project produces alone.

    No ratio, no composite score. The two columns answer different questions and
    the reader is trusted to hold them together:

        "In rural Latvia help takes X minutes and Y% of households could not last
         three days."
    """
    merged = proximity.merge(preparedness, on="community_class", how="outer")
    merged["community_class"] = pd.Categorical(
        merged["community_class"], categories=CLASSES, ordered=True
    )
    merged = merged.sort_values("community_class").reset_index(drop=True)
    merged.attrs["warning"] = (
        "Two axes, deliberately not combined. RHI measures endurance through a "
        "prolonged utility disruption; TTH measures arrival for an acute "
        f"incident. A ratio would imply they describe one scenario. Target for "
        f"'under target' is {target_days} days."
    )
    return merged


def riga_contrast(cells: pd.DataFrame, travel: pd.DataFrame,
                  municipality: pd.Series, survey: pd.DataFrame,
                  weight: str = "w_national") -> pd.DataFrame:
    """Rīga against the rest of Latvia — the one unambiguous NUTS3 comparison.

    LV006 is exactly the city of Rīga, so the survey's `region_latvia` and the
    map agree on it without a crosswalk. The other five regions are not attempted.
    """
    is_riga_cell = municipality.reindex(travel.index) == "Rīga"
    population = cells["T"].reindex(travel.index)

    rows = []
    for label, cell_mask, survey_mask in (
        ("Rīga (LV006)", is_riga_cell, survey["region_latvia"] == 3.0),
        ("rest of Latvia", ~is_riga_cell, survey["region_latvia"] != 3.0),
    ):
        weights = population[cell_mask.fillna(False)]
        response = travel.loc[cell_mask.fillna(False), "response_minutes"]
        usable = response.notna() & (weights > 0)
        total = float(weights[usable].sum())

        group = survey[survey_mask & survey["rhi_days"].notna()
                       & survey[weight].notna()]
        n_eff = effective_n(group, weight) if len(group) else 0.0
        rows.append({
            "area": label,
            "population": int(weights.sum()),
            "mean_response_min": float((response[usable] * weights[usable]).sum() / total)
            if total else np.nan,
            "survey_n": int(len(group)),
            "n_effective": round(n_eff, 1),
            "mean_rhi_days": weighted_mean(group, "rhi_days", weight) if len(group) else np.nan,
            "thin_cell": n_eff < MIN_EFFECTIVE_N,
        })
    return pd.DataFrame(rows)
