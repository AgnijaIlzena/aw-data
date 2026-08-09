"""Phase 1 contracts: the three reference-geography readers.

Split deliberately into two kinds of test.

**Synthetic** tests pin the logic and run everywhere — the -9999 sentinel, the
centroid offset, the audit trail. These must pass before the readers are wired to
real files.

**Real-file** tests pin the readers against what is actually on disk and skip
when `dati/` is absent. They exist because project #1's three worst bugs all had
the same cause: trusting a description of a file over the file.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import pandas as pd
from shapely.geometry import Point, Polygon

from actionwise_geo import config as gc
from actionwise_geo.data import boundaries as bd
from actionwise_geo.data import depots as dp
from actionwise_geo.data import popgrid as pg

requires_raw = pytest.mark.skipif(
    not gc.VUGD_DEPOTS_CSV.exists(), reason="dati/ not present in this checkout"
)


# ══════════════════════════════════════════════════════════════════════════
# depots
# ══════════════════════════════════════════════════════════════════════════

@requires_raw
def test_depots_load_as_points_in_the_working_crs():
    gdf, audit = dp.load_depots()
    assert len(gdf) == gc.VUGD_N_DEPOTS
    assert gdf.crs.to_epsg() == gc.CRS_WORKING
    assert gdf.geometry.notna().all(), "every depot must have a coordinate"
    assert {"nosaukums", "adrese", "regiona_piederiba"} <= set(gdf.columns)


@requires_raw
def test_depots_fall_inside_latvia():
    """Catches the mislabelled-CRS failure at the point of loading."""
    gdf, _ = dp.load_depots()
    minx, miny, maxx, maxy = gc.LV_BBOX_3059
    assert gdf.geometry.x.between(minx, maxx).all()
    assert gdf.geometry.y.between(miny, maxy).all()


@requires_raw
def test_depot_regional_breakdown_matches_the_file_itself():
    """A truncated read shows up here long before it shows up as a wrong map."""
    gdf, _ = dp.load_depots()
    assert gdf["regiona_piederiba"].value_counts().to_dict() == gc.DEPOTS_PER_REGION


@requires_raw
def test_depot_load_records_an_audit_trail():
    _, audit = dp.load_depots()
    trail = audit.to_frame()
    assert not trail.empty
    assert {"step", "rows_in", "rows_out", "reason"} <= set(trail.columns)
    assert trail["rows_out"].iloc[-1] == gc.VUGD_N_DEPOTS


@requires_raw
def test_crosscheck_register_is_not_returned_as_mappable_geometry():
    """Its coordinates are degrees; making it awkward to map is deliberate."""
    reg = dp.load_depots_crosscheck()
    assert not isinstance(reg, gpd.GeoDataFrame), (
        "the property register must come back as a plain DataFrame so it cannot "
        "be plotted or measured by accident"
    )
    assert len(reg) == 99


@requires_raw
def test_property_register_is_missing_real_depots():
    """Evidence for the rule 'never use the register as a source'.

    At a 2 km tolerance — wide enough to see past the register's parcel-level
    coordinate imprecision — several genuine depots have no counterpart in it at
    all, and it contributes buildings that are not depots.
    """
    depots, _ = dp.load_depots()
    diff = dp.compare_depot_sources(depots, dp.load_depots_crosscheck(),
                                    tolerance_m=2_000)

    missing = diff[diff["source"] == "csv_only"]
    assert len(missing) >= 5, (
        "the register should be missing real depots; if it no longer is, revisit "
        "which file is authoritative"
    )
    assert (missing["distance_m"] > 5_000).any(), "some are missing by tens of km"


@requires_raw
def test_source_comparison_is_meaningless_without_its_tolerance():
    """The count is strongly tolerance-dependent — 62 at 250 m, ~10 at 5 km.

    Pinned so nobody quotes a mismatch count without the threshold that produced
    it: the two files disagree about WHERE depots are as much as about which exist.
    """
    depots, _ = dp.load_depots()
    register = dp.load_depots_crosscheck()

    tight = len(dp.compare_depot_sources(depots, register, tolerance_m=250))
    loose = len(dp.compare_depot_sources(depots, register, tolerance_m=5_000))
    assert tight > loose * 3, (
        "if the count stopped depending on tolerance, the register's coordinate "
        "precision changed and the 2 km default should be revisited"
    )


# ══════════════════════════════════════════════════════════════════════════
# boundaries
# ══════════════════════════════════════════════════════════════════════════

@requires_raw
def test_boundaries_load_with_the_expected_shape():
    gdf, _ = bd.load_boundaries()
    assert len(gdf) == gc.BOUNDARIES_N_FEATURES
    assert gdf.crs.to_epsg() == gc.CRS_WORKING
    assert {"nosaukums", "atrib", "is_city"} <= set(gdf.columns)


@requires_raw
def test_city_flag_agrees_with_both_the_code_and_the_name():
    """`atrib` is the classification; the ' nov.' suffix is a naming convention.

    They should agree. Where they disagree, the code wins — but the disagreement
    itself means the file changed and is worth an error.
    """
    gdf, _ = bd.load_boundaries()
    assert gdf["is_city"].sum() == gc.BOUNDARIES_N_CITIES
    by_name = ~gdf["nosaukums"].str.endswith(" nov.")
    assert (gdf["is_city"] == by_name).all()
    assert set(gdf.loc[gdf["is_city"], "nosaukums"]) == {
        "Rīga", "Daugavpils", "Jelgava", "Jūrmala", "Liepāja", "Rēzekne", "Ventspils"
    }


@requires_raw
def test_the_known_missing_municipality_is_still_missing():
    """42 features is not all of Latvia — this is a documented gap, not a bug.

    If Varakļāni ever appears, Phase 6's join reconciliation changes, so the
    expectation is asserted rather than left in a comment.
    """
    gdf, _ = bd.load_boundaries()
    for missing in gc.BOUNDARIES_MISSING:
        assert missing not in set(gdf["nosaukums"])


@requires_raw
def test_wrong_feature_count_raises_rather_than_being_absorbed():
    with pytest.raises(ValueError):
        bd.load_boundaries(layer="does_not_exist")


def _box_and_points():
    poly = gpd.GeoDataFrame(
        {"nosaukums": ["Box"], "atrib": ["0001000"], "is_city": [True]},
        geometry=[Polygon([(0, 0), (0, 100), (100, 100), (100, 0)])],
        crs=gc.CRS_WORKING,
    )
    pts = gpd.GeoDataFrame(
        {"id": [1, 2]},
        geometry=[Point(50, 50), Point(5_000, 5_000)],   # inside, far outside
        crs=gc.CRS_WORKING,
    )
    return poly, pts


def test_assign_municipality_keeps_unmatched_points_visible():
    """An unmatched point is the project's most useful diagnostic — never dropped."""
    poly, pts = _box_and_points()
    out, audit = bd.assign_municipality(pts, poly)

    assert len(out) == 2, "unmatched points must survive the join"
    assert out.loc[out["id"] == 1, "municipality"].iloc[0] == "Box"
    assert pd.isna(out.loc[out["id"] == 2, "municipality"].iloc[0])
    assert audit.to_frame()["cells_nulled"].iloc[-1] == 1, "the unmatched count is recorded"


