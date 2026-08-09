"""The gate must fail when the geography is broken.

A gate that only ever passes is decoration. Most of these tests deliberately
break something — the CRS, the join, a count — and assert that the gate notices.
The real-data test at the end is the one that must stay green.

Mirrors `tests/test_sanity_gate.py`, which does the same for project #1.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import pandas as pd
from shapely.geometry import Point, Polygon

from actionwise_geo import config as gc
from actionwise_geo.validate import sanity

# A miniature Latvia: one big "Rīga" square holding a third of the people, one
# rural square, and two depots. Everything sits inside LV_BBOX_3059.
BASE_X, BASE_Y = 500_000, 300_000


def synthetic_boundaries() -> gpd.GeoDataFrame:
    def square(x, y, size=20_000):
        return Polygon([(x, y), (x, y + size), (x + size, y + size), (x + size, y)])

    return gpd.GeoDataFrame(
        {
            "nosaukums": ["Rīga", "Talsu nov."],
            "atrib": ["0001000", "0088000"],
            "is_city": [True, False],
        },
        geometry=[square(BASE_X, BASE_Y), square(BASE_X + 30_000, BASE_Y)],
        crs=gc.CRS_WORKING,
    )


def synthetic_depots(n_by_region: dict | None = None) -> gpd.GeoDataFrame:
    counts = n_by_region or dict(gc.DEPOTS_PER_REGION)
    regions, xs, ys = [], [], []
    i = 0
    for region, n in counts.items():
        for _ in range(n):
            regions.append(region)
            # spread inside the two squares so they all land in a municipality
            xs.append(BASE_X + 1_000 + (i % 15) * 1_000)
            ys.append(BASE_Y + 1_000 + (i % 15) * 1_000)
            i += 1
    return gpd.GeoDataFrame(
        {"regiona_piederiba": regions, "nosaukums": [f"depot{j}" for j in range(len(xs))]},
        geometry=[Point(x, y) for x, y in zip(xs, ys)],
        crs=gc.CRS_WORKING,
    )


def synthetic_grid(n_cells: int = gc.POPGRID_LV_CELLS) -> gpd.GeoDataFrame:
    """Two populated cells carrying the census total, plus empty padding."""
    riga_pop = int(gc.POPULATION_LV_CENSUS_2021 * 0.324)
    rural_pop = gc.POPULATION_LV_CENSUS_2021 - riga_pop

    rows = {
        "grd_id": ["a", "b"],
        "T": [riga_pop, rural_pop],
        "density": [2_000.0, 50.0],
        "land_km2": [1.0, 1.0],
        "age_suppressed": [False, False],
        "unallocated": [False, False],
    }
    geometry = [Point(BASE_X + 5_000, BASE_Y + 5_000),
                Point(BASE_X + 35_000, BASE_Y + 5_000)]

    pad = n_cells - 2
    for key, value in (("grd_id", "pad"), ("T", 0), ("density", 0.0),
                       ("land_km2", 1.0), ("age_suppressed", False),
                       ("unallocated", False)):
        rows[key] = list(rows[key]) + [value] * pad
    geometry += [Point(BASE_X + 6_000, BASE_Y + 6_000)] * pad

    return gpd.GeoDataFrame(rows, geometry=geometry, crs=gc.CRS_WORKING)


@pytest.fixture
def layers():
    return synthetic_depots(), synthetic_boundaries(), synthetic_grid()


# ── the gate passes on sound geography ─────────────────────────────────────

def test_gate_passes_on_consistent_layers(layers):
    result = sanity.run_gate(*layers)
    failures = result[~result["pass"]]
    assert failures.empty, f"unexpected failures:\n{failures.to_string(index=False)}"


def test_gate_reports_every_check_it_ran(layers):
    result = sanity.run_gate(*layers)
    assert {"check", "expected", "observed", "pass", "note"} <= set(result.columns)
    assert len(result) >= 10


# ── and fails when something is actually wrong ─────────────────────────────

def test_gate_catches_a_layer_in_the_wrong_crs(layers):
    """The failure this whole module exists for."""
    depots, boundaries, grid = layers
    depots = depots.to_crs(epsg=gc.CRS_WGS84)
    result = sanity.run_gate(depots, boundaries, grid)
    assert not result.loc[result["check"] == "CRS of depots", "pass"].iloc[0]


def test_gate_catches_displaced_depots_that_still_sit_inside_the_bbox():
    """A bbox check would pass this; the containment check must not.

    Depots shifted into the sea between the two municipalities are inside
    Latvia's bounding box and inside no territory — exactly what a subtly wrong
    CRS or a bad transform produces.
    """
    boundaries = synthetic_boundaries()
    depots = synthetic_depots()
    depots["geometry"] = depots.geometry.translate(xoff=25_000)   # into the gap

    result = sanity.run_gate(depots, boundaries, synthetic_grid())
    row = result[result["check"] == "depots inside a municipality"].iloc[0]
    assert not row["pass"]


def test_gate_catches_a_wrong_depot_count():
    counts = dict(gc.DEPOTS_PER_REGION)
    counts["Kurzemes reģiona pārvalde"] -= 1        # one depot silently lost
    result = sanity.run_gate(synthetic_depots(counts), synthetic_boundaries(),
                             synthetic_grid())
    assert not result.loc[result["check"] == "depot count", "pass"].iloc[0]
    assert not result.loc[result["check"] == "depots per region", "pass"].iloc[0]


def test_gate_catches_a_population_total_that_drifted(layers):
    depots, boundaries, grid = layers
    grid = grid.copy()
    grid.loc[grid.index[0], "T"] = int(grid.loc[grid.index[0], "T"] * 0.5)
    result = sanity.run_gate(depots, boundaries, grid)
    assert not result.loc[
        result["check"] == "grid population vs census 2021", "pass"
    ].iloc[0]


def test_gate_catches_population_stranded_far_from_any_territory():
    """Coastal rounding is fine; a cell 200 km out is a broken CRS."""
    boundaries = synthetic_boundaries()
    grid = synthetic_grid()
    grid.loc[grid.index[1], "geometry"] = Point(BASE_X + 200_000, BASE_Y + 100_000)

    result = sanity.run_gate(synthetic_depots(), boundaries, grid)
    offshore = result[result["check"] == "unplaced cells are coastal"]
    stranded = result[result["check"] == "population outside every territory"]
    assert not offshore["pass"].iloc[0] or not stranded["pass"].iloc[0]


def test_format_gate_says_stop_when_a_check_fails(layers):
    depots, boundaries, grid = layers
    text = sanity.format_gate(sanity.run_gate(depots.to_crs(epsg=4326), boundaries, grid))
    assert "GATE FAILED" in text and "STOP" in text


def test_format_gate_is_readable(layers):
    """A gate nobody reads is not a gate — no row may blow out the width."""
    text = sanity.format_gate(sanity.run_gate(*layers))
    assert "GATE PASSED" in text
    assert max(len(line) for line in text.splitlines()) < 200


# ── the density diagnostic is NOT a gate ───────────────────────────────────

def test_density_comparison_is_reported_not_gated(layers):
    """The plan called for a rank-order check. The measured data refutes it.

    Grid and survey disagree on rank order (grid puts rural above cluster, the
    survey the reverse) because self-reported community type and measured density
    are different constructs. This asserts the comparison stays a diagnostic —
    it must never appear among the gate's pass/fail rows.
    """
    _, _, grid = layers
    result = sanity.run_gate(*layers)
    assert not result["check"].str.contains("d25|community|density class",
                                            case=False, regex=True).any()

    comparison = sanity.density_class_comparison(
        grid, {"rural": 0.291, "urban_cluster": 0.321, "urban_centre": 0.389}
    )
    assert set(comparison["class"]) == {"urban_centre", "urban_cluster", "rural"}
    assert "gap_pp" in comparison.columns
    assert "never gated" in comparison.attrs["warning"].lower()


def test_density_classes_use_the_official_eurostat_thresholds(layers):
    _, _, grid = layers
    shares = sanity.density_class_distribution(grid)
    assert shares.sum() == pytest.approx(1.0)
    assert gc.DEGURBA_URBAN_CENTRE_MIN == 1500
    assert gc.DEGURBA_URBAN_CLUSTER_MIN == 300


# ── and it must hold on the real data ──────────────────────────────────────

@pytest.mark.skipif(not gc.POPGRID_ZIP.exists(), reason="dati/ not present")
def test_gate_passes_on_the_real_data():
    """The check that matters. Everything downstream inherits this geography."""
    from actionwise_geo.data.boundaries import load_boundaries
    from actionwise_geo.data.depots import load_depots
    from actionwise_geo.data.popgrid import load_population_grid

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)

    result = sanity.run_gate(depots, boundaries, grid)
    failures = result[~result["pass"]]
    assert failures.empty, (
        "the geography gate failed on real data — stop and fix the readers "
        f"before anything downstream:\n{failures.to_string(index=False)}"
    )
