"""Phase 0 gate: the routing stack installs and the PBF actually parses.

Marked `slow` — the parse takes ~73 s, so this is excluded from the default run
and executed deliberately:

    pytest -m slow tests/test_geo_smoke.py

Skips cleanly when the geo extra is not installed or `dati/` is absent, so a
checkout without either still goes green.

The tag assertions are the point. `pyrosm` returning a frame proves nothing; what
matters is that `highway`, `maxspeed`, `oneway` and `ref` mean what Phase 3 and
Phase 5 assume they mean. A1 and P1 are checked against their real-world class
because a silent tag-parsing regression would otherwise surface as a plausible
travel-time map with no error anywhere.
"""
import pytest

from actionwise_geo import config as gc

pyrosm = pytest.importorskip("pyrosm", reason="geo extra not installed")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not gc.OSM_PBF.exists(), reason="OSM extract not in dati/"),
]


@pytest.fixture(scope="module")
def network():
    """Parsed once and shared — this is the expensive fixture in the suite."""
    osm = pyrosm.OSM(str(gc.OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    return nodes, edges


def test_network_size_is_in_the_expected_range(network):
    """Guards against a truncated or swapped file, not against OSM's normal churn."""
    nodes, edges = network
    tol = gc.OSM_COUNT_TOLERANCE
    assert abs(len(nodes) - gc.OSM_EXPECTED_NODES) / gc.OSM_EXPECTED_NODES < tol
    assert abs(len(edges) - gc.OSM_EXPECTED_EDGES) / gc.OSM_EXPECTED_EDGES < tol


def test_edges_arrive_in_degrees_and_must_be_reprojected(network):
    """pyrosm hands back EPSG:4326. Everything downstream works in 3059."""
    _, edges = network
    assert edges.crs.to_epsg() == gc.CRS_WGS84
    assert gc.CRS_WORKING != gc.CRS_WGS84


def test_known_roads_carry_their_real_classes(network):
    """A1/A2 are trunk roads and P1 is a regional primary — independently known."""
    _, edges = network
    ref = edges["ref"].astype("string").str.split(";").str[0].str.strip()

    a1 = edges[ref == "A1"]
    assert len(a1) > 500
    assert set(a1["highway"].unique()) <= {"trunk", "trunk_link"}

    p1 = edges[ref == "P1"]
    assert len(p1) > 200
    assert set(p1["highway"].unique()) <= {"primary", "primary_link"}


def test_maxspeed_is_mostly_absent_which_is_why_defaults_matter(network):
    """If tag coverage ever jumps, the speed-default sensitivity can be relaxed."""
    _, edges = network
    share = edges["maxspeed"].notna().mean()
    assert 0.10 < share < 0.30, (
        f"maxspeed coverage is {share:.1%}; config records {gc.OSM_MAXSPEED_TAGGED_SHARE:.1%}. "
        "DEFAULT_SPEEDS_KMH drives the rest of the network, so a large change here "
        "means the speed model's weight in the result has changed too."
    )
    # Every class in the fallback table must exist, or the default is dead code.
    classes = set(edges["highway"].dropna().unique())
    assert classes & set(gc.DEFAULT_SPEEDS_KMH), "no highway class matches the speed table"


def test_maxspeed_is_a_string_with_non_numeric_values(network):
    """`RU:urban` and friends: coerce, never cast."""
    import pandas as pd

    _, edges = network
    tagged = edges["maxspeed"].dropna().astype(str)
    non_numeric = tagged[pd.to_numeric(tagged, errors="coerce").isna()]
    assert not non_numeric.empty, "expected implicit-speed tags; re-verify if gone"
    assert set(non_numeric.unique()) <= set(gc.OSM_NONNUMERIC_MAXSPEED)


def test_oneway_absent_means_two_way(network):
    """91% of edges have no `oneway` tag. Dropping nulls would delete the network."""
    _, edges = network
    assert edges["oneway"].notna().mean() < 0.25


def test_ref_is_populated_enough_to_join_the_traffic_data(network):
    """Phase 5's join key. Without it there is no AADT-weighted travel time."""
    _, edges = network
    assert edges["ref"].notna().sum() > 200_000
