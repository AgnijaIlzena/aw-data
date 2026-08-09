"""The Preparedness–Proximity matrix — the join between the two projects.

Three things are pinned here, and each guards against a different way of
producing a confident wrong answer:

  * the two axes are never combined into one number — RHI and TTH describe
    different scenarios, and a ratio would imply otherwise;
  * the classes are calibrated before comparison, or the two sides partition
    Latvia differently and the table compares different groups of people;
  * RHI stays a bracket. Band 2 is literally "2-3 days", so whether such a
    household clears a 3-day target is unknowable, and collapsing to a midpoint
    would turn the upper bound into an estimate.
"""
import pytest

pytest.importorskip("geopandas", reason="geo extra not installed")
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from actionwise.config import RESILIENCE_TARGET_DAYS
from actionwise_geo import config as gc
from actionwise_geo.indices import matrix as mx


def cells_with(densities, populations) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"T": populations, "density": densities,
         "grd_id": [f"c{k}" for k in range(len(densities))]},
        geometry=[Point(500_000 + 1000 * k, 300_000) for k in range(len(densities))],
        crs=gc.CRS_WORKING,
    )


def survey_with(rows) -> pd.DataFrame:
    """rows = [(community_class, rhi_days, rhi_band, weight), ...]"""
    return pd.DataFrame(rows, columns=["community_class", "rhi_days", "rhi_band",
                                       "w_national"])


# ── calibration ────────────────────────────────────────────────────────────

def test_calibration_reproduces_the_survey_split():
    """Both sides must describe the same three groups of people."""
    cells = cells_with(
        densities=[10, 50, 200, 600, 1200, 5000],
        populations=[100, 100, 100, 100, 100, 100],
    )
    target = pd.Series({"rural": 1 / 3, "urban_cluster": 1 / 3, "urban_centre": 1 / 3})
    thresholds = mx.calibrate_density_thresholds(cells, target)
    classes = mx.classify_cells(cells, thresholds)

    shares = cells.groupby(classes)["T"].sum() / cells["T"].sum()
    for name in mx.CLASSES:
        assert shares.get(name, 0) == pytest.approx(1 / 3, abs=0.2)


def test_uncalibrated_classes_use_the_official_degurba_cutoffs():
    cells = cells_with([100, 500, 2000], [10, 10, 10])
    classes = mx.classify_cells(cells, None)
    assert classes.tolist() == ["rural", "urban_cluster", "urban_centre"]
    assert gc.DEGURBA_URBAN_CLUSTER_MIN == 300
    assert gc.DEGURBA_URBAN_CENTRE_MIN == 1500


def test_cells_without_a_density_are_not_classified():
    cells = cells_with([np.nan, 500], [10, 10])
    assert pd.isna(mx.classify_cells(cells, None).iloc[0])


# ── the RHI axis stays a bracket ───────────────────────────────────────────

def test_preparedness_reports_a_bracket_not_a_point():
    """Band 2 is '2-3 days'. Whether it clears a 3-day target is unknowable."""
    survey = survey_with([
        ("rural", 1.0, 1, 1.0),    # certainly under 3 days
        ("rural", 2.5, 2, 1.0),    # "2-3 days" — could be exactly 3
        ("rural", 5.5, 3, 1.0),
        ("rural", 10.0, 4, 1.0),
    ])
    out = mx.preparedness_by_class(survey).set_index("community_class")
    row = out.loc["rural"]

    assert row["share_under_target_certain"] == pytest.approx(0.25)
    assert row["share_under_target_upper"] == pytest.approx(0.50)
    assert row["share_under_target_certain"] < row["share_under_target_upper"], (
        "collapsing the bracket would turn the upper bound into an estimate"
    )


def test_intervals_use_effective_sample_size_not_row_count():
    """Weights inflate variance; an interval built on n would be too narrow."""
    rng = np.random.default_rng(0)
    n = 200
    survey = pd.DataFrame({
        "community_class": ["rural"] * n,
        "rhi_days": rng.choice([1.0, 2.5, 5.5, 10.0], n),
        "rhi_band": rng.choice([1, 2, 3, 4], n),
        "w_national": rng.uniform(0.1, 5.0, n),   # highly variable weights
    })
    out = mx.preparedness_by_class(survey).iloc[0]
    assert out["n_effective"] < out["n"], "Kish n_eff must be below the raw count"
    assert out["ci_low"] < out["share_under_target_upper"] < out["ci_high"]


def test_thin_classes_are_flagged():
    survey = survey_with([("rural", 1.0, 1, 1.0)] * 20)
    out = mx.preparedness_by_class(survey).set_index("community_class")
    assert out.loc["rural", "thin_cell"]
    assert not out.loc["rural", "n"] == 0, "a thin class is flagged, never dropped"


