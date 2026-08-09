"""The 87 VUGD fire-and-rescue depots — the origin points of every travel time.

Two files exist and only one is a source:

  * `vugd_depo_adreses.csv` — 87 rows, coordinates already in EPSG:3059, with
    name, address, phone and regional command. **This is the source.**
  * `valsts_ugunsdzesibas_un_glabsanas_dienests.xlsx` — 99 rows from the property
    register. Its portal metadata claims LKS-92; the values are WGS84 degrees,
    and the extra 12 rows are administrative buildings, not operational depots.
    Loaded only by `load_depots_crosscheck`, never as a source.

Pure readers. Nothing here computes an index.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    CRS_WGS84,
    CRS_WORKING,
    DEPOTS_PER_REGION,
    VUGD_DEPOTS_CSV,
    VUGD_N_DEPOTS,
    VUGD_STATIONS_XLSX,
)
from actionwise_geo.crs import assert_plausibly_lv, points_from_xy, to_working_crs

KEEP_COLUMNS = ["id", "nosaukums", "adrese", "epasts", "regiona_piederiba",
                "telefons", "x", "y"]


def load_depots(path=VUGD_DEPOTS_CSV, audit: Audit | None = None
                ) -> tuple[gpd.GeoDataFrame, Audit]:
    """Read the depot register as points in EPSG:3059.

    Steps, each recorded in the audit:
      1. read the CSV (expect VUGD_N_DEPOTS rows)
      2. build point geometry from `x`/`y`, which are already easting/northing
      3. assert the result falls inside Latvia — see `crs.assert_plausibly_lv`
      4. check the regional breakdown against `config.DEPOTS_PER_REGION`

    Step 4 is not decoration. A truncated read, a wrong encoding or a stray
    filter all show up as a shifted regional count long before they show up as a
    wrong map, and the file states its own expected answer.

    Args:
        path: override for tests.
        audit: an existing trail to append to; a new one is created if omitted.

    Returns:
        `(gdf, audit)` where `gdf` has columns
        `id, nosaukums, adrese, regiona_piederiba, geometry` and CRS 3059.
        No rows are dropped — a depot with a bad coordinate keeps a null
        geometry and is counted in the audit, because losing a station silently
        would enlarge every coverage gap around it.
    """
    audit = audit or Audit()

    # 1. read
    raw = pd.read_csv(path)
    audit.record(
        step="read_depot_register",
        rows_in=len(raw),
        rows_out=len(raw),
        cells_nulled=0,
        reason=f"{path.name}: the authoritative depot list, coordinates in EPSG:{CRS_WORKING}",
    )
    if len(raw) != VUGD_N_DEPOTS:
        raise ValueError(
            f"{path.name} has {len(raw)} rows, expected {VUGD_N_DEPOTS}. The depot "
            "register changed — confirm which depots were added or closed before "
            "rebuilding any coverage figure on it."
        )

    # 2. geometry. x/y are easting/northing here, unlike the property register.
    gdf = points_from_xy(raw, "x", "y", crs=CRS_WORKING)
    missing_geom = int(gdf.geometry.isna().sum())
    audit.record(
        step="build_depot_points",
        rows_in=len(raw),
        rows_out=len(gdf),
        cells_nulled=missing_geom,
        reason=(
            f"{missing_geom} depot(s) without usable coordinates kept with null "
            "geometry — dropping one would silently enlarge the coverage gap "
            "around it"
        ),
    )

    # 3. the check a declared CRS cannot give you
    assert_plausibly_lv(gdf, name=path.name)
    audit.record(
        step="verify_depot_extent",
        rows_in=len(gdf),
        rows_out=len(gdf),
        cells_nulled=0,
        reason="all coordinates fall inside Latvia in metres, so the CRS label is true",
    )

    # 4. the file's own expected answer
    observed = gdf["regiona_piederiba"].value_counts().to_dict()
    if observed != DEPOTS_PER_REGION:
        raise ValueError(
            f"regional breakdown is {observed}, expected {DEPOTS_PER_REGION}. This "
            "is what a truncated read or a wrong encoding looks like before it "
            "looks like a wrong map."
        )
    audit.record(
        step="verify_depot_regions",
        rows_in=len(gdf),
        rows_out=len(gdf),
        cells_nulled=0,
        reason="regional counts match the register's own breakdown: "
               + ", ".join(f"{k.split()[0]} {v}" for k, v in DEPOTS_PER_REGION.items()),
    )
    return gdf, audit


def load_depots_crosscheck(path=VUGD_STATIONS_XLSX) -> pd.DataFrame:
    """Read the 99-row property register — for comparison only, never as a source.

    Deliberately returns a plain DataFrame, not a GeoDataFrame: making it awkward
    to map is the point. Its coordinates are degrees despite the metadata, and it
    mixes administrative buildings in with operational depots.

    Useful for one question only: does it list a depot the authoritative file
    lacks? If so, one of the two is stale and that is worth knowing before a
    coverage map is built on either.
    """
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    # Named so the units are impossible to mistake at the call site.
    rename = {"x": "longitude", "y": "latitude", "X": "longitude", "Y": "latitude"}
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


def compare_depot_sources(depots: gpd.GeoDataFrame, register: pd.DataFrame,
                          tolerance_m: float = 2_000.0) -> pd.DataFrame:
    """Match the two files by proximity and report what only one of them has.

    The register is in degrees, so it must be reprojected before any distance
    comparison — doing it the other way round is exactly the mistake this module
    exists to prevent.

    **The result is meaningless without its tolerance**, because the two files
    disagree about *where* depots are as much as about *which* exist. Measured
    on 2026-08-06:

        250 m -> 62 unmatched     1 km -> 39
        500 m -> 54               2 km -> 15        5 km -> 10

    The register stores property parcels, not garage doors, so a depot can sit
    500 m-5 km from its own coordinate. `Ķeipenes postenis` and `Cesvaines
    postenis` each appear on BOTH sides at an identical distance — one depot,
    recorded ~4 km apart, not two missing ones.

    The default of 2 km is chosen to see past that imprecision. What survives it
    is substantive, and it is why the register is never a source:
      * ~8 depots in the authoritative CSV have no counterpart at all —
        Rojas (28 km), Siguldas (30 km), Cēsu (28 km), Jaunpiebalgas (29 km)
      * the register adds buildings that are not depots — `materiālo rezervju
        noliktava`, `VUGD noliktavas` (warehouses)

    Args:
        depots: the authoritative frame, already in EPSG:3059.
        register: the property register, whose coordinates are DEGREES.
        tolerance_m: how far apart two records may sit and still be the same
            depot. Report it alongside any count derived from this function.

    Returns:
        One row per unmatched entry, with `source` ("csv_only" / "xlsx_only"),
        the name, and the distance to its nearest counterpart.
    """
    lon = "longitude" if "longitude" in register.columns else "x"
    lat = "latitude" if "latitude" in register.columns else "y"

    # Declared as 4326 because that is what the values ARE, whatever the portal
    # metadata claims, then reprojected into the working CRS like everything else.
    reg = points_from_xy(register, lon, lat, crs=CRS_WGS84)
    reg = to_working_crs(reg[reg.geometry.notna()], name="vugd_property_register")

    name_col = next(
        (c for c in ("nosaukums", "Name", "name", "description") if c in reg.columns),
        None,
    )

    rows: list[dict] = []
    depot_geoms = depots.geometry.dropna()

    for idx, point in reg.geometry.items():
        distance = depot_geoms.distance(point).min()
        if distance > tolerance_m:
            rows.append({
                "source": "xlsx_only",
                "name": reg.loc[idx, name_col] if name_col else str(idx),
                "distance_m": round(float(distance), 1),
            })

    for idx, point in depot_geoms.items():
        distance = reg.geometry.distance(point).min()
        if distance > tolerance_m:
            rows.append({
                "source": "csv_only",
                "name": depots.loc[idx, "nosaukums"],
                "distance_m": round(float(distance), 1),
            })

    return pd.DataFrame(rows, columns=["source", "name", "distance_m"])
