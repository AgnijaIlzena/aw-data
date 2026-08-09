"""Speed assignment, graph construction and snapping.

Built on a graph small enough to know the right answer by hand. The failures
targeted here are the ones a routing library would hide: parallel edges summing
instead of taking the minimum, an absent `oneway` tag deleting the network, a
zero speed carving a fake hole in the map.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from actionwise_geo import config as gc
from actionwise_geo.network import speeds as sp
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points, snap_quality

# Four nodes in a line, 1 km apart, in EPSG:3059.
X0, Y0 = 500_000, 300_000


def toy_nodes(n: int = 4) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"id": list(range(n))},
        geometry=[Point(X0 + i * 1000, Y0) for i in range(n)],
        crs=gc.CRS_WORKING,
    )


def toy_edges(rows: list[dict]) -> gpd.GeoDataFrame:
    frame = pd.DataFrame(rows)
    for column, default in (("maxspeed", None), ("oneway", None),
                            ("highway", "residential"), ("access", None)):
        if column not in frame:
            frame[column] = default
    geometry = [
        LineString([(X0 + r["u"] * 1000, Y0), (X0 + r["v"] * 1000, Y0)])
        for _, r in frame.iterrows()
    ]
    return gpd.GeoDataFrame(frame, geometry=geometry, crs=gc.CRS_WORKING)


# ══════════════════════════════════════════════════════════════════════════
# speeds
# ══════════════════════════════════════════════════════════════════════════

def test_parse_maxspeed_handles_the_forms_osm_actually_uses():
    parsed = sp.parse_maxspeed(pd.Series(["90", "50", "30 mph", "RU:urban", "walk"]))
    assert parsed.iloc[0] == 90
    assert parsed.iloc[1] == 50
    assert parsed.iloc[2] == pytest.approx(48.28, abs=0.1)
    assert parsed.iloc[3] == 60      # Russian urban default
    assert parsed.iloc[4] == 5


def test_parse_maxspeed_nulls_nonsense_rather_than_returning_zero():
    """A zero speed is an infinite travel time — a fake hole in the coverage map."""
    parsed = sp.parse_maxspeed(pd.Series(["0", "999", "fast", "", None, "none"]))
    assert parsed.isna().all(), (
        "unparseable values must fall through to the class default, never become 0"
    )


def test_assign_speeds_prefers_the_tag_then_the_class():
    edges = toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "70", "highway": "primary"},
        {"u": 1, "v": 2, "length": 1000.0, "maxspeed": None, "highway": "primary"},
        {"u": 2, "v": 3, "length": 1000.0, "maxspeed": None, "highway": "not_a_class"},
    ])
    out = sp.assign_speeds(edges)
    assert out["speed_kmh"].iloc[0] == 70
    assert out["speed_source"].iloc[0] == "tagged"
    assert out["speed_kmh"].iloc[1] == gc.DEFAULT_SPEEDS_KMH["primary"]
    assert out["speed_source"].iloc[1] == "class_default"
    assert out["speed_source"].iloc[2] == "global_default"
    assert out["speed_kmh"].iloc[2] > 0, "an unroutable edge is a hole in the map"


def test_emergency_factor_scales_every_speed():
    edges = toy_edges([{"u": 0, "v": 1, "length": 1000.0, "maxspeed": "50"}])
    assert sp.assign_speeds(edges, factor=1.2)["speed_kmh"].iloc[0] == pytest.approx(60)


def test_travel_time_is_minutes():
    """60 km/h over 1 km is exactly one minute."""
    assert sp.travel_time_minutes([1000.0], [60.0]).iloc[0] == pytest.approx(1.0)


def test_provenance_is_weighted_by_length_not_edge_count():
    """One long tagged road matters more than many short untagged ones."""
    edges = sp.assign_speeds(toy_edges([
        {"u": 0, "v": 1, "length": 10_000.0, "maxspeed": "90", "highway": "trunk"},
        {"u": 1, "v": 2, "length": 100.0, "maxspeed": None, "highway": "residential"},
        {"u": 2, "v": 3, "length": 100.0, "maxspeed": None, "highway": "residential"},
    ]))
    provenance = sp.speed_provenance(edges).set_index("speed_source")
    assert provenance.loc["tagged", "edges"] == 1
    assert provenance.loc["tagged", "share_of_length"] > 0.9


# ══════════════════════════════════════════════════════════════════════════
# graph
# ══════════════════════════════════════════════════════════════════════════

def test_absent_oneway_means_two_way():
    """91% of real edges carry no oneway tag. Treating null as unknown deletes them."""
    graph, _ = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "oneway": None},
    ]))
    dense = graph.matrix.toarray()
    assert dense[0, 1] > 0 and dense[1, 0] > 0


def test_oneway_yes_is_directed():
    graph, _ = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "oneway": "yes"},
    ]))
    dense = graph.matrix.toarray()
    assert dense[0, 1] > 0 and dense[1, 0] == 0


def test_oneway_minus_one_reverses_direction():
    graph, _ = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "oneway": "-1"},
    ]))
    dense = graph.matrix.toarray()
    assert dense[1, 0] > 0 and dense[0, 1] == 0


def test_parallel_edges_take_the_minimum_not_the_sum():
    """The bug a COO matrix introduces silently.

    Two roads between the same junctions must leave the faster one usable.
    Summing turns them into a single slower road, which inflates every travel
    time through that pair without any error being raised.
    """
    graph, _ = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "oneway": "yes"},
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "20", "oneway": "yes"},
    ]))
    fast = sp.travel_time_minutes([1000.0], [60.0]).iloc[0]
    assert graph.matrix.toarray()[0, 1] == pytest.approx(fast), (
        "the slow parallel road won, or the two were summed"
    )


def test_access_no_is_excluded_but_private_is_kept():
    """A barrier blocks a fire engine; a private-road sign does not."""
    graph, _ = build_graph(toy_nodes(3), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "access": "no"},
        {"u": 1, "v": 2, "length": 1000.0, "maxspeed": "60", "access": "private"},
    ]))
    dense = graph.matrix.toarray()
    assert dense[0, 1] == 0, "access=no must not be routable"
    assert dense[1, 2] > 0, "access=private must stay — it does not bind emergencies"


def test_edges_referencing_unknown_nodes_are_dropped_and_counted():
    graph, audit = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60"},
        {"u": 0, "v": 999, "length": 1000.0, "maxspeed": "60"},
    ]))
    trail = audit.to_frame()
    step = trail[trail["step"] == "index_graph_nodes"].iloc[0]
    assert step["cells_nulled"] == 1


def test_distance_matrix_carries_metres_not_minutes():
    """The decomposition depends on these being different weightings."""
    graph, _ = build_graph(toy_nodes(2), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "oneway": "yes"},
    ]))
    assert graph.matrix_m.toarray()[0, 1] == pytest.approx(1000.0)
    assert graph.matrix.toarray()[0, 1] == pytest.approx(1.0)


def test_graph_reprojects_node_coordinates_to_metres():
    nodes = toy_nodes(2).to_crs(epsg=gc.CRS_WGS84)
    graph, _ = build_graph(nodes, toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60"},
    ]))
    assert abs(graph.coords[0][0] - X0) < 5, "coords must come back in EPSG:3059"


# ══════════════════════════════════════════════════════════════════════════
# snapping
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def toy_graph():
    graph, _ = build_graph(toy_nodes(4), toy_edges([
        {"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60"},
        {"u": 1, "v": 2, "length": 1000.0, "maxspeed": "60"},
        {"u": 2, "v": 3, "length": 1000.0, "maxspeed": "60"},
    ]))
    return graph


def test_snap_finds_the_nearest_node_and_reports_metres(toy_graph):
    points = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Point(X0 + 1_100, Y0 + 300)], crs=gc.CRS_WORKING
    )
    snapped, _ = snap_points(points, toy_graph)
    assert snapped["node_index"].iloc[0] == 1
    assert snapped["snap_distance_m"].iloc[0] == pytest.approx(316.2, abs=1)


def test_far_snaps_are_flagged_not_dropped(toy_graph):
    """A cell snapped to a road 30 km away gives a precise, plausible, wrong answer."""
    points = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(X0, Y0), Point(X0, Y0 + 30_000)],
        crs=gc.CRS_WORKING,
    )
    snapped, audit = snap_points(points, toy_graph, max_distance_m=2_000)
    assert len(snapped) == 2, "nothing is dropped"
    assert not snapped["snap_suspect"].iloc[0]
    assert snapped["snap_suspect"].iloc[1]
    assert audit.to_frame()["reason"].iloc[-1].count("beyond") == 1


def test_null_geometry_snaps_to_nothing_without_raising(toy_graph):
    """The unallocated population row is exactly this case."""
    points = gpd.GeoDataFrame(
        {"id": [1, 2]}, geometry=[Point(X0, Y0), None], crs=gc.CRS_WORKING
    )
    snapped, _ = snap_points(points, toy_graph)
    assert snapped["node_index"].iloc[1] == -1
    assert pd.isna(snapped["snap_distance_m"].iloc[1])


def test_snapping_refuses_degrees(toy_graph):
    points = gpd.GeoDataFrame(
        {"id": [1]}, geometry=[Point(24.1, 56.9)], crs=gc.CRS_WGS84
    )
    with pytest.raises(ValueError, match="3059"):
        snap_points(points, toy_graph)


def test_snap_quality_weights_by_population(toy_graph):
    """A hundred empty cells snapping badly does not matter; one populated one does."""
    points = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(X0, Y0), Point(X0, Y0 + 30_000)],
        crs=gc.CRS_WORKING,
    )
    snapped, _ = snap_points(points, toy_graph, max_distance_m=2_000)
    quality = snap_quality(snapped, pd.Series([1000, 5], index=points.index))
    assert quality["suspect"] == 1
    assert quality["population_suspect"] == 5
    assert quality["population_suspect_share"] == pytest.approx(5 / 1005)
