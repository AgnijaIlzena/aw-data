"""Settlements — which cells the 8-minute standard applies to.

MK 297 p. 6.1 grants eight minutes "pilsētā, ciemā un mazciemā, kur IR Valsts
ugunsdzēsības un glābšanas dienesta daļa vai postenis": in the **settlement**
holding a unit. Not the municipality — three Rīga suburbs have no depot of their
own, and Ventspils city and Ventspils novads are different territories with very
different access.

So settlements have to be delineated. They are grown by **contiguity on the
census grid** rather than by drawing a radius around a town centre, because a
radius is a guess and contiguity is a measurement: it follows ribbon development
along a road, and it stops where the houses stop.

A cluster becomes "served" when it contains a depot. Everything else falls under
p. 6.2 and its 23 minutes.

Pure transforms over the grid. No I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import sparse

from actionwise_geo.config import (
    ARRIVAL_TARGET_SERVED_MIN,
    ARRIVAL_TARGET_UNSERVED_MIN,
    CRS_ETRS89_LAEA,
    POPGRID_CELL_M,
    SETTLEMENT_CONNECTIVITY,
    SETTLEMENT_DENSITY_FLOOR,
)

# 8-connectivity as offsets; only half are needed since the graph is undirected.
_NEIGHBOURS_8 = ((1, 0), (0, 1), (1, 1), (1, -1))
_NEIGHBOURS_4 = ((1, 0), (0, 1))


def lattice_clusters(cells: pd.DataFrame,
                     min_density: float = SETTLEMENT_DENSITY_FLOOR,
                     connectivity: int = SETTLEMENT_CONNECTIVITY,
                     within: pd.Series | None = None) -> pd.Series:
    """Label contiguous groups of populated cells above a density floor.

    Runs on the EPSG:3035 lattice indices (`grid_i`, `grid_j`), where
    neighbouring cells differ by one. Reprojecting to 3059 rotates the grid, so
    adjacency there would have to be recovered by tolerance-matching float
    coordinates — this way it is exact integer arithmetic.

    Args:
        cells: populated cells with `grid_i`, `grid_j`, `density`.
        min_density: people per km² for a cell to count as built-up. Without a
            floor the whole country becomes one settlement holding 88.5% of the
            population — see `config.SETTLEMENT_DENSITY_FLOOR`.
        connectivity: 8 (default) or 4.
        within: optional grouping — usually the municipality — that a settlement
            may not cross. **Load-bearing.** Pure contiguity fuses Salaspils,
            Ķekava and Mārupe into the Rīga blob along the built-up corridors,
            and those towns then inherit the 8-minute standard from Rīga's
            depots while having none of their own. That is not what MK 297 says:
            its unit is the named pilsēta/ciems/mazciems, and p. 6.2 explicitly
            contrasts "citā novada teritorijā". Municipality boundaries are the
            authoritative split available, so a settlement stops at one.

    Returns:
        Cluster label per row, -1 for cells below the floor.
    """
    labels = pd.Series(-1, index=cells.index, dtype=int)
    qualifying = cells[
        (cells["density"] >= min_density) & cells["grid_i"].notna()
    ]
    if qualifying.empty:
        return labels

    i = qualifying["grid_i"].astype(int).to_numpy()
    j = qualifying["grid_j"].astype(int).to_numpy()
    position = {(a, b): k for k, (a, b) in enumerate(zip(i, j))}

    if within is not None:
        # Cells only connect when they share a grouping value, so a cluster
        # cannot straddle a municipality boundary.
        group_of = within.reindex(qualifying.index).to_numpy()
    else:
        group_of = None

    offsets = _NEIGHBOURS_8 if connectivity == 8 else _NEIGHBOURS_4
    rows, cols = [], []
    for (a, b), k in position.items():
        for da, db in offsets:
            neighbour = position.get((a + da, b + db))
            if neighbour is None:
                continue
            if group_of is not None:
                left, right = group_of[k], group_of[neighbour]
                if pd.isna(left) or pd.isna(right) or left != right:
                    continue
            rows.append(k)
            cols.append(neighbour)

    n = len(position)
    adjacency = sparse.coo_matrix(
        (np.ones(len(rows)), (rows, cols)), shape=(n, n)
    )
    _, component = sparse.csgraph.connected_components(adjacency, directed=False)
    labels.loc[qualifying.index] = component
    return labels


def depot_lattice_cells(depots) -> pd.DataFrame:
    """Each depot's position on the EPSG:3035 lattice.

    Depots arrive in EPSG:3059 and the grid lives on the 3035 lattice, so they
    are reprojected rather than the grid — the lattice is the thing that must
    stay exact.
    """
    projected = depots.to_crs(epsg=CRS_ETRS89_LAEA)
    return pd.DataFrame(
        {
            "grid_i": np.floor(projected.geometry.x / POPGRID_CELL_M).astype("Int64"),
            "grid_j": np.floor(projected.geometry.y / POPGRID_CELL_M).astype("Int64"),
        },
        index=depots.index,
    )


def served_settlements(cells: pd.DataFrame, labels: pd.Series, depots,
                       audit=None) -> tuple[pd.Series, "object"]:
    """Mark cells whose settlement contains a depot.

    A depot may sit in a cell that is empty or below the density floor — a
    station on the edge of a village, for instance. Such a depot is matched to a
    neighbouring cluster within one cell before being treated as serving nothing,
    since "the depot is 400 m outside the settlement it serves" is a mapping
    artefact rather than a legal fact.

    Returns:
        `(served, audit)` — boolean per cell.
    """
    from actionwise.data.cleaner_eb547 import Audit

    audit = audit or Audit()

    lattice = depot_lattice_cells(depots)
    cluster_of: dict[tuple[int, int], int] = {}
    valid = labels >= 0
    for (a, b), label in zip(
        zip(cells.loc[valid, "grid_i"].astype(int),
            cells.loc[valid, "grid_j"].astype(int)),
        labels[valid],
    ):
        cluster_of[(a, b)] = int(label)

    served_labels: set[int] = set()
    matched_directly = adopted = orphaned = 0

    for _, row in lattice.iterrows():
        if pd.isna(row["grid_i"]):
            orphaned += 1
            continue
        a, b = int(row["grid_i"]), int(row["grid_j"])
        label = cluster_of.get((a, b))
        if label is not None:
            served_labels.add(label)
            matched_directly += 1
            continue
        # One-cell search: a depot just outside the built-up edge still serves it.
        neighbours = {
            cluster_of.get((a + da, b + db))
            for da in (-1, 0, 1)
            for db in (-1, 0, 1)
        } - {None}
        if neighbours:
            served_labels.update(int(n) for n in neighbours)
            adopted += 1
        else:
            orphaned += 1

    served = labels.isin(served_labels) & (labels >= 0)

    audit.record(
        step="mark_served_settlements",
        rows_in=len(cells),
        rows_out=int(served.sum()),
        cells_nulled=orphaned,
        reason=(
            f"{len(served_labels)} settlement(s) contain a depot: {matched_directly} "
            f"depot(s) matched their own cell, {adopted} adopted an adjacent "
            f"settlement, {orphaned} sit in no built-up area at all. Cells in a "
            "served settlement fall under MK 297 p. 6.1 (8 min); everything else "
            "under p. 6.2 (23 min)"
        ),
    )
    return served, audit


def applicable_target(served: pd.Series) -> pd.Series:
    """The legal arrival target per cell, in minutes.

    The whole point of the module: reporting one national "% within 8 minutes"
    would judge rural Latvia against a standard the law does not apply to it.
    """
    return pd.Series(
        np.where(served, ARRIVAL_TARGET_SERVED_MIN, ARRIVAL_TARGET_UNSERVED_MIN),
        index=served.index,
        dtype=float,
    )


def settlement_summary(cells: pd.DataFrame, labels: pd.Series,
                       served: pd.Series, population_col: str = "T") -> pd.DataFrame:
    """One row per settlement class, for the model card."""
    population = cells[population_col]
    total = float(population.sum())

    groups = {
        "served settlement (8 min)": served,
        "unserved settlement (23 min)": (labels >= 0) & ~served,
        "outside any settlement (23 min)": labels < 0,
    }
    return pd.DataFrame([
        {
            "class": name,
            "cells": int(mask.sum()),
            "settlements": int(labels[mask].nunique()) if name != "outside any settlement (23 min)" else 0,
            "population": int(population[mask].sum()),
            "share": float(population[mask].sum() / total) if total else np.nan,
        }
        for name, mask in groups.items()
    ])
