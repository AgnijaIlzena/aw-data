"""Eurostat census grid — where people actually live, at 1 km.

This is what turns "area covered" into "people covered". Area is a map; people
is a finding.

The file is EU-wide (4,595,932 rows) inside a 566 MB archive holding five
renderings of the same data. Only the 76 MB parquet is touched, and it is read
**from inside the zip** — `zipfile` handles are seekable, so nothing is extracted
and the 1.3 GB GeoPackage is never materialised.

Four traps, all measured on 2026-08-06 and all silent if missed. They are
documented at length in `config.py`; in short:

  1. `-9999` is a confidentiality sentinel on the age bands. Summed naively,
     Y_GE65 totals **-211,308,180**.
  2. Age suppression is **not random** — it hits sparse cells, which are exactly
     the remote ones this project is about.
  3. `LAND_SURFACE` is a fraction, not an area. Density needs it as a divisor.
  4. `POPULATED` disagrees with `T > 0` on 2,031 cells. Filter on `T`.

Pure reader plus geometry decoding. No index logic.
"""
from __future__ import annotations

import zipfile

import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    CRS_ETRS89_LAEA,
    POPGRID_AGE_BANDS,
    POPGRID_CELL_M,
    POPGRID_COLUMNS,
    POPGRID_GRD_ID_RE,
    POPGRID_MEMBER,
    POPGRID_SUPPRESSED,
    POPGRID_UNALLOCATED_SUFFIX,
    POPGRID_ZIP,
)
from actionwise_geo.crs import assert_plausibly_lv, points_from_xy, to_working_crs


def decode_grd_id(grd_id: pd.Series) -> pd.DataFrame:
    """Turn `GRD_ID` strings into EPSG:3035 coordinates.

    The grid ships no coordinate columns — this string *is* the geometry:

        "CRS3035RES1000mN3731000E5018000"  ->  north=3_731_000  east=5_018_000

    Those name the cell's **lower-left corner**, so the centroid is corner plus
    half a cell. Using the corner as the centroid shifts every cell 500 m
    south-west — far too small to look wrong on a map of Latvia, and easily
    enough to move a cell across an 8-minute isochrone boundary.

    Returns:
        A frame with `east`, `north` (corner), `resolution_m`, and `crs_epsg`,
        indexed like the input. Unparseable IDs give nulls rather than raising;
        the caller counts them into the audit.
    """
    parts = grd_id.astype("string").str.extract(POPGRID_GRD_ID_RE)
    return pd.DataFrame(
        {
            "east": pd.to_numeric(parts["east"], errors="coerce"),
            "north": pd.to_numeric(parts["north"], errors="coerce"),
            "resolution_m": pd.to_numeric(parts["res"], errors="coerce"),
            "crs_epsg": pd.to_numeric(parts["crs"], errors="coerce"),
        },
        index=grd_id.index,
    )