def test_assign_municipality_survives_a_name_column_on_both_sides():
    """Both frames legitimately use `nosaukums` — depot name vs municipality name.

    The synthetic fixture above has no name column, so it never hits this; the
    real depot register does, and an unrenamed join suffixes both away.
    """
    poly, pts = _box_and_points()
    pts = pts.assign(nosaukums=["VUGD Rīgas daļa", "VUGD Talsu daļa"])

    out, _ = bd.assign_municipality(pts, poly)

    assert out["nosaukums"].tolist() == ["VUGD Rīgas daļa", "VUGD Talsu daļa"], (
        "the point's own name must survive untouched"
    )
    assert out.loc[out["id"] == 1, "municipality"].iloc[0] == "Box"
    assert "municipality_atrib" in out.columns


# ══════════════════════════════════════════════════════════════════════════
# population grid
# ══════════════════════════════════════════════════════════════════════════

def test_decode_grd_id_reads_the_corner_coordinates():
    s = pd.Series(["CRS3035RES1000mN3731000E5018000",
                   "CRS3035RES1000mN3767000E5084000"])
    out = pg.decode_grd_id(s)
    assert list(out["north"]) == [3_731_000, 3_767_000]
    assert list(out["east"]) == [5_018_000, 5_084_000]
    assert set(out["resolution_m"]) == {1000}
    assert set(out["crs_epsg"]) == {gc.CRS_ETRS89_LAEA}


