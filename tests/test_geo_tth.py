"""TTH — multi-source routing, the turnout constant, and the decomposed baseline.

The toy network is a 4 km straight line at 60 km/h, so every expected answer is
arithmetic: node *i* is *i* minutes from node 0.

The last group is the one that earns its place. A single time-based comparison
against a straight line lands at 1.00 on the real network and reads as "the
routing added nothing" — which is false. These tests pin the decomposition that
tells the road detour apart from the assumed baseline speed.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from actionwise_geo import config as gc
from actionwise_geo.indices import tth
from actionwise_geo.network.graph import build_graph
from actionwise_geo.network.snap import snap_points

X0, Y0 = 500_000, 300_000


def line_network(n: int = 5, speed: str = "60"):
    """n nodes, 1 km apart, all at `speed` — so travel time in minutes == index."""
    nodes = gpd.GeoDataFrame(
        {"id": list(range(n))},
        geometry=[Point(X0 + i * 1000, Y0) for i in range(n)],
        crs=gc.CRS_WORKING,
    )
    rows = [{"u": i, "v": i + 1, "length": 1000.0, "maxspeed": speed,
             "highway": "primary", "oneway": None, "access": None}
            for i in range(n - 1)]
    edges = gpd.GeoDataFrame(
        pd.DataFrame(rows),
        geometry=[LineString([(X0 + r["u"] * 1000, Y0), (X0 + r["v"] * 1000, Y0)])
                  for r in rows],
        crs=gc.CRS_WORKING,
    )
    graph, _ = build_graph(nodes, edges)
    return graph


def cells_at(indices, population=100):
    return gpd.GeoDataFrame(
        {"grd_id": [f"c{i}" for i in indices], "T": [population] * len(indices)},
        geometry=[Point(X0 + i * 1000, Y0) for i in indices],
        crs=gc.CRS_WORKING,
    )


def depots_at(indices):
    return gpd.GeoDataFrame(
        {"nosaukums": [f"d{i}" for i in indices]},
        geometry=[Point(X0 + i * 1000, Y0) for i in indices],
        crs=gc.CRS_WORKING,
    )


# ── multi-source routing ───────────────────────────────────────────────────

def test_time_from_a_single_depot_is_the_distance_in_minutes():
    graph = line_network(5)
    minutes = tth.time_from_nearest_depot(graph, [0])
    assert list(np.round(minutes, 6)) == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_multi_source_takes_the_nearest_depot_not_the_first():
    """The whole point of min_only: 87 depots, one pass, nearest wins."""
    graph = line_network(5)
    minutes = tth.time_from_nearest_depot(graph, [0, 4])
    assert list(np.round(minutes, 6)) == [0.0, 1.0, 2.0, 1.0, 0.0]


def test_unreachable_nodes_stay_infinite():
    """An unreachable place is a fact about the network, not a slow journey."""
    graph = line_network(3)
    isolated = gpd.GeoDataFrame(
        {"id": [99]}, geometry=[Point(X0 + 50_000, Y0)], crs=gc.CRS_WORKING
    )
    nodes = pd.concat([
        gpd.GeoDataFrame({"id": list(range(3))},
                         geometry=[Point(X0 + i * 1000, Y0) for i in range(3)],
                         crs=gc.CRS_WORKING),
        isolated,
    ], ignore_index=True)
    rows = [{"u": 0, "v": 1, "length": 1000.0, "maxspeed": "60", "highway": "primary",
             "oneway": None, "access": None},
            {"u": 1, "v": 2, "length": 1000.0, "maxspeed": "60", "highway": "primary",
             "oneway": None, "access": None}]
    edges = gpd.GeoDataFrame(
        pd.DataFrame(rows),
        geometry=[LineString([(X0, Y0), (X0 + 1000, Y0)]),
                  LineString([(X0 + 1000, Y0), (X0 + 2000, Y0)])],
        crs=gc.CRS_WORKING,
    )
    graph, _ = build_graph(nodes, edges)
    minutes = tth.time_from_nearest_depot(graph, [0])
    assert np.isinf(minutes[3])


def test_routing_without_a_snapped_depot_raises():
    with pytest.raises(ValueError, match="(?i)depot"):
        tth.time_from_nearest_depot(line_network(3), [-1, -1])


# ── cell assignment and the turnout constant ───────────────────────────────

def test_response_time_adds_the_ninety_second_turnout():
    """MK 297 p. 5. Travel and response are separate columns so neither is ever
    quietly reported as the other."""
    graph = line_network(5)
    cells = cells_at([0, 2])
    snapped, _ = snap_points(cells, graph)
    minutes = tth.time_from_nearest_depot(graph, [0])

    travel, _ = tth.cell_travel_times(cells, snapped, minutes)
    assert travel["tth_minutes"].tolist() == [0.0, 2.0]
    assert travel["response_minutes"].tolist() == [
        gc.TURNOUT_MINUTES, 2.0 + gc.TURNOUT_MINUTES
    ]
    assert gc.TURNOUT_MINUTES == 1.5


def test_unreachable_cells_are_null_never_a_large_number():
    graph = line_network(3)
    cells = cells_at([0])
    snapped, _ = snap_points(cells, graph)
    minutes = np.array([np.inf, np.inf, np.inf])

    travel, audit = tth.cell_travel_times(cells, snapped, minutes)
    assert pd.isna(travel["tth_minutes"].iloc[0])
    assert not travel["reachable"].iloc[0]
    assert "unreached" in audit.to_frame()["reason"].str.cat().lower() or \
           "could not be reached" in audit.to_frame()["reason"].str.cat()


def test_coverage_uses_response_time_against_the_legal_thresholds():
    graph = line_network(30)
    cells = cells_at([0, 10, 25], population=100)
    snapped, _ = snap_points(cells, graph)
    minutes = tth.time_from_nearest_depot(graph, [0])

    travel, _ = tth.cell_travel_times(cells, snapped, minutes)
    coverage = tth.coverage_summary(cells, travel).set_index("threshold")

    # response = travel + 1.5 -> 1.5, 11.5, 26.5 minutes
    assert coverage.loc["within 8 min (served settlements)", "population"] == 100
    assert coverage.loc["within 23 min (elsewhere)", "population"] == 200
    assert coverage.loc["beyond 23 min or unreachable", "population"] == 100


# ── the decomposition ──────────────────────────────────────────────────────

def test_detour_factor_is_one_on_a_straight_road():
    """Sanity anchor: a perfectly straight network cannot detour."""
    graph = line_network(5)
    cells, depots = cells_at([4]), depots_at([0])
    snapped, _ = snap_points(cells, graph)
    minutes = tth.time_from_nearest_depot(graph, [0])
    metres = tth.distance_from_nearest_depot(graph, [0])

    travel, _ = tth.cell_travel_times(cells, snapped, minutes, depots=depots,
                                      node_metres=metres)
    assert travel["detour_factor"].iloc[0] == pytest.approx(1.0, abs=0.01)
    assert travel["road_m"].iloc[0] == pytest.approx(4000.0)


def test_detour_factor_detects_a_road_that_goes_the_long_way():
    """Two nodes 1 km apart connected only by a 3 km road -> detour 3.0."""
    nodes = gpd.GeoDataFrame(
        {"id": [0, 1]},
        geometry=[Point(X0, Y0), Point(X0 + 1000, Y0)],
        crs=gc.CRS_WORKING,
    )
    edges = gpd.GeoDataFrame(
        pd.DataFrame([{"u": 0, "v": 1, "length": 3000.0, "maxspeed": "60",
                       "highway": "primary", "oneway": None, "access": None}]),
        geometry=[LineString([(X0, Y0), (X0 + 1000, Y0)])],
        crs=gc.CRS_WORKING,
    )
    graph, _ = build_graph(nodes, edges)
    cells, depots = cells_at([1]), depots_at([0])
    snapped, _ = snap_points(cells, graph)

    travel, _ = tth.cell_travel_times(
        cells, snapped,
        tth.time_from_nearest_depot(graph, [0]),
        depots=depots,
        node_metres=tth.distance_from_nearest_depot(graph, [0]),
    )
    assert travel["detour_factor"].iloc[0] == pytest.approx(3.0, abs=0.01)


def test_detour_is_speed_free_but_time_ratio_is_not():
    """THE test for this decomposition.

    Doubling every speed halves the time ratio and leaves the detour untouched.
    That is exactly why the two are reported separately: on the real network the
    time ratio sits at 1.00 and would read as 'routing added nothing', while the
    detour shows the roads winding by 23%.
    """
    cells, depots = cells_at([4]), depots_at([0])

    def measure(speed: str) -> tuple[float, float]:
        graph = line_network(5, speed=speed)
        snapped, _ = snap_points(cells, graph)
        travel, _ = tth.cell_travel_times(
            cells, snapped,
            tth.time_from_nearest_depot(graph, [0]),
            depots=depots,
            node_metres=tth.distance_from_nearest_depot(graph, [0]),
        )
        return travel["time_ratio"].iloc[0], travel["detour_factor"].iloc[0]

    slow_ratio, slow_detour = measure("30")
    fast_ratio, fast_detour = measure("60")

    assert slow_ratio == pytest.approx(2 * fast_ratio, rel=0.01)
    assert slow_detour == pytest.approx(fast_detour, rel=1e-6), (
        "the detour must not move when only the speed model changes"
    )


def test_baseline_comparison_reports_both_ratios():
    graph = line_network(5)
    cells, depots = cells_at([2, 4]), depots_at([0])
    snapped, _ = snap_points(cells, graph)
    travel, _ = tth.cell_travel_times(
        cells, snapped,
        tth.time_from_nearest_depot(graph, [0]),
        depots=depots,
        node_metres=tth.distance_from_nearest_depot(graph, [0]),
    )
    summary = tth.baseline_comparison(travel, cells["T"])
    assert {"network_mean_min", "baseline_mean_min", "median_time_ratio",
            "median_detour", "p90_detour"} <= set(summary.columns)
    assert summary["median_detour"].iloc[0] == pytest.approx(1.0, abs=0.01)


# ── face validity on the real network ──────────────────────────────────────

@pytest.mark.slow
@pytest.mark.skipif(not gc.OSM_PBF.exists(), reason="OSM extract not in dati/")
def test_real_network_face_validity():
    """The plan's Phase 3 check: cities fast, large rural municipalities slow.

    Deliberately not "Rīga is fastest". Rīga covers 304 km² with 9 depots, so its
    population-weighted mean (4.4 min) sits behind compact single-depot cities
    like Rēzekne (2.4 min) — that is correct, and a test asserting otherwise
    would be wrong about the geography rather than about the code.
    """
    import pyrosm

    from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
    from actionwise_geo.data.depots import load_depots
    from actionwise_geo.data.popgrid import load_population_grid

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()

    osm = pyrosm.OSM(str(gc.OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    graph, audit = build_graph(nodes, edges, speed_factor=1.0, audit=audit)

    depot_snap, audit = snap_points(depots, graph, audit=audit)
    cell_snap, audit = snap_points(cells, graph, audit=audit)
    minutes = tth.time_from_nearest_depot(graph, depot_snap["node_index"])
    metres = tth.distance_from_nearest_depot(graph, depot_snap["node_index"])
    travel, audit = tth.cell_travel_times(cells, cell_snap, minutes, depots=depots,
                                          node_metres=metres, audit=audit)

    joined, audit = assign_municipality(cells, boundaries, audit=audit)
    frame = pd.DataFrame({
        "municipality": joined["municipality"].to_numpy(),
        "tth": travel["tth_minutes"].to_numpy(),
        "pop": cells["T"].to_numpy(),
    }).dropna()
    per = frame.groupby("municipality").apply(
        lambda d: (d["tth"] * d["pop"]).sum() / d["pop"].sum(), include_groups=False
    )

    # Cities must beat the national average comfortably.
    national = (frame["tth"] * frame["pop"]).sum() / frame["pop"].sum()
    for city in ("Rīga", "Daugavpils", "Liepāja", "Rēzekne"):
        assert per[city] < national, f"{city} should be faster than the national mean"
    assert per["Rīga"] < 8.0, "Rīga cannot average worse than the 8-minute standard"

    # And the slowest places must be rural, never a valstspilsēta.
    slowest = set(per.sort_values().tail(6).index)
    assert not (slowest & set(boundaries.loc[boundaries["is_city"], "nosaukums"])), (
        f"a city ranked among the slowest municipalities: {slowest} — the graph or "
        "the CRS is wrong"
    )

    # The geometric detour must be a real detour, not a rounding artefact.
    detour = travel["detour_factor"].replace([np.inf, -np.inf], np.nan).dropna()
    assert 1.1 < detour.median() < 1.6, (
        f"median detour {detour.median():.3f} — a real road network winds by "
        "roughly 20-40%; near 1.0 means the routing is not following roads"
    )
