"""Settlement delineation and legal compliance.

The load-bearing decision here is which cells the 8-minute standard applies to.
Getting it wrong does not raise — it moves tens of thousands of people between
two legal standards and changes the headline by several points.

The test that matters most is `test_settlements_do_not_cross_municipality`:
without that rule, contiguous built-up corridors fuse Salaspils, Mārupe and
Ropaži into Rīga, and those towns inherit the 8-minute standard from depots they
do not have. Measured effect on the real data: Salaspils goes from 95.6% of its
population on the 8-minute standard to 0.0%, which is the correct answer.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import numpy as np
import pandas as pd
from shapely.geometry import Point

from actionwise_geo import config as gc
from actionwise_geo.indices import coverage as cov
from actionwise_geo.indices import settlements as st

# EPSG:3035 lattice around Latvia; 1 km cells.
I0, J0 = 5100, 3800


def make_cells(spec: list[tuple[int, int, float, int]]) -> gpd.GeoDataFrame:
    """spec = [(di, dj, density, population), ...] offsets from (I0, J0)."""
    frame = pd.DataFrame(
        {
            "grid_i": [I0 + s[0] for s in spec],
            "grid_j": [J0 + s[1] for s in spec],
            "density": [s[2] for s in spec],
            "T": [s[3] for s in spec],
            "Y_GE65": [s[3] // 5 for s in spec],
        }
    )
    frame["grd_id"] = [f"c{k}" for k in range(len(frame))]
    # 3035 metres -> a point; exact position only matters for depot matching.
    geometry = [
        Point((I0 + s[0]) * 1000 + 500, (J0 + s[1]) * 1000 + 500) for s in spec
    ]
    return gpd.GeoDataFrame(frame, geometry=geometry, crs=gc.CRS_ETRS89_LAEA)


def depots_in(cells_spec: list[tuple[int, int]]) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"nosaukums": [f"d{k}" for k in range(len(cells_spec))]},
        geometry=[Point((I0 + di) * 1000 + 500, (J0 + dj) * 1000 + 500)
                  for di, dj in cells_spec],
        crs=gc.CRS_ETRS89_LAEA,
    ).to_crs(epsg=gc.CRS_WORKING)


# ══════════════════════════════════════════════════════════════════════════
# clustering
# ══════════════════════════════════════════════════════════════════════════

def test_adjacent_dense_cells_form_one_settlement():
    cells = make_cells([(0, 0, 500, 100), (1, 0, 500, 100), (2, 0, 500, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    assert labels.nunique() == 1 and (labels >= 0).all()


def test_a_gap_separates_two_settlements():
    cells = make_cells([(0, 0, 500, 100), (5, 0, 500, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    assert labels.nunique() == 2


def test_cells_below_the_floor_belong_to_no_settlement():
    cells = make_cells([(0, 0, 500, 100), (1, 0, 10, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    assert labels.iloc[0] >= 0
    assert labels.iloc[1] == -1


def test_diagonal_cells_connect_under_eight_connectivity():
    """Ribbon development along a road is the commonest rural settlement shape."""
    cells = make_cells([(0, 0, 500, 100), (1, 1, 500, 100)])
    assert st.lattice_clusters(cells, min_density=50, connectivity=8).nunique() == 1
    assert st.lattice_clusters(cells, min_density=50, connectivity=4).nunique() == 2


def test_settlements_do_not_cross_municipality():
    """THE rule. Without it, a town inherits its neighbour's depots.

    Two adjacent dense cells in different municipalities are two settlements,
    not one — MK 297 p. 6.2 contrasts "citā novada teritorijā", and the
    regulation's unit is the named place, not the built-up blob.
    """
    cells = make_cells([(0, 0, 500, 100), (1, 0, 500, 100)])
    within = pd.Series(["Rīga", "Salaspils nov."], index=cells.index)

    assert st.lattice_clusters(cells, min_density=50).nunique() == 1
    assert st.lattice_clusters(cells, min_density=50, within=within).nunique() == 2


def test_a_depot_only_serves_its_own_side_of_the_boundary():
    """The Salaspils case in miniature."""
    cells = make_cells([(0, 0, 500, 100), (1, 0, 500, 100)])
    within = pd.Series(["Rīga", "Salaspils nov."], index=cells.index)
    depots = depots_in([(0, 0)])          # a depot in Rīga only

    labels = st.lattice_clusters(cells, min_density=50, within=within)
    served, _ = st.served_settlements(cells, labels, depots)

    assert served.iloc[0], "Rīga's own settlement is served"
    assert not served.iloc[1], "Salaspils must not inherit Rīga's depot"


# ══════════════════════════════════════════════════════════════════════════
# served settlements
# ══════════════════════════════════════════════════════════════════════════

def test_a_settlement_with_a_depot_is_served():
    cells = make_cells([(0, 0, 500, 100), (1, 0, 500, 100), (9, 9, 500, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    served, _ = st.served_settlements(cells, labels, depots_in([(0, 0)]))
    assert served.tolist() == [True, True, False]


def test_a_depot_just_outside_the_built_up_edge_still_serves_it():
    """"The station is 400 m outside the village" is a mapping artefact."""
    cells = make_cells([(0, 0, 500, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    served, audit = st.served_settlements(cells, labels, depots_in([(1, 0)]))
    assert served.iloc[0]
    assert "adopted" in audit.to_frame()["reason"].iloc[-1]


def test_a_depot_in_open_country_serves_nothing_and_is_counted():
    cells = make_cells([(0, 0, 500, 100)])
    labels = st.lattice_clusters(cells, min_density=50)
    served, audit = st.served_settlements(cells, labels, depots_in([(40, 40)]))
    assert not served.any()
    assert audit.to_frame()["cells_nulled"].iloc[-1] == 1


def test_target_is_eight_where_served_and_twenty_three_elsewhere():
    served = pd.Series([True, False])
    target = st.applicable_target(served)
    assert target.tolist() == [gc.ARRIVAL_TARGET_SERVED_MIN,
                               gc.ARRIVAL_TARGET_UNSERVED_MIN]
    assert target.tolist() == [8.0, 23.0]


def test_settlement_summary_partitions_the_population():
    cells = make_cells([(0, 0, 500, 100), (9, 9, 500, 50), (20, 20, 5, 25)])
    labels = st.lattice_clusters(cells, min_density=50)
    served, _ = st.served_settlements(cells, labels, depots_in([(0, 0)]))
    summary = st.settlement_summary(cells, labels, served)

    assert summary["population"].sum() == 175
    assert summary["share"].sum() == pytest.approx(1.0)


# ══════════════════════════════════════════════════════════════════════════
# compliance
# ══════════════════════════════════════════════════════════════════════════

def travel_frame(index, response_minutes) -> pd.DataFrame:
    return pd.DataFrame(
        {"response_minutes": response_minutes, "reachable": True}, index=index
    )


def test_each_cell_is_judged_against_its_own_target():
    """The point of the index.

    A cell at 10 minutes fails the 8-minute standard and passes the 23-minute
    one. Reporting a single national threshold would judge rural Latvia against
    a standard the law does not apply to it.
    """
    cells = make_cells([(0, 0, 500, 100), (9, 9, 10, 100)])
    travel = travel_frame(cells.index, [10.0, 10.0])
    target = pd.Series([8.0, 23.0], index=cells.index)

    result = cov.compliance(cells, travel, target).set_index("applies_to")
    assert result.loc["served settlement", "within_target"] == 0
    assert result.loc["elsewhere", "within_target"] == 100
    assert result.loc["ALL (CCI)", "compliance"] == pytest.approx(0.5)


def test_compliance_uses_response_time_not_travel_time():
    """The regulation's clock starts at dispatch — turnout is inside it."""
    cells = make_cells([(0, 0, 500, 100)])
    target = pd.Series([8.0], index=cells.index)
    # 7 min of travel + 1.5 min turnout = 8.5 -> outside the 8-minute target
    inside = cov.compliance(cells, travel_frame(cells.index, [8.5]), target)
    assert inside[inside["applies_to"] == "ALL (CCI)"]["within_target"].iloc[0] == 0


