"""CRS discipline — the one guard that stands between this project and a wrong map.

A degree/metre mix does not raise. It produces a map that looks fine, with
distances wrong by a factor of about 100,000, and every downstream number
plausible enough to put in a dossier. The VUGD property register is a live
example: its portal metadata says LKS-92, its values are WGS84 degrees.

So nothing here trusts a declared CRS on its own. `assert_plausibly_lv` checks
the coordinates against Latvia's real extent, which is the check that catches a
mislabelled file; `to_working_crs` is the only sanctioned way to reproject.

Pure functions over GeoDataFrames. No I/O.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from actionwise_geo.config import CRS_WORKING, LV_BBOX_3059


def to_working_crs(gdf: gpd.GeoDataFrame, name: str = "frame") -> gpd.GeoDataFrame:
    """Reproject to EPSG:3059 (LKS-92 / Latvia TM), the project's metric CRS.

    Reprojection runs one way only: into 3059 at the edge of the pipeline, never
    out of it. Everything downstream — distances, snapping, densities, travel
    times — assumes metres.

    Args:
        gdf: any GeoDataFrame with a declared CRS.
        name: used in the error message so a failure names the dataset.

    Returns:
        The same frame in EPSG:3059. Returned unchanged if already there.

    Raises:
        ValueError: if `gdf` has no CRS at all. Guessing one is how the
            mislabelled VUGD file would have entered the pipeline unnoticed.
    """
    if gdf.crs is None:
        raise ValueError(
            f"{name} has no CRS. Refusing to guess — an unlabelled frame is how a "
            "degree/metre mix enters the pipeline silently. Set the CRS the data "
            "is actually IN (check the coordinate magnitudes), then reproject."
        )
    if gdf.crs.to_epsg() == CRS_WORKING:
        return gdf
    return gdf.to_crs(epsg=CRS_WORKING)


def assert_plausibly_lv(gdf: gpd.GeoDataFrame, name: str = "frame",
                        margin_m: float = 5_000.0) -> None:
    """Check the geometry actually falls inside Latvia, in metres.

    Call this AFTER `to_working_crs`, on every frame entering the pipeline. It is
    the check a declared CRS cannot give you: a WGS84 frame mislabelled as 3059
    lands near the origin and fails here by six orders of magnitude.

    Args:
        gdf: a frame already in EPSG:3059.
        name: dataset name for the error message.
        margin_m: tolerance outside LV_BBOX_3059, for boundary geometry that
            legitimately extends slightly past the national bounding box.

    Raises:
        ValueError: if the CRS is not 3059, or the bounds fall outside Latvia.
            The message reports the observed bounds — "out of range" alone does
            not tell you whether you are looking at degrees, a different country,
            or a genuine outlier.
    """
    epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
    if epsg != CRS_WORKING:
        raise ValueError(
            f"{name} is in EPSG:{epsg}, not EPSG:{CRS_WORKING}. Call to_working_crs "
            "first — this check only means anything in metres."
        )

    if gdf.geometry.isna().all() or gdf.geometry.is_empty.all():
        raise ValueError(f"{name} has no usable geometry to check.")

    minx, miny, maxx, maxy = gdf.total_bounds
    lo_x, lo_y, hi_x, hi_y = LV_BBOX_3059

    outside = (
        minx < lo_x - margin_m or miny < lo_y - margin_m
        or maxx > hi_x + margin_m or maxy > hi_y + margin_m
    )
    if outside:
        # Naming the likely cause saves the reader a diagnostic step: degrees
        # land within a few hundred of the origin, which is unmistakable.
        hint = ""
        if abs(minx) < 1_000 and abs(miny) < 1_000:
            hint = (
                " These look like DEGREES declared as metres — the same defect as "
                "the VUGD property register. Set crs=4326, then reproject."
            )
        raise ValueError(
            f"{name} falls outside Latvia. Observed bounds "
            f"({minx:.2f}, {miny:.2f}, {maxx:.2f}, {maxy:.2f}); expected within "
            f"{LV_BBOX_3059} ± {margin_m:.0f} m.{hint}"
        )


def points_from_xy(df, x: str, y: str, crs: int = CRS_WORKING) -> gpd.GeoDataFrame:
    """Build a point GeoDataFrame from two coordinate columns.

    Args:
        df: a plain DataFrame.
        x, y: column names. Note the ordering trap — in EPSG:3059 `x` is easting
            and `y` is northing, but the VUGD property register stores longitude
            in `x` and latitude in `y`, which is the same ordering with an
            entirely different meaning. `assert_plausibly_lv` is what tells the
            two apart.
        crs: the CRS the coordinates are IN, not the one you want them in.

    Returns:
        A GeoDataFrame with a `geometry` column and `crs` set. Rows with a null
        coordinate keep a null geometry rather than being dropped — the caller
        decides, and the audit records it.
    """
    xs = pd.to_numeric(df[x], errors="coerce")
    ys = pd.to_numeric(df[y], errors="coerce")

    # Built row by row rather than with gpd.points_from_xy, which turns a NaN
    # coordinate into POINT (nan nan) — a geometry that survives every null check
    # and then silently poisons distances. None is the honest value.
    geometry = [
        Point(xi, yi) if pd.notna(xi) and pd.notna(yi) else None
        for xi, yi in zip(xs, ys)
    ]
    return gpd.GeoDataFrame(df.copy(), geometry=geometry, crs=crs)