def test_an_absent_class_produces_a_row_rather_than_vanishing():
    survey = survey_with([("rural", 1.0, 1, 1.0)])
    out = mx.preparedness_by_class(survey)
    assert set(out["community_class"]) == set(mx.CLASSES)
    assert pd.isna(out.set_index("community_class").loc["urban_centre", "mean_rhi_days"])


# ── the proximity axis ─────────────────────────────────────────────────────

def test_proximity_is_population_weighted():
    cells = cells_with([100, 100], [900, 100])
    travel = pd.DataFrame(
        {"response_minutes": [10.0, 20.0], "reachable": True}, index=cells.index
    )
    classes = pd.Series(["rural", "rural"], index=cells.index)
    out = mx.proximity_by_class(cells, travel, classes).set_index("community_class")
    # 900 people at 10 min, 100 at 20 -> 11, not the unweighted 15
    assert out.loc["rural", "mean_response_min"] == pytest.approx(11.0)


# ── the matrix itself ──────────────────────────────────────────────────────

def test_the_matrix_never_combines_the_two_axes():
    """A ratio would imply RHI and TTH describe one scenario. They do not."""
    cells = cells_with([100, 2000], [500, 500])
    travel = pd.DataFrame(
        {"response_minutes": [12.0, 5.0], "reachable": True}, index=cells.index
    )
    classes = pd.Series(["rural", "urban_centre"], index=cells.index)
    survey = survey_with([("rural", 5.5, 3, 1.0), ("urban_centre", 1.0, 1, 1.0)])

    result = mx.proximity_matrix(
        mx.proximity_by_class(cells, travel, classes),
        mx.preparedness_by_class(survey),
    )
    combined = [c for c in result.columns
                if any(k in c for k in ("ratio", "score", "index", "product"))]
    assert not combined, f"the axes must stay separate; found {combined}"
    assert "mean_response_min" in result.columns
    assert "mean_rhi_days" in result.columns
    assert "not combined" in result.attrs["warning"]


def test_matrix_rows_are_ordered_rural_to_urban():
    cells = cells_with([100, 2000], [500, 500])
    travel = pd.DataFrame(
        {"response_minutes": [12.0, 5.0], "reachable": True}, index=cells.index
    )
    classes = pd.Series(["rural", "urban_centre"], index=cells.index)
    result = mx.proximity_matrix(
        mx.proximity_by_class(cells, travel, classes),
        mx.preparedness_by_class(survey_with([("rural", 5.5, 3, 1.0)])),
    )
    assert list(result["community_class"]) == list(mx.CLASSES)


def test_the_target_comes_from_project_one_not_a_local_copy():
    """Two copies of a headline constant is how a dossier quotes two numbers."""
    assert mx.RESILIENCE_TARGET_DAYS is RESILIENCE_TARGET_DAYS
    assert mx.RESILIENCE_TARGET_DAYS == 3.0


# ── the real join ──────────────────────────────────────────────────────────

@pytest.mark.slow
@pytest.mark.skipif(not gc.OSM_PBF.exists(), reason="dati/ not present")
def test_matrix_reconciles_with_project_one_nationally():
    """The population-weighted classes must sum back to project #1's Latvia figure.

    Project #1 reports Latvia at 2.60 mean RHI days and 82.3% below the 3-day
    target on the upper bound. If the class breakdown does not reproduce those,
    the join is wrong somewhere.
    """
    import duckdb
    import pyreadstat

    from actionwise.config import DUCKDB_PATH, EB547_SAV

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        rhi = con.execute(
            "SELECT uniqid, rhi_days, rhi_band, w_national FROM rhi_respondents "
            "WHERE country_grouped = 'LV'"
        ).fetchdf()
        national = con.execute(
            "SELECT mean_days, below_target_upper FROM rhi_by_country "
            "WHERE country = 'LV'"
        ).fetchdf().iloc[0]
    finally:
        con.close()

    raw, _ = pyreadstat.read_sav(str(EB547_SAV),
                                 usecols=["uniqid", "isocntry", "d25"])
    lv = raw[raw["isocntry"] == "LV"]
    survey = rhi.merge(lv[["uniqid", "d25"]], on="uniqid", how="left")
    survey["community_class"] = survey["d25"].map(mx.D25_TO_CLASS)

    per_class = mx.preparedness_by_class(survey)
    shares = mx.survey_class_shares(survey)

    recombined_days = float(
        (per_class.set_index("community_class")["mean_rhi_days"] * shares).sum()
    )
    recombined_under = float(
        (per_class.set_index("community_class")["share_under_target_upper"] * shares).sum()
    )

    assert recombined_days == pytest.approx(national["mean_days"], abs=0.05)
    assert recombined_under == pytest.approx(national["below_target_upper"], abs=0.01)
