"""The CRS guard, tested against the exact failure it exists to catch.

A degree/metre mix never raises on its own. It yields a map that looks right and
distances wrong by ~100,000×. The VUGD property register is a real instance:
metadata says LKS-92, values are degrees. Every test here is a rehearsal of that
mistake.
"""
import pytest

gpd = pytest.importorskip("geopandas", reason="geo extra not installed")
import pandas as pd
from shapely.geometry import Point

from actionwise_geo import config as gc
from actionwise_geo.crs import assert_plausibly_lv, points_from_xy, to_working_crs

# Rīga, in each CRS. Same place, three coordinate systems.
RIGA_3059 = (508_000.0, 312_000.0)
RIGA_4326 = (24.105, 56.949)


def frame_3059(coords=(RIGA_3059,)) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [f"p{i}" for i in range(len(coords))]},
        geometry=[Point(*c) for c in coords],
        crs=gc.CRS_WORKING,
    )


def frame_4326(coords=(RIGA_4326,)) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [f"p{i}" for i in range(len(coords))]},
        geometry=[Point(*c) for c in coords],
        crs=gc.CRS_WGS84,
    )


# ── to_working_crs ─────────────────────────────────────────────────────────

def test_reprojects_degrees_to_metres():
    out = to_working_crs(frame_4326())
    assert out.crs.to_epsg() == gc.CRS_WORKING
    x, y = out.geometry.iloc[0].x, out.geometry.iloc[0].y
    assert abs(x - RIGA_3059[0]) < 5_000 and abs(y - RIGA_3059[1]) < 5_000


def test_already_in_working_crs_is_left_alone():
    src = frame_3059()
    out = to_working_crs(src)
    assert out.crs.to_epsg() == gc.CRS_WORKING
    assert out.geometry.iloc[0].equals_exact(src.geometry.iloc[0], 1e-9)


def test_missing_crs_raises_rather_than_guessing():
    """Guessing is how a mislabelled file enters the pipeline unnoticed."""
    naked = gpd.GeoDataFrame({"name": ["x"]}, geometry=[Point(*RIGA_3059)], crs=None)
    with pytest.raises(ValueError, match="(?i)crs"):
        to_working_crs(naked, name="naked")


# ── assert_plausibly_lv ────────────────────────────────────────────────────

def test_accepts_real_latvian_coordinates():
    assert_plausibly_lv(frame_3059(), name="riga")


def test_rejects_degrees_mislabelled_as_metres():
    """THE test. This is the VUGD property register, exactly."""
    mislabelled = gpd.GeoDataFrame(
        {"name": ["depot"]},
        geometry=[Point(27.67, 57.18)],   # degrees, declared as EPSG:3059
        crs=gc.CRS_WORKING,
    )
    with pytest.raises(ValueError) as exc:
        assert_plausibly_lv(mislabelled, name="vugd_xlsx")
    assert "vugd_xlsx" in str(exc.value), "the message must name the dataset"
    assert "27" in str(exc.value) or "57" in str(exc.value), (
        "the message must report the observed bounds — 'out of range' alone does "
        "not say whether you are looking at degrees, another country, or an outlier"
    )


def test_rejects_a_frame_still_in_degrees():
    with pytest.raises(ValueError):
        assert_plausibly_lv(frame_4326(), name="unprojected")


def test_rejects_coordinates_in_a_neighbouring_country():
    """Helsinki in EPSG:3059 — metric, plausible-looking, and not Latvia."""
    helsinki = gpd.GeoDataFrame(
        {"name": ["hki"]}, geometry=[Point(553_000, 730_000)], crs=gc.CRS_WORKING
    )
    with pytest.raises(ValueError):
        assert_plausibly_lv(helsinki, name="helsinki")


def test_margin_allows_boundary_geometry_to_overhang_slightly():
    minx, miny, _, _ = gc.LV_BBOX_3059
    edge = gpd.GeoDataFrame(
        {"name": ["edge"]}, geometry=[Point(minx - 1_000, miny + 1_000)],
        crs=gc.CRS_WORKING,
    )
    assert_plausibly_lv(edge, name="edge", margin_m=5_000)
    with pytest.raises(ValueError):
        assert_plausibly_lv(edge, name="edge", margin_m=0)


# ── points_from_xy ─────────────────────────────────────────────────────────

def test_builds_points_and_sets_the_crs():
    df = pd.DataFrame({"x": [RIGA_3059[0]], "y": [RIGA_3059[1]], "n": ["a"]})
    out = points_from_xy(df, "x", "y", crs=gc.CRS_WORKING)
    assert out.crs.to_epsg() == gc.CRS_WORKING
    assert out.geometry.iloc[0].x == pytest.approx(RIGA_3059[0])
    assert list(out["n"]) == ["a"]


def test_null_coordinates_keep_a_null_geometry_instead_of_being_dropped():
    """Losing a depot silently would enlarge the coverage gap around it."""
    df = pd.DataFrame({"x": [RIGA_3059[0], None], "y": [RIGA_3059[1], None],
                       "n": ["good", "bad"]})
    out = points_from_xy(df, "x", "y", crs=gc.CRS_WORKING)
    assert len(out) == 2, "rows must survive; the caller and the audit decide"
    assert out.geometry.iloc[1] is None or out.geometry.isna().iloc[1]
