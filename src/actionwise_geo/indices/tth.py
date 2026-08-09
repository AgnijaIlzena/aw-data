"""TTH — Time-to-Help: minutes from the nearest depot, along real roads.

The project's core index. For every populated 1 km cell:

    TTH       = shortest travel time from any of the 87 depots
    response  = TTH + TURNOUT_MINUTES        (MK 297 p. 5 — 90 seconds)

Computed with a single multi-source Dijkstra. `scipy.sparse.csgraph.dijkstra`
with `min_only=True` treats all 87 depots as one source set and returns each
node's distance to its nearest — one pass over the network, not 87.

**Every figure here is reported beside a straight-line baseline.** If network
routing does not beat "distance to the nearest depot as the crow flies", then
1.38M edges of machinery added nothing, and that is worth knowing rather than
assuming. It is the same discipline as project #1 reporting a majority-class
baseline next to every model.

Pure transforms. No I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree

from actionwise_geo.config import (
    ARRIVAL_TARGET_SERVED_MIN,
    ARRIVAL_TARGET_UNSERVED_MIN,
    TURNOUT_MINUTES,
)
from actionwise_geo.network.graph import RoadGraph

# Speed for the straight-line comparator. Deliberately generous — the baseline
# should be hard to beat, not a straw man.
BASELINE_SPEED_KMH = 60.0


def time_from_nearest_depot(graph: RoadGraph, depot_nodes) -> np.ndarray:
    """Minutes from the nearest depot to every node in the graph.

    Args:
        graph: the routable network.
        depot_nodes: node *positions* (not OSM ids) of the depots.

    Returns:
        Array of length `graph.n_nodes`; `inf` for nodes no depot can reach.
        Infinities are preserved rather than filled — an unreachable node is a
        finding about the network, and replacing it with a large number would
        silently turn it into a slow journey.
    """
    sources = np.asarray([n for n in np.asarray(depot_nodes) if n >= 0], dtype=np.int32)
    if sources.size == 0:
        raise ValueError("no depot snapped to the network — nothing to route from")

    return sparse.csgraph.dijkstra(
        graph.matrix, directed=True, indices=sources, min_only=True
    )


def distance_from_nearest_depot(graph: RoadGraph, depot_nodes) -> np.ndarray:
    """Metres along the road from the nearest depot to every node.

    A second pass, weighted by length instead of time, so the **geometric**
    detour can be measured on its own.

    This matters more than it looks. Comparing network *time* against a
    straight line at an assumed speed produces one number that mixes two
    unrelated things: how much the roads wind, and how wrong the assumed speed
    was. Measured on this network they very nearly cancel — the composite lands
    at 1.00, which reads as "routing adds nothing" and is not what is happening.
    Distance-over-distance has no speed in it and cannot be confounded that way.
    """
    sources = np.asarray([n for n in np.asarray(depot_nodes) if n >= 0], dtype=np.int32)
    if sources.size == 0:
        raise ValueError("no depot snapped to the network — nothing to route from")

    return sparse.csgraph.dijkstra(
        graph.matrix_m, directed=True, indices=sources, min_only=True
    )


def straight_line_metres(points, depots) -> pd.Series:
    """Euclidean distance to the nearest depot, in metres.

    Both frames must be in EPSG:3059. This is the denominator of the detour
    factor and the basis of the time baseline.
    """
    usable = points.geometry.notna() & ~points.geometry.is_empty
    out = pd.Series(np.nan, index=points.index, dtype=float)
    if not usable.any():
        return out

    tree = cKDTree(np.column_stack([depots.geometry.x, depots.geometry.y]))
    query = np.column_stack([
        points.loc[usable].geometry.x.to_numpy(),
        points.loc[usable].geometry.y.to_numpy(),
    ])
    distance_m, _ = tree.query(query, k=1)
    out.loc[usable] = distance_m
    return out


def straight_line_minutes(points, depots, speed_kmh: float = BASELINE_SPEED_KMH
                          ) -> pd.Series:
    """The naive comparator: crow-flies distance at one assumed speed.

    What an analyst with a ruler would produce. The network model has to beat it
    to have earned its complexity — but read `detour_factor` alongside, because
    this one number carries the assumed speed inside it.
    """
    return (straight_line_metres(points, depots) / 1000.0) / speed_kmh * 60.0


def cell_travel_times(cells, snapped: pd.DataFrame, node_minutes: np.ndarray,
                      depots=None, node_metres: np.ndarray | None = None,
                      turnout_minutes: float = TURNOUT_MINUTES,
                      audit=None) -> tuple[pd.DataFrame, "object"]:
    """Attach travel and response times to grid cells.

    Args:
        cells: populated grid cells in EPSG:3059.
        snapped: output of `network.snap.snap_points` for the same cells.
        node_minutes: output of `time_from_nearest_depot`.
        depots: if given, the straight-line baseline is computed alongside.
        turnout_minutes: MK 297 p. 5 — 90 seconds from dispatch to leaving the
            garage. Travel time and response time are kept as separate columns
            so neither is ever quietly reported as the other.
        audit: an `Audit` to append to.

    Returns:
        `(frame, audit)` with `tth_minutes`, `response_minutes`,
        `snap_distance_m`, `snap_suspect`, `reachable`, and — when `depots` is
        supplied — `baseline_minutes` and `network_penalty` (the ratio of the
        two, which is how much the road network costs over a straight line).
    """
    from actionwise.data.cleaner_eb547 import Audit

    audit = audit or Audit()
    out = pd.DataFrame(index=cells.index)

    index = snapped["node_index"].reindex(cells.index).fillna(-1).astype(int)
    minutes = np.full(len(cells), np.inf)
    found = index.to_numpy() >= 0
    minutes[found] = node_minutes[index.to_numpy()[found]]

    out["tth_minutes"] = np.where(np.isinf(minutes), np.nan, minutes)
    out["reachable"] = np.isfinite(minutes)
    out["response_minutes"] = out["tth_minutes"] + turnout_minutes
    out["snap_distance_m"] = snapped["snap_distance_m"].reindex(cells.index)
    out["snap_suspect"] = snapped["snap_suspect"].reindex(cells.index).fillna(False)

    unreachable = int((~out["reachable"]).sum())
    unreachable_pop = int(cells.loc[~out["reachable"], "T"].sum()) if "T" in cells else 0
    audit.record(
        step="compute_tth",
        rows_in=len(cells),
        rows_out=len(out),
        cells_nulled=unreachable,
        reason=(
            f"{unreachable} cell(s) holding {unreachable_pop:,} people could not be "
            "reached from any depot — kept as null, not as a large number, because "
            "an unreachable cell is a fact about the network, not a slow journey; "
            f"response = travel + {turnout_minutes} min turnout (MK 297 p. 5)"
        ),
    )

    if depots is not None:
        crow_m = straight_line_metres(cells, depots)
        out["straight_line_m"] = crow_m
        out["baseline_minutes"] = (crow_m / 1000.0) / BASELINE_SPEED_KMH * 60.0
        out["time_ratio"] = (out["tth_minutes"] / out["baseline_minutes"]).replace(
            [np.inf, -np.inf], np.nan
        )

        if node_metres is not None:
            road_m = np.full(len(cells), np.nan)
            road_m[found] = node_metres[index.to_numpy()[found]]
            road_m[np.isinf(road_m)] = np.nan
            out["road_m"] = road_m
            # Pure geometry: no speed in the numerator or the denominator, so it
            # cannot be confounded by the speed model the way `time_ratio` is.
            out["detour_factor"] = (
                pd.Series(road_m, index=out.index) / crow_m
            ).replace([np.inf, -np.inf], np.nan)

        audit.record(
            step="compute_baseline",
            rows_in=len(out),
            rows_out=len(out),
            cells_nulled=int(out["baseline_minutes"].isna().sum()),
            reason=(
                f"straight-line comparator at {BASELINE_SPEED_KMH:.0f} km/h "
                "(time_ratio) plus the speed-free geometric detour "
                "(detour_factor); the two are reported separately because a "
                "single time comparison cannot tell a winding road apart from a "
                "badly guessed baseline speed"
            ),
        )
    return out, audit


def coverage_summary(cells: pd.DataFrame, travel: pd.DataFrame,
                     population_col: str = "T") -> pd.DataFrame:
    """Population within each legal threshold — the headline table.

    Uses **response** time (travel + turnout), because that is what the
    regulation's clock measures. Reported over the mappable population only.
    """
    population = cells[population_col].reindex(travel.index).fillna(0)
    total = float(population.sum())

    rows = []
    for label, limit in (
        ("within 8 min (served settlements)", ARRIVAL_TARGET_SERVED_MIN),
        ("within 23 min (elsewhere)", ARRIVAL_TARGET_UNSERVED_MIN),
    ):
        inside = travel["response_minutes"] <= limit
        covered = float(population[inside.fillna(False)].sum())
        rows.append({
            "threshold": label,
            "minutes": limit,
            "population": int(covered),
            "share": covered / total if total else np.nan,
        })

    beyond = travel["response_minutes"] > ARRIVAL_TARGET_UNSERVED_MIN
    unreachable = ~travel["reachable"]
    rows.append({
        "threshold": "beyond 23 min or unreachable",
        "minutes": np.nan,
        "population": int(population[(beyond | unreachable).fillna(True)].sum()),
        "share": float(population[(beyond | unreachable).fillna(True)].sum()) / total
        if total else np.nan,
    })
    return pd.DataFrame(rows)


def baseline_comparison(travel: pd.DataFrame, population: pd.Series) -> pd.DataFrame:
    """Network model vs straight line, decomposed — reported beside every figure.

    Two ratios, and reading only the first is how you reach a wrong conclusion:

      * `time_ratio` — network minutes over crow-flies minutes at an assumed
        speed. Confounded: it mixes the road detour with the speed guess.
      * `detour_factor` — network metres over crow-flies metres. Pure geometry,
        no speed anywhere, so it answers "how much do the roads wind" on its own.

    On this network the time ratio sits near 1.0 while the detour is materially
    above it. Quoting the first alone would say the routing was decorative; the
    second shows the roads genuinely wind and the baseline's 60 km/h simply
    happened to offset it.
    """
    usable = travel["tth_minutes"].notna() & travel["baseline_minutes"].notna()
    subset = travel[usable]
    weights = population.reindex(subset.index).fillna(0)

    def weighted_mean(column: str) -> float:
        if weights.sum() == 0 or column not in subset:
            return float("nan")
        return float((subset[column] * weights).sum() / weights.sum())

    row = {
        "network_mean_min": weighted_mean("tth_minutes"),
        "baseline_mean_min": weighted_mean("baseline_minutes"),
        "median_time_ratio": float(subset["time_ratio"].median()),
        "cells": int(len(subset)),
    }
    if "detour_factor" in subset:
        detour = subset["detour_factor"].replace([np.inf, -np.inf], np.nan).dropna()
        row["median_detour"] = float(detour.median())
        row["p90_detour"] = float(detour.quantile(0.9))
    return pd.DataFrame([row])
