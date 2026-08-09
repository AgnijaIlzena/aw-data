"""Attach points to the road graph.

Both ends of every travel time go through here: the 87 depots, and the ~29,600
populated grid cells. A 1 km cell centroid should sit close to a road, and one
that does not is a data problem — an offshore centroid, or a node the extract
never joined to the network. Those get flagged and counted, never absorbed,
because a cell snapped to a road 30 km away produces a travel time that is
precise, plausible and meaningless.

Uses a KD-tree over node coordinates in EPSG:3059, so distances are metres.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from actionwise_geo.config import MAX_SNAP_DISTANCE_M
from actionwise_geo.network.graph import RoadGraph


def snap_points(points, graph: RoadGraph,
                max_distance_m: float = MAX_SNAP_DISTANCE_M,
                audit=None) -> tuple[pd.DataFrame, "object"]:
    """Find each point's nearest graph node.

    Args:
        points: a GeoDataFrame in EPSG:3059. Null geometries are allowed and
            come back unsnapped rather than raising — the unallocated population
            row is exactly such a case.
        graph: the road graph, whose `coords` are metric.
        max_distance_m: beyond this a snap is reported as suspect. It does not
            drop the row; the caller decides, with the count in front of it.
        audit: an `Audit` to append to.

    Returns:
        `(frame, audit)` indexed like `points`, with `node_index` (position in
        the graph, -1 if unsnapped), `node_id` (OSM id), `snap_distance_m`, and
        `snap_suspect`.
    """
    from actionwise.data.cleaner_eb547 import Audit

    audit = audit or Audit()

    if points.crs is not None and points.crs.to_epsg() != 3059:
        raise ValueError(
            f"points are EPSG:{points.crs.to_epsg()}; snapping needs EPSG:3059 or "
            "the distances come back in degrees and every threshold is meaningless"
        )

    usable = points.geometry.notna() & ~points.geometry.is_empty
    result = pd.DataFrame(
        {
            "node_index": -1,
            "node_id": pd.NA,
            "snap_distance_m": np.nan,
            "snap_suspect": False,
        },
        index=points.index,
    )

    if usable.any():
        tree = cKDTree(graph.coords)
        query = np.column_stack([
            points.loc[usable].geometry.x.to_numpy(),
            points.loc[usable].geometry.y.to_numpy(),
        ])
        distance, index = tree.query(query, k=1)

        result.loc[usable, "node_index"] = index.astype(int)
        result.loc[usable, "node_id"] = graph.node_ids[index]
        result.loc[usable, "snap_distance_m"] = distance
        result.loc[usable, "snap_suspect"] = distance > max_distance_m

    suspect = int(result["snap_suspect"].sum())
    unsnapped = int((result["node_index"] < 0).sum())
    worst = result["snap_distance_m"].max()

    audit.record(
        step="snap_to_network",
        rows_in=len(points),
        rows_out=len(result),
        cells_nulled=unsnapped,
        reason=(
            f"nearest node within {max_distance_m:.0f} m for "
            f"{len(result) - suspect - unsnapped} of {len(points)} point(s); "
            f"{suspect} beyond it (worst {worst:.0f} m) flagged not dropped; "
            f"{unsnapped} had no geometry to snap"
        ),
    )
    return result, audit


def snap_quality(snapped: pd.DataFrame, weights: pd.Series | None = None) -> dict:
    """Summarise snapping for the model card.

    Args:
        snapped: output of `snap_points`.
        weights: optional population per row. Reported alongside the row counts
            because a hundred empty cells snapping badly does not matter and one
            populated one does.
    """
    distance = snapped["snap_distance_m"].dropna()
    summary = {
        "points": int(len(snapped)),
        "snapped": int((snapped["node_index"] >= 0).sum()),
        "suspect": int(snapped["snap_suspect"].sum()),
        "median_m": float(distance.median()) if len(distance) else float("nan"),
        "p99_m": float(distance.quantile(0.99)) if len(distance) else float("nan"),
        "max_m": float(distance.max()) if len(distance) else float("nan"),
    }
    if weights is not None:
        aligned = weights.reindex(snapped.index).fillna(0)
        total = float(aligned.sum())
        summary["population"] = total
        summary["population_suspect"] = float(aligned[snapped["snap_suspect"]].sum())
        summary["population_suspect_share"] = (
            summary["population_suspect"] / total if total else float("nan")
        )
    return summary