def load_population_grid(path=POPGRID_ZIP, member: str = POPGRID_MEMBER,
                         country: str = "LV", audit: Audit | None = None
                         ) -> tuple[gpd.GeoDataFrame, Audit]:
    """Read one country's cells as centroid points in EPSG:3059.

    Steps, each recorded in the audit:
      1. open the parquet inside the zip and read row group by row group,
         filtering to `country` as you go — the full frame is EU-wide and there
         is no reason to hold it
      2. decode `GRD_ID` to corner coordinates, then offset to centroids
      3. replace `POPGRID_SUPPRESSED` (-9999) with null in the age bands **only**
         — never in `T`, which is never suppressed
      4. derive `land_km2` from `LAND_SURFACE` and `density` = T / land_km2
      5. reproject 3035 → 3059

    Step 3 is the one that matters. Left as -9999 the age bands are catastrophic;
    replaced with 0 they are quietly wrong, understating the elderly everywhere
    the data is thin. Null is the only honest value, and it forces every
    downstream figure to state its coverage.

    Returns:
        `(gdf, audit)` with `grd_id, T, Y_LT15, Y_1564, Y_GE65, land_km2,
        density, age_suppressed, geometry`, CRS 3059, one row per cell.

        `age_suppressed` is kept as an explicit boolean rather than left implicit
        in the nulls, so Phase 4 can report "this figure covers X% of the
        population" without recomputing what was missing.
    """
    audit = audit or Audit()

    # 1. read only what is needed, filtering per row group
    with zipfile.ZipFile(path) as archive:
        with archive.open(member) as handle:
            parquet = pq.ParquetFile(handle)
            rows_eu = parquet.metadata.num_rows
            chunks = []
            for group in range(parquet.metadata.num_row_groups):
                frame = parquet.read_row_group(
                    group, columns=list(POPGRID_COLUMNS)
                ).to_pandas()
                chunks.append(frame[frame["CNTR_ID"] == country])
    raw = pd.concat(chunks, ignore_index=True)

    audit.record(
        step="read_population_grid",
        rows_in=rows_eu,
        rows_out=len(raw),
        cells_nulled=0,
        reason=(
            f"{member} read in place from the archive, filtered to CNTR_ID="
            f"{country!r}; the 1.3 GB GeoPackage in the same zip is never touched"
        ),
    )

    # 2. geometry from the ID, corner -> centroid
    corners = decode_grd_id(raw["GRD_ID"])
    half = POPGRID_CELL_M / 2
    grid = pd.DataFrame({
        "grd_id": raw["GRD_ID"],
        "east": corners["east"] + half,
        "north": corners["north"] + half,
    })
    grid["T"] = raw["T"]

    # One row is not a cell: "<CC>_unallocated" holds people the census could not
    # place in any square. Flagged rather than dropped — it belongs in the
    # national total and must be excluded from the mappable one.
    grid["unallocated"] = raw["GRD_ID"].astype("string").str.endswith(
        POPGRID_UNALLOCATED_SUFFIX
    ).fillna(False)
    # Anything unparseable that is NOT the unallocated row is a genuine defect.
    stray = int((corners["north"].isna() & ~grid["unallocated"]).sum())

    audit.record(
        step="decode_grid_geometry",
        rows_in=len(raw),
        rows_out=len(grid),
        cells_nulled=stray,
        reason=(
            f"GRD_ID decoded to EPSG:{CRS_ETRS89_LAEA} corners, offset by {half:.0f} m "
            "to cell centres; skipping that offset shifts every cell south-west by "
            f"{half:.0f} m, enough to cross an isochrone boundary"
        ),
    )

    unallocated_pop = int(grid.loc[grid["unallocated"], "T"].sum())
    audit.record(
        step="flag_unallocated_population",
        rows_in=len(grid),
        rows_out=len(grid),
        cells_nulled=int(grid["unallocated"].sum()),
        reason=(
            f"{unallocated_pop:,} people carry no grid square and keep a null "
            "geometry. They belong in the NATIONAL denominator (which reconciles to "
            "the census) and must be excluded from the MAPPABLE one (the only "
            "correct base for 'share within X minutes')"
        ),
    )

    # 3. the sentinel. Null, never zero.
    suppressed = pd.Series(False, index=raw.index)
    nulled = 0
    for band in POPGRID_AGE_BANDS:
        flag = raw[band] == POPGRID_SUPPRESSED
        suppressed |= flag
        nulled += int(flag.sum())
        grid[band] = raw[band].where(~flag).astype("Float64")
    grid["age_suppressed"] = suppressed

    audit.record(
        step="null_suppressed_age_bands",
        rows_in=len(grid),
        rows_out=len(grid),
        cells_nulled=nulled,
        reason=(
            f"{POPGRID_SUPPRESSED} is a disclosure-control sentinel on "
            f"{', '.join(POPGRID_AGE_BANDS)} (never on T); left in place Y_GE65 sums "
            "to -211,308,180. Suppression concentrates in sparse cells, so zeroing "
            "would understate the elderly exactly where travel times are longest"
        ),
    )

    # 4. LAND_SURFACE is a fraction of the cell, not an area
    cell_km2 = (POPGRID_CELL_M / 1000) ** 2
    grid["land_km2"] = raw["LAND_SURFACE"] * cell_km2
    grid["density"] = (grid["T"] / grid["land_km2"]).where(grid["land_km2"] > 0)

    audit.record(
        step="derive_density",
        rows_in=len(grid),
        rows_out=len(grid),
        cells_nulled=int(grid["density"].isna().sum()),
        reason=(
            "density = T / land area, where land area comes from LAND_SURFACE as a "
            "FRACTION (0-1) of the cell; using the whole cell understates density "
            "on every coastal, riverside and lakeside cell"
        ),
    )

    # 5. into the working CRS
    gdf = points_from_xy(grid, "east", "north", crs=CRS_ETRS89_LAEA)
    gdf = to_working_crs(gdf, name="eurostat_census_grid")
    assert_plausibly_lv(gdf, name="eurostat_census_grid", margin_m=20_000)

    audit.record(
        step="reproject_grid",
        rows_in=len(gdf),
        rows_out=len(gdf),
        cells_nulled=0,
        reason=f"EPSG:{CRS_ETRS89_LAEA} -> EPSG:3059, verified inside Latvia",
    )

    # The EPSG:3035 lattice indices are kept, not dropped. Reprojecting to 3059
    # rotates the grid slightly, so 3059 coordinates no longer sit on a clean
    # 1 km lattice and neighbouring cells cannot be identified by arithmetic.
    # In 3035 they can — which is what Phase 4 needs to grow settlements by
    # contiguity instead of guessing a radius around a town centre.
    gdf["grid_i"] = ((gdf["east"] - half) / POPGRID_CELL_M).round().astype("Int64")
    gdf["grid_j"] = ((gdf["north"] - half) / POPGRID_CELL_M).round().astype("Int64")

    return gdf.drop(columns=["east", "north"]), audit


def population_coverage(grid: gpd.GeoDataFrame) -> dict:
    """Summarise what the age bands actually cover — for the model card.

    The headline in Phase 4 is a share of over-65s, and its honesty depends on
    this: 65% of populated cells have no age detail, but they hold only 4.9% of
    people. Both numbers belong next to the finding, because the first sounds
    disqualifying and the second shows it is not — while the bias direction
    (suppression concentrated in sparse, remote cells) still needs stating.

    Returns:
        `{cells, populated_cells, population, age_suppressed_cells,
          population_with_age_detail, age_coverage_share}`
    """
    populated = grid[grid["T"] > 0]
    with_age = populated[~populated["age_suppressed"]]
    population = int(populated["T"].sum())
    covered = int(with_age["T"].sum())

    unallocated = (
        int(populated.loc[populated["unallocated"], "T"].sum())
        if "unallocated" in populated.columns
        else 0
    )

    return {
        "cells": int(len(grid)),
        "populated_cells": int(len(populated)),
        # The national total reconciles to the census; the mappable total is the
        # only correct denominator for a "share within X minutes" figure. Both are
        # returned so a caller cannot pick the wrong one without noticing.
        "population": population,
        "unallocated_population": unallocated,
        "mappable_population": population - unallocated,
        "age_suppressed_cells": int(populated["age_suppressed"].sum()),
        "population_with_age_detail": covered,
        "age_coverage_share": covered / population if population else float("nan"),
    }
