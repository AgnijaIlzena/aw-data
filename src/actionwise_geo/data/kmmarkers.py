"""Kilometre markers — the bridge from the traffic spreadsheets to the map.

The traffic workbooks give road number and a chainage range (`no km`, `līdz km`)
and no coordinates at all. LVC publishes no shapefile. These 20,853 markers are
what puts an AADT figure onto a stretch of road, and they are the reason this
phase is possible without a road geometry dataset.

Four traps, all measured and all silent (see `config.KM_MARKERS_*`):

  1. `KM` is a mixed-format **string**, and rounded — marker "V 1398km23.749"
     carries `KM=24`. The true chainage is in `SEARCH_STR`.
  2. 45 rows are entirely null; 19 carry the literal `"***"`.
  3. `AC_INDEX` has stray whitespace on 35 rows: `"V 1398"`, `"V  1376"`.
  4. At least one marker belongs to several roads at once —
     `"P36; P54; P55; V579; V580"` is a junction and cannot be joined 1:1.

After dropping the junk, 20,789 rows remain and `SEARCH_STR` parses for every one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    CRS_WGS84,
    KM_MARKERS_CHAINAGE_COL,
    KM_MARKERS_CHAINAGE_RE,
    KM_MARKERS_CSV,
    KM_MARKERS_MULTI_ROAD_SEP,
    KM_MARKERS_NULL_SENTINEL,
)
from actionwise_geo.crs import assert_plausibly_lv, points_from_xy, to_working_crs
from actionwise_geo.data.traffic import normalise_road_ref


def load_km_markers(path=KM_MARKERS_CSV, audit: Audit | None = None):
    """Read the markers as points in EPSG:3059 with a parsed decimal chainage.

    Returns:
        `(gdf, audit)` with `road`, `chainage_km`, `multi_road`, `geometry`.

        Junction markers listing several roads are **expanded to one row per
        road** rather than dropped: a marker at a P-road/V-road junction is a
        valid chainage point on both, and dropping it would leave a gap in the
        chainage series exactly where two roads meet.
    """
    audit = audit or Audit()
    raw = pd.read_csv(path)
    rows_in = len(raw)

    junk = raw[["AC_INDEX", "KM", KM_MARKERS_CHAINAGE_COL]].isna().all(axis=1)
    sentinel = raw["KM"].astype("string").str.strip() == KM_MARKERS_NULL_SENTINEL
    usable = raw[~junk & ~sentinel.fillna(False)].copy()
    audit.record(
        step="drop_km_marker_junk",
        rows_in=rows_in,
        rows_out=len(usable),
        cells_nulled=int(junk.sum() + sentinel.fillna(False).sum()),
        reason=(
            f"{int(junk.sum())} all-null row(s) and "
            f"{int(sentinel.fillna(False).sum())} carrying the literal "
            f"{KM_MARKERS_NULL_SENTINEL!r} removed"
        ),
    )

    # Chainage from SEARCH_STR — KM is rounded and cannot carry it.
    parsed = usable[KM_MARKERS_CHAINAGE_COL].astype("string").str.extract(
        KM_MARKERS_CHAINAGE_RE
    )
    usable["chainage_km"] = pd.to_numeric(parsed["chainage"], errors="coerce")
    unparsed = int(usable["chainage_km"].isna().sum())
    audit.record(
        step="parse_km_marker_chainage",
        rows_in=len(usable),
        rows_out=len(usable),
        cells_nulled=unparsed,
        reason=(
            f"decimal chainage read from {KM_MARKERS_CHAINAGE_COL}; the KM column "
            "is a rounded string and would land the join on the wrong kilometre"
        ),
    )

    # Junction markers -> one row per road.
    usable["multi_road"] = (
        usable["AC_INDEX"].astype("string")
        .str.contains(KM_MARKERS_MULTI_ROAD_SEP, na=False)
    )
    expanded = usable.assign(
        road=usable["AC_INDEX"].astype("string").str.split(KM_MARKERS_MULTI_ROAD_SEP)
    ).explode("road")
    expanded["road"] = normalise_road_ref(expanded["road"])
    audit.record(
        step="expand_junction_markers",
        rows_in=len(usable),
        rows_out=len(expanded),
        cells_nulled=int(usable["multi_road"].sum()),
        reason=(
            f"{int(usable['multi_road'].sum())} junction marker(s) listing several "
            "roads expanded to one row each — a junction is a valid chainage point "
            "on every road meeting there, and dropping it leaves a gap exactly "
            "where roads join"
        ),
    )

    gdf = points_from_xy(expanded, "Longitude", "Latitude", crs=CRS_WGS84)
    gdf = to_working_crs(gdf, name=path.name)
    assert_plausibly_lv(gdf, name=path.name)

    keep = gdf["road"].notna() & gdf["chainage_km"].notna() & gdf.geometry.notna()
    out = gdf.loc[keep, ["road", "chainage_km", "multi_road", "geometry"]]
    audit.record(
        step="load_km_markers",
        rows_in=len(gdf),
        rows_out=len(out),
        cells_nulled=int((~keep).sum()),
        reason=(
            f"{out['road'].nunique():,} roads carry usable markers, reprojected to "
            "EPSG:3059 so chainage matching happens in metres"
        ),
    )
    return out, audit
