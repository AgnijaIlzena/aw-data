"""The routable road graph — 1.35M nodes, 1.38M edges.

Built as a scipy sparse matrix rather than a networkx graph. At this size the
difference is not stylistic: `scipy.sparse.csgraph.dijkstra` with
`min_only=True` answers "how far is every node from its nearest depot" in a
single pass over a ~30 MB matrix, where a networkx `DiGraph` of the same network
costs gigabytes and a Python-level heap.

Two correctness points that a graph library would otherwise hide:

  * **Parallel edges must take the minimum, not the sum.** Building a COO matrix
    from duplicate (u, v) pairs silently *adds* their weights, so two roads
    between the same junctions become one slower road. Deduplicated on the way in.
  * **Absent `oneway` means two-way.** 91% of edges carry no tag; treating null
    as "unknown" and dropping it would delete the network.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse

from actionwise_geo.config import CRS_WGS84, CRS_WORKING
from actionwise_geo.network.speeds import assign_speeds, travel_time_minutes

# `access=no` is a barrier. `private` and `destination` are legal restrictions
# that do not bind emergency services responding to a call, so they stay in the
# network — a modelling choice, stated here rather than buried in a filter.
BLOCKED_ACCESS = {"no"}

ONEWAY_FORWARD = {"yes", "true", "1"}
ONEWAY_REVERSE = {"-1", "reverse"}


@dataclass
class RoadGraph:
    """A routable network plus everything needed to map results back to places.

    Attributes:
        matrix: CSR travel times in minutes, shape (n_nodes, n_nodes).
        matrix_m: the same arcs weighted by metres. Carried so the *geometric*
            detour can be measured separately from the speed model. A single
            time-based comparison against a straight line cannot tell "the roads
            wind" apart from "the baseline speed was guessed badly" — the two
            effects cancel, and the composite lands near 1.0 while saying nothing.
        node_ids: OSM node ids, positionally aligned with the matrix.
        coords: node coordinates in EPSG:3059 metres, shape (n_nodes, 2), for
            snapping. Kept metric so a nearest-neighbour search returns metres.
        speed_factor: the emergency uplift these times were built with.
        provenance: where each edge's speed came from, weighted by length.
    """

    matrix: sparse.csr_matrix
    matrix_m: sparse.csr_matrix
    node_ids: np.ndarray
    coords: np.ndarray
    speed_factor: float
    provenance: pd.DataFrame

    @property
    def n_nodes(self) -> int:
        return len(self.node_ids)

    @property
    def n_edges(self) -> int:
        return int(self.matrix.nnz)

    def index_of(self, osm_ids) -> np.ndarray:
        """Positions of the given OSM node ids, -1 where absent."""
        lookup = pd.Series(np.arange(len(self.node_ids)), index=self.node_ids)
        return lookup.reindex(np.asarray(osm_ids)).fillna(-1).astype(int).to_numpy()


def build_graph(nodes, edges, speed_factor: float = 1.0,
                audit=None) -> tuple[RoadGraph, "object"]:
    """Turn pyrosm's nodes/edges into a routable sparse graph.

    Args:
        nodes: pyrosm node frame — needs `id` and geometry (EPSG:4326).
        edges: pyrosm edge frame — needs `u`, `v`, `length`, `highway`,
            `maxspeed`, `oneway`.
        speed_factor: emergency-vehicle uplift, passed to `assign_speeds`.
        audit: an `Audit` to append to.

    Returns:
        `(RoadGraph, audit)`.
    """
    from actionwise.data.cleaner_eb547 import Audit

    audit = audit or Audit()
    rows_in = len(edges)

    # ── speeds and travel times ────────────────────────────────────────────
    priced = assign_speeds(edges, factor=speed_factor)
    # NOTE: the COLUMN, not the .length property — see speeds.travel_time_minutes
    priced["travel_min"] = travel_time_minutes(priced["length"], priced["speed_kmh"])

    provenance = _provenance(priced)
    inferred = float(
        provenance.loc[provenance["speed_source"] != "tagged", "share_of_length"].sum()
    )
    audit.record(
        step="assign_speeds",
        rows_in=rows_in,
        rows_out=len(priced),
        cells_nulled=0,
        reason=(
            f"speed factor {speed_factor}x; {inferred:.0%} of network LENGTH runs on "
            "an inferred speed rather than a maxspeed tag — the dominant uncertainty "
            "in every travel time downstream"
        ),
    )

    # ── drop what cannot be routed ─────────────────────────────────────────
    usable = priced["travel_min"].notna() & (priced["travel_min"] > 0)
    if "access" in priced.columns:
        blocked = priced["access"].astype("string").str.lower().isin(BLOCKED_ACCESS)
        usable &= ~blocked.fillna(False)
    routable = priced[usable]
    audit.record(
        step="filter_routable_edges",
        rows_in=len(priced),
        rows_out=len(routable),
        cells_nulled=int((~usable).sum()),
        reason=(
            "dropped edges with no positive travel time or access=no; "
            "access=private/destination are KEPT because those restrictions do not "
            "bind emergency services on a call"
        ),
    )

    # ── node index ─────────────────────────────────────────────────────────
    node_ids = np.asarray(nodes["id"], dtype=np.int64)
    position = pd.Series(np.arange(len(node_ids)), index=node_ids)

    u = position.reindex(routable["u"].to_numpy()).to_numpy()
    v = position.reindex(routable["v"].to_numpy()).to_numpy()
    weight = routable["travel_min"].to_numpy(dtype=float)
    metres = routable["length"].to_numpy(dtype=float)

    valid = ~(np.isnan(u) | np.isnan(v))
    dangling = int((~valid).sum())
    u, v = u[valid].astype(np.int32), v[valid].astype(np.int32)
    weight, metres = weight[valid], metres[valid]
    audit.record(
        step="index_graph_nodes",
        rows_in=len(routable),
        rows_out=int(valid.sum()),
        cells_nulled=dangling,
        reason=f"{dangling} edge(s) referenced a node outside the extract",
    )

    # ── direction ──────────────────────────────────────────────────────────
    oneway = routable.loc[valid, "oneway"].astype("string").str.lower()
    forward_only = oneway.isin(ONEWAY_FORWARD).to_numpy()
    reverse_only = oneway.isin(ONEWAY_REVERSE).to_numpy()
    both = ~(forward_only | reverse_only)   # includes every untagged edge

    src = np.concatenate([u[forward_only], v[reverse_only], u[both], v[both]])
    dst = np.concatenate([v[forward_only], u[reverse_only], v[both], u[both]])
    val = np.concatenate([
        weight[forward_only], weight[reverse_only], weight[both], weight[both]
    ])
    dist = np.concatenate([
        metres[forward_only], metres[reverse_only], metres[both], metres[both]
    ])
    audit.record(
        step="apply_direction",
        rows_in=int(valid.sum()),
        rows_out=len(val),
        cells_nulled=0,
        reason=(
            f"{int(forward_only.sum())} one-way, {int(reverse_only.sum())} reversed, "
            f"{int(both.sum())} two-way (an ABSENT oneway tag means two-way — 91% of "
            "edges carry none, so treating null as unknown would delete the network)"
        ),
    )

    # ── parallel edges take the minimum, not the sum ───────────────────────
    order = np.argsort(val, kind="stable")
    src, dst, val, dist = src[order], dst[order], val[order], dist[order]
    keep = ~pd.DataFrame({"s": src, "d": dst}).duplicated().to_numpy()
    duplicates = int((~keep).sum())
    src, dst, val, dist = src[keep], dst[keep], val[keep], dist[keep]
    audit.record(
        step="dedupe_parallel_edges",
        rows_in=len(keep),
        rows_out=len(val),
        cells_nulled=duplicates,
        reason=(
            f"{duplicates} parallel arc(s) reduced to the fastest; building the "
            "matrix without this SUMS their weights, turning two roads between the "
            "same junctions into one slower road"
        ),
    )

    n = len(node_ids)
    matrix = sparse.csr_matrix((val, (src, dst)), shape=(n, n))
    matrix_m = sparse.csr_matrix((dist, (src, dst)), shape=(n, n))

    # ── coordinates, in metres, for snapping ───────────────────────────────
    geometry = nodes.geometry
    if nodes.crs is not None and nodes.crs.to_epsg() != CRS_WORKING:
        geometry = nodes.to_crs(epsg=CRS_WORKING).geometry
    coords = np.column_stack([geometry.x.to_numpy(), geometry.y.to_numpy()])

    audit.record(
        step="build_graph",
        rows_in=len(val),
        rows_out=n,
        cells_nulled=0,
        reason=(
            f"{n:,} nodes / {matrix.nnz:,} directed arcs as a CSR matrix in minutes; "
            f"node coordinates reprojected EPSG:{CRS_WGS84} -> EPSG:{CRS_WORKING} so "
            "snapping distances come out in metres"
        ),
    )
    return RoadGraph(matrix, matrix_m, node_ids, coords, speed_factor, provenance), audit


def _provenance(edges: pd.DataFrame) -> pd.DataFrame:
    from actionwise_geo.network.speeds import speed_provenance

    return speed_provenance(edges)


def connected_report(graph: RoadGraph) -> pd.DataFrame:
    """Size of each weakly connected component.

    Islands are why a coverage map can show a village as unreachable when it is
    simply not joined to the network in OSM. Reported, never silently dropped.
    """
    n_components, labels = sparse.csgraph.connected_components(
        graph.matrix, directed=True, connection="weak"
    )
    sizes = pd.Series(labels).value_counts()
    return pd.DataFrame({
        "component": sizes.index,
        "nodes": sizes.to_numpy(),
        "share": sizes.to_numpy() / graph.n_nodes,
    }).head(20)