def test_decode_grd_id_nulls_unparseable_ids_instead_of_raising():
    out = pg.decode_grd_id(pd.Series(["CRS3035RES1000mN3731000E5018000", "rubbish"]))
    assert out["north"].notna().iloc[0]
    assert out["north"].isna().iloc[1]


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_grid_loads_only_latvia_and_reconciles_to_the_census():
    grid, audit = pg.load_population_grid()
    assert len(grid) == gc.POPGRID_LV_CELLS
    assert grid.crs.to_epsg() == gc.CRS_WORKING

    total = grid["T"].sum()
    assert total == gc.POPGRID_LV_POPULATION
    delta = abs(total - gc.POPULATION_LV_CENSUS_2021) / gc.POPULATION_LV_CENSUS_2021
    assert delta < gc.SANITY_POPULATION_TOLERANCE


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_suppressed_age_bands_become_null_never_zero():
    """The single most damaging trap in this dataset.

    Left as -9999, Y_GE65 sums to -211 million. Replaced with 0, it is quietly
    wrong — understating the elderly in exactly the sparse, remote cells the
    23-minute analysis is about. Null is the only honest value.
    """
    grid, _ = pg.load_population_grid()
    for band in gc.POPGRID_AGE_BANDS:
        assert (grid[band].dropna() >= 0).all(), f"{band} still carries the sentinel"
        assert grid[band].sum() > 0, f"{band} must not sum negative"

    assert grid["age_suppressed"].sum() > 0
    assert grid.loc[grid["age_suppressed"], gc.POPGRID_AGE_BANDS[0]].isna().all()
    # T is never suppressed, so it must survive intact.
    assert grid["T"].notna().all() and (grid["T"] >= 0).all()


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_density_uses_land_surface_as_a_fraction_not_an_area():
    """LAND_SURFACE is 0.0-1.0. Treating it as km² inverts the whole calculation."""
    grid, _ = pg.load_population_grid()
    populated = grid[grid["T"] > 0]
    assert (populated["land_km2"] > 0).all(), "no populated cell is pure water"
    assert (populated["land_km2"] <= 1.0001).all(), "a 1 km cell cannot exceed 1 km²"
    # Partial-land cells must come out denser than the naive T/1km² figure.
    partial = populated[populated["land_km2"] < 0.5]
    if len(partial):
        assert (partial["density"] > partial["T"]).all()


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_age_bands_are_not_expected_to_reconcile_cell_by_cell():
    """Disclosure perturbation: they agree nationally, not per cell.

    Asserted so nobody later "fixes" a reconciliation that was never meant to hold.
    """
    assert gc.POPGRID_BANDS_RECONCILE_TO_TOTAL is False
    grid, _ = pg.load_population_grid()
    usable = grid[(grid["T"] > 0) & ~grid["age_suppressed"]]
    banded = usable[list(gc.POPGRID_AGE_BANDS)].sum(axis=1)
    assert (banded == usable["T"]).mean() < 0.5
    assert abs(banded.sum() - usable["T"].sum()) / usable["T"].sum() < 0.001


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_unallocated_population_is_kept_flagged_and_unmappable():
    """4,844 people exist in the census with no grid square.

    Dropping them makes every coverage share disagree with the census by 0.26%
    for no visible reason; mapping them would invent a location. The only correct
    handling is to keep the row, give it no geometry, and expose both denominators.
    """
    grid, _ = pg.load_population_grid()

    unallocated = grid[grid["unallocated"]]
    assert len(unallocated) == 1
    assert unallocated["T"].iloc[0] == gc.POPGRID_LV_UNALLOCATED_POPULATION
    assert unallocated.geometry.isna().all(), "it must not be given a fake location"

    cov = pg.population_coverage(grid)
    assert cov["unallocated_population"] == gc.POPGRID_LV_UNALLOCATED_POPULATION
    assert cov["mappable_population"] == cov["population"] - cov["unallocated_population"]
    # The national total is the one that reconciles to the census.
    assert cov["population"] == gc.POPGRID_LV_POPULATION


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_every_other_grd_id_parses():
    """Exactly one row is unparseable, and it is the unallocated pseudo-cell."""
    grid, audit = pg.load_population_grid()
    trail = audit.to_frame()
    decode = trail[trail["step"] == "decode_grid_geometry"].iloc[0]
    assert decode["cells_nulled"] == 0, (
        "a GRD_ID that fails to parse and is NOT the unallocated row is a defect"
    )
    assert grid.loc[~grid["unallocated"]].geometry.notna().all()


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_cells_without_land_carry_no_population():
    """165 cells have zero land area, hence a null density. None hold people."""
    grid, _ = pg.load_population_grid()
    no_land = grid[grid["density"].isna() & grid["geometry"].notna()]
    assert (no_land["T"] == 0).all(), "a null density must never hide population"


@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="grid archive not present")
def test_coverage_summary_reports_both_halves_of_the_suppression_story():
    """65% of cells lack age detail; they hold 4.9% of people. Both belong in the card."""
    grid, _ = pg.load_population_grid()
    cov = pg.population_coverage(grid)

    assert cov["populated_cells"] == gc.POPGRID_LV_POPULATED_CELLS
    assert cov["age_suppressed_cells"] == gc.POPGRID_LV_AGE_SUPPRESSED_CELLS
    assert cov["age_coverage_share"] == pytest.approx(
        gc.POPGRID_LV_AGE_COVERED_POPULATION_SHARE, abs=0.005
    )