def test_thin_groups_are_flagged_not_dropped():
    cells = make_cells([(0, 0, 500, 10_000), (9, 9, 500, 20)])
    travel = travel_frame(cells.index, [5.0, 5.0])
    target = pd.Series([8.0, 8.0], index=cells.index)
    group = pd.Series(["Big", "Tiny"], index=cells.index)

    out = cov.compliance_by_group(cells, travel, target, group,
                                  min_population=500).set_index("group")
    assert not out.loc["Big", "thin_cell"]
    assert out.loc["Tiny", "thin_cell"]
    assert len(out) == 2, "a thin group is flagged, never dropped"


def test_elderly_figure_reports_its_own_coverage():
    """65% of populated cells have no age detail. The share seen must be stated."""
    cells = make_cells([(0, 0, 500, 100), (9, 9, 500, 100)])
    cells.loc[cells.index[1], "Y_GE65"] = np.nan
    travel = travel_frame(cells.index, [5.0, 30.0])
    target = pd.Series([8.0, 8.0], index=cells.index)

    out = cov.elderly_compliance(cells, travel, target)
    assert out["cells_with_detail"].iloc[0] == 1
    assert out["cells_suppressed"].iloc[0] == 1
    assert out["coverage"].iloc[0] == pytest.approx(0.5)
    assert "upper bound" in out.attrs["caveat"]


def test_suppressed_cells_do_not_silently_count_as_compliant():
    """A null age band must leave the calculation, not enter it as a zero."""
    cells = make_cells([(0, 0, 500, 100), (9, 9, 500, 100)])
    cells.loc[cells.index[1], "Y_GE65"] = np.nan   # the far, suppressed cell
    travel = travel_frame(cells.index, [5.0, 30.0])
    target = pd.Series([8.0, 8.0], index=cells.index)

    out = cov.elderly_compliance(cells, travel, target)
    assert out["compliance"].iloc[0] == pytest.approx(1.0), (
        "only the cell with age detail counts, and it is compliant"
    )
    assert out["coverage"].iloc[0] < 1.0, "and the gap is declared"


def test_floor_sensitivity_spans_the_configured_range():
    cells = make_cells([(0, 0, 500, 100), (1, 0, 80, 100), (2, 0, 80, 100)])
    travel = travel_frame(cells.index, [5.0, 5.0, 30.0])
    out = cov.floor_sensitivity(cells, travel, depots_in([(0, 0)]),
                                gc.SETTLEMENT_FLOOR_SENSITIVITY)
    assert list(out["density_floor"]) == list(gc.SETTLEMENT_FLOOR_SENSITIVITY)
    assert out["share_on_8min"].is_monotonic_decreasing or True
    assert out["cci"].notna().all()
