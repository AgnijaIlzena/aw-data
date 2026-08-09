"""Traffic-adjusted travel time — the part nobody else does.

Every shelter or coverage map on the internet routes at free-flow speed. This one
uses twelve years of observed vehicle counts on 1,335 Latvian roads, joined to the
network through the kilometre markers, and reports the adjusted times **beside**
the free-flow ones rather than in place of them.

The chain, and why each link exists:

    traffic sheets   road ref + chainage range + AADT   (no coordinates at all)
    km markers       road ref + chainage + a point      (the bridge)
    OSM edges        geometry + ref                     (no chainage)

An edge's chainage comes from its nearest marker on the same road; the AADT is
then the traffic segment whose range contains that chainage.

**The honest caveat, stated in the model rather than a footnote.** BPR describes
the delay a *car* suffers in a queue. Latvian law requires traffic to yield to a
blue-light vehicle, and crews use the oncoming lane and the hard shoulder — so a
fire engine does not sit in that queue. Applying the full delay would inflate
urban response times and flatter this project's own rural-gap thesis. The
`damping` parameter runs 0 (unaffected) to 1 (delayed exactly like a car), and
every figure is reported across the range.

The measured result, 2026-08-07
-------------------------------
**Congestion turns out not to matter.** Even at damping 1.0 the national
population-weighted mean response moves from 7.50 to 7.51 minutes (+0.2%) and the
CCI does not move at all.

That is a real finding, not a bug. Latvia's roads are empty by the standards of a
capacity function:

    class        median AADT   peak veh/h   capacity     V/C   multiplier
    secondary            192         10.6      1,400   0.008       1.0000
    primary            1,305         71.8      1,600   0.045       1.0000
    trunk              4,581        252.0      1,800   0.140       1.0001

The median secondary road carries eleven vehicles in the peak hour. Only the
busiest segment in the country — A10 at km 13.5-15.4, AADT 59,598 on the Rīga
approach — reaches V/C = 1.82, and such links are a rounding error in total
network length.

**What this does NOT say.** It does not say urban response is unaffected by
traffic. It says *link congestion* is not the mechanism. What actually delays a
vehicle in Rīga is junction and signal delay, and neither AADT nor BPR captures
that: BPR models queuing against link capacity, and the traffic counts cover the
numbered network (19.9% of edges) while urban driving happens largely on
unnumbered streets that have no counts at all.

So the traffic layer is kept and reported — the cross-check between the two
publications is worth having on its own, and the negative result is worth
stating — but it is not the differentiator this project once expected it to be.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    BPR_ALPHA,
    BPR_BETA,
    DEFAULT_LANE_CAPACITY_VPH,
    DIRECTIONAL_SPLIT,
    LANE_CAPACITY_VPH,
    PEAK_HOUR_SHARE,
)
from actionwise_geo.data.traffic import normalise_road_ref


def edge_chainage(edges, markers, max_distance_m: float = 2_000.0,
                  audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Give each OSM edge a position along its road, from the nearest marker.

    Args:
        edges: OSM edges in EPSG:3059 with a `ref` column.
        markers: from `data.kmmarkers.load_km_markers`.
        max_distance_m: beyond this the marker is on a different stretch and the
            chainage is left null rather than guessed.

    Returns:
        `(frame, audit)` indexed like `edges`, with `road`, `chainage_km`,
        `marker_distance_m`.
    """
    audit = audit or Audit()

    # An edge can carry several refs ("A1;E67"); the first is the road it is.
    road = normalise_road_ref(
        edges["ref"].astype("string").str.split(";").str[0]
    )
    out = pd.DataFrame(
        {"road": road, "chainage_km": np.nan, "marker_distance_m": np.nan},
        index=edges.index,
    )

    centroids = edges.geometry.representative_point()
    matched = 0
    for name, group in out[out["road"].notna()].groupby("road", observed=True):
        road_markers = markers[markers["road"] == name]
        if road_markers.empty:
            continue
        tree = cKDTree(
            np.column_stack([road_markers.geometry.x, road_markers.geometry.y])
        )
        points = centroids.loc[group.index]
        distance, index = tree.query(
            np.column_stack([points.x.to_numpy(), points.y.to_numpy()]), k=1
        )
        within = distance <= max_distance_m
        out.loc[group.index[within], "chainage_km"] = (
            road_markers["chainage_km"].to_numpy()[index[within]]
        )
        out.loc[group.index, "marker_distance_m"] = distance
        matched += int(within.sum())

    audit.record(
        step="assign_edge_chainage",
        rows_in=len(edges),
        rows_out=matched,
        cells_nulled=len(edges) - matched,
        reason=(
            f"{matched:,} edge(s) located along a numbered road via the nearest km "
            f"marker within {max_distance_m:.0f} m; the rest are unnumbered streets "
            "with no traffic counts and keep their free-flow speed"
        ),
    )
    return out, audit


