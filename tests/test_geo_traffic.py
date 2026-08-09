"""The six-sheet traffic ETL, the km-marker bridge, and the congestion model.

Most of these pin failures that are silent. The forward-fill one is the worst:
`Ceļa Nr.` is null on 96 of 111 Galvenie rows, a null means "same road as above",
and without the fill every continuation segment loses its road and vanishes from
the join without any error being raised.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point

from actionwise_geo import config as gc
from actionwise_geo.data import traffic as tr
from actionwise_geo.network import congestion as cg

requires_raw = pytest.mark.skipif(
    not gc.TRAFFIC_XLSX_2014_2023.exists(), reason="dati/ not present"
)


# ══════════════════════════════════════════════════════════════════════════
# road reference normalisation — one function, four spellings
# ══════════════════════════════════════════════════════════════════════════

def test_every_spelling_of_a_road_number_normalises_to_one_key():
    """Galvenie writes A-14, Reģionālie P99, the markers "V 1398", OSM A14."""
    out = tr.normalise_road_ref(pd.Series(["A-14", "a14", "V 1398", "V  1398", "p99"]))
    assert out.tolist() == ["A14", "A14", "V1398", "V1398", "P99"]


def test_blank_road_refs_become_null_not_empty_strings():
    assert tr.normalise_road_ref(pd.Series(["", "  ", None])).isna().all()


# ══════════════════════════════════════════════════════════════════════════
# censored AADT
# ══════════════════════════════════════════════════════════════════════════

def test_censored_traffic_is_parsed_not_dropped():
    """"≤100" marks the quietest roads — exactly where response times are longest."""
    aadt, censored = tr.parse_aadt(pd.Series(["≤100", "500", "abc"]))
    assert aadt.iloc[0] == gc.TRAFFIC_CENSORED_LOW_AADT
    assert censored.iloc[0]
    assert aadt.iloc[1] == 500 and not censored.iloc[1]
    assert pd.isna(aadt.iloc[2]), "unparseable stays null rather than becoming 0"


# ══════════════════════════════════════════════════════════════════════════
# the six-sheet ETL, against the real workbooks
# ══════════════════════════════════════════════════════════════════════════

@requires_raw
def test_forward_fill_recovers_every_continuation_segment():
    """THE trap. 96 of 111 Galvenie rows carry no road number."""
    frame, audit = tr.load_traffic_sheet(gc.TRAFFIC_XLSX_2014_2023, "Galvenie")
    assert frame["road"].notna().all(), "a segment without a road cannot be joined"

    step = audit.to_frame().iloc[0]
    assert step["cells_nulled"] >= 90, (
        "if the null count collapsed, the file changed and the fill must be re-checked"
    )
    # A-14 must keep both of its segments, not just the row that named it.
    assert (frame["road"] == "A14").sum() > 1


@requires_raw
@pytest.mark.parametrize("sheet", gc.TRAFFIC_SHEETS)
def test_every_sheet_yields_the_same_long_schema(sheet):
    """Six sheets, six header spellings, one output shape."""
    frame, _ = tr.load_traffic_sheet(gc.TRAFFIC_XLSX_2014_2023, sheet)
    assert {"road", "km_from", "km_to", "year", "aadt", "heavy_pct"} <= set(frame.columns)
    assert (frame["km_to"] > frame["km_from"]).all()
    assert frame["year"].between(2010, 2030).all()
    assert not frame.empty


@requires_raw
def test_headers_with_newlines_and_case_differences_are_found():
    """Vietējie spells it `ceļa Nr.` and `no\\nkm`; Galvenie uses `posms` for the name."""
    vietejie, _ = tr.load_traffic_sheet(gc.TRAFFIC_XLSX_2014_2023, "Vietējie")
    assert vietejie["km_from"].notna().all()
    assert vietejie["road"].str.startswith("V").all()


@requires_raw
def test_the_two_publications_agree_where_they_overlap():
    """A free external check — and it passes at 98.4%.

    Large disagreement would mean one workbook was revised, and any figure built
    on the union would silently depend on which row won.
    """
    traffic, _ = tr.load_traffic()
    agreement = tr.overlap_agreement(traffic)
    assert agreement["overlapping_rows"].iloc[0] > 1000
    assert agreement["share_identical"].iloc[0] > 0.95
    assert agreement["median_abs_diff"].iloc[0] == 0


@requires_raw
def test_latest_year_gives_one_row_per_segment():
    traffic, _ = tr.load_traffic()
    latest = tr.latest_year(traffic)
    assert not latest.duplicated(subset=["road", "km_from", "km_to"]).any()
    assert len(latest) < len(traffic)


# ══════════════════════════════════════════════════════════════════════════
# the km-marker bridge
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not gc.KM_MARKERS_CSV.exists(), reason="dati/ not present")
def test_markers_load_with_decimal_chainage_and_expanded_junctions():
    from actionwise_geo.data.kmmarkers import load_km_markers

    markers, audit = load_km_markers()
    assert markers.crs.to_epsg() == gc.CRS_WORKING
    assert markers["chainage_km"].notna().all()
    assert markers["road"].notna().all()

    # Chainage must carry decimals — the KM column is rounded.
    assert (markers["chainage_km"] % 1 != 0).any(), (
        "every chainage is a whole number, so KM was used instead of SEARCH_STR"
    )
    # Junction markers were expanded, not dropped.
    assert markers["multi_road"].any()
    trail = audit.to_frame()
    assert (trail["step"] == "expand_junction_markers").any()


# ══════════════════════════════════════════════════════════════════════════
# the congestion model
# ══════════════════════════════════════════════════════════════════════════

def test_empty_roads_are_not_slowed():
    multiplier = cg.bpr_multiplier([100.0], ["secondary"], damping=1.0)
    assert multiplier.iloc[0] == pytest.approx(1.0, abs=1e-6)


def test_a_saturated_road_is_slowed_substantially():
    """A10 into Rīga carries 59,598 AADT — V/C = 1.82 against trunk capacity."""
    multiplier = cg.bpr_multiplier([59_598.0], ["trunk"], damping=1.0)
    assert multiplier.iloc[0] > 1.5


def test_edges_without_a_count_are_left_at_free_flow():
    """The adjustment may only ever slow the network, never speed it up."""
    multiplier = cg.bpr_multiplier([np.nan], ["primary"], damping=1.0)
    assert multiplier.iloc[0] == 1.0


def test_damping_zero_reproduces_free_flow_exactly():
    """Damping is the emergency-vehicle question, and 0 must be a true no-op."""
    multiplier = cg.bpr_multiplier([59_598.0], ["trunk"], damping=0.0)
    assert multiplier.iloc[0] == 1.0


def test_damping_scales_the_delay_not_the_travel_time():
    """Half the damping must give half the *extra* time, not half the total."""
    full = cg.bpr_multiplier([59_598.0], ["trunk"], damping=1.0).iloc[0]
    half = cg.bpr_multiplier([59_598.0], ["trunk"], damping=0.5).iloc[0]
    assert (half - 1.0) == pytest.approx((full - 1.0) / 2, rel=1e-6)


def test_unknown_road_class_falls_back_to_a_capacity_rather_than_zero():
    multiplier = cg.bpr_multiplier([5000.0], ["not_a_class"], damping=1.0)
    assert np.isfinite(multiplier.iloc[0]) and multiplier.iloc[0] >= 1.0


def test_congestion_lowers_the_speed_it_writes_back():
    """apply_congestion rewrites maxspeed so the graph builder needs no change."""
    edges = gpd.GeoDataFrame(
        pd.DataFrame({
            "u": [0], "v": [1], "length": [1000.0], "maxspeed": ["90"],
            "highway": ["trunk"], "oneway": [None], "access": [None],
        }),
        geometry=[LineString([(500_000, 300_000), (501_000, 300_000)])],
        crs=gc.CRS_WORKING,
    )
    aadt = pd.DataFrame({"aadt": [59_598.0]}, index=edges.index)

    out, audit = cg.apply_congestion(edges, aadt, damping=1.0)
    assert float(out["maxspeed"].iloc[0]) < 90
    assert out["congestion_multiplier"].iloc[0] > 1.5

    unaffected, _ = cg.apply_congestion(edges, aadt, damping=0.0)
    assert float(unaffected["maxspeed"].iloc[0]) == pytest.approx(90, abs=0.01)


def test_chainage_beyond_the_marker_radius_is_left_null_not_guessed():
    markers = gpd.GeoDataFrame(
        {"road": ["A1"], "chainage_km": [5.0], "multi_road": [False]},
        geometry=[Point(500_000, 300_000)], crs=gc.CRS_WORKING,
    )
    edges = gpd.GeoDataFrame(
        pd.DataFrame({"ref": ["A1"], "length": [100.0]}),
        geometry=[LineString([(560_000, 300_000), (560_100, 300_000)])],
        crs=gc.CRS_WORKING,
    )
    out, _ = cg.edge_chainage(edges, markers, max_distance_m=2_000)
    assert pd.isna(out["chainage_km"].iloc[0])


def test_aadt_attaches_only_inside_the_segment_range():
    chainage = pd.DataFrame({"road": ["A1", "A1"], "chainage_km": [2.0, 40.0],
                             "marker_distance_m": [10.0, 10.0]})
    segments = pd.DataFrame({
        "road": ["A1"], "km_from": [0.0], "km_to": [10.0], "aadt": [5000.0],
        "heavy_pct": [12.0], "aadt_censored": [False],
    })
    out, _ = cg.attach_aadt(chainage, segments)
    assert out["aadt"].iloc[0] == 5000.0
    assert pd.isna(out["aadt"].iloc[1]), "km 40 is outside the 0-10 segment"