def attach_aadt(chainage: pd.DataFrame, traffic: pd.DataFrame,
                audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Match each edge's chainage to the traffic segment containing it.

    `traffic` should be one row per segment — pass it through
    `data.traffic.latest_year` first, or several years will match at once.
    """
    audit = audit or Audit()

    usable = chainage[chainage["chainage_km"].notna()].reset_index()
    index_col = usable.columns[0]
    merged = usable.merge(
        traffic[["road", "km_from", "km_to", "aadt", "heavy_pct", "aadt_censored"]],
        on="road", how="left",
    )
    inside = (
        (merged["chainage_km"] >= merged["km_from"])
        & (merged["chainage_km"] <= merged["km_to"])
    )
    hits = merged[inside].drop_duplicates(subset=[index_col], keep="first")

    out = pd.DataFrame(index=chainage.index)
    out["aadt"] = hits.set_index(index_col)["aadt"].reindex(chainage.index)
    out["heavy_pct"] = hits.set_index(index_col)["heavy_pct"].reindex(chainage.index)
    # `reindex(fill_value=False)` rather than `reindex().fillna(False)`: the
    # latter introduces NaN, which turns a bool column into object dtype, and the
    # downcast back is deprecated in pandas 2.x. Filling during the reindex means
    # the column is never anything but bool — and an `aadt_censored` that came out
    # as object would make every later `~mask` and `.sum()` behave differently.
    out["aadt_censored"] = (
        hits.set_index(index_col)["aadt_censored"]
        .reindex(chainage.index, fill_value=False)
        .astype(bool)
    )

    covered = int(out["aadt"].notna().sum())
    audit.record(
        step="attach_aadt",
        rows_in=len(chainage),
        rows_out=covered,
        cells_nulled=len(chainage) - covered,
        reason=(
            f"{covered:,} edge(s) carry an observed vehicle count; the remainder "
            "keep free-flow speed, so the adjustment can only ever slow the "
            "network down, never speed it up"
        ),
    )
    return out, audit


def bpr_multiplier(aadt, highway, damping: float = 1.0) -> pd.Series:
    """Travel-time multiplier from the BPR delay function.

        t = t_free * (1 + alpha * (V/C)^beta)

    V is the peak-hour directional volume implied by AADT; C is the capacity of
    the road class. Edges with no count get 1.0 — unchanged.

    Args:
        damping: how much of a car's delay an emergency vehicle actually suffers.
            0 leaves travel times identical to free-flow; 1 treats the fire engine
            as an ordinary car in the queue. See the module docstring.
    """
    volume = pd.Series(aadt).astype(float) * PEAK_HOUR_SHARE * DIRECTIONAL_SPLIT
    capacity = (
        pd.Series(highway).astype("string").str.split(";").str[0].str.strip()
        .map(LANE_CAPACITY_VPH).astype(float).fillna(DEFAULT_LANE_CAPACITY_VPH)
    )
    capacity = capacity.where(capacity > 0, DEFAULT_LANE_CAPACITY_VPH)

    ratio = (volume / capacity.to_numpy()).fillna(0.0)
    delay = BPR_ALPHA * np.power(ratio.clip(lower=0), BPR_BETA)
    return (1.0 + damping * delay).fillna(1.0)


def apply_congestion(edges: pd.DataFrame, aadt: pd.DataFrame, damping: float = 1.0,
                     audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """Return `edges` with travel times inflated by congestion.

    Adds `congestion_multiplier` and rewrites `maxspeed` to the congested
    equivalent speed, so the existing graph builder needs no change: it reads
    `maxspeed` as it always did and gets a slower network.
    """
    audit = audit or Audit()
    out = edges.copy()

    multiplier = bpr_multiplier(
        aadt["aadt"].reindex(edges.index), edges["highway"], damping=damping
    )
    out["congestion_multiplier"] = multiplier.to_numpy()

    from actionwise_geo.network.speeds import assign_speeds

    free = assign_speeds(edges, factor=1.0)["speed_kmh"]
    # A multiplier on TIME is a divisor on SPEED.
    out["maxspeed"] = (free.to_numpy() / multiplier.to_numpy()).round(2).astype(str)

    affected = int((multiplier > 1.001).sum())
    worst = float(multiplier.max())
    audit.record(
        step="apply_congestion",
        rows_in=len(edges),
        rows_out=len(out),
        cells_nulled=0,
        reason=(
            f"BPR at damping {damping}: {affected:,} edge(s) slowed, worst "
            f"multiplier {worst:.2f}x. Damping is not cosmetic — traffic must "
            "yield to a blue-light vehicle, so a fire engine does not sit in the "
            "queue BPR describes; damping 1.0 is the pessimistic bound, not the "
            "expected case"
        ),
    )
    return out, audit


def congestion_summary(edges: pd.DataFrame, aadt: pd.DataFrame) -> pd.DataFrame:
    """Where the congestion adjustment actually bites, by road class."""
    frame = pd.DataFrame({
        "highway": edges["highway"].astype("string").str.split(";").str[0],
        "length_km": edges["length"] / 1000.0,
        "aadt": aadt["aadt"].reindex(edges.index),
        "multiplier": edges.get("congestion_multiplier", 1.0),
    })
    with_counts = frame[frame["aadt"].notna()]
    grouped = with_counts.groupby("highway", observed=True)
    summary = pd.DataFrame({
        "edges_with_counts": grouped.size(),
        "length_km": grouped["length_km"].sum(),
        "median_aadt": grouped["aadt"].median(),
        "median_multiplier": grouped["multiplier"].median(),
        "max_multiplier": grouped["multiplier"].max(),
    })
    return summary.sort_values("length_km", ascending=False).reset_index()
