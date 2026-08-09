"""Administrative territories — the reporting geography.

42 features in EPSG:3059: 7 valstspilsētas and 35 novadi. Two facts that must not
be assumed away:

  * **42 is not all of Latvia.** The country has 36 novadi; Varakļānu nov. is
    absent from this file. NMPD reports it, which is how the gap surfaces in
    Phase 6 rather than in a conclusion.
  * The 2021 reform sits inside the traffic series (2012-2023), so anything
    aggregated across 1 July 2021 needs `load_crosswalk`.

`atrib` is the 7-digit ATVK-family code (`0001000` = Rīga). It is the stable join
key; `nosaukums` is the one that matches NMPD, and matches it imperfectly.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    BOUNDARIES_CROSSWALK_CSV,
    BOUNDARIES_GPKG,
    BOUNDARIES_LAYER,
    BOUNDARIES_N_CITIES,
    BOUNDARIES_N_FEATURES,
)
from actionwise_geo.crs import assert_plausibly_lv, to_working_crs

# Valstspilsētas hold codes 0001000-0007000; novadi start at 0020000. The gap is
# wide enough that a single threshold is unambiguous.
CITY_CODE_MAX = 10_000


def load_boundaries(path=BOUNDARIES_GPKG, layer: str = BOUNDARIES_LAYER,
                    audit: Audit | None = None) -> tuple[gpd.GeoDataFrame, Audit]:
    """Read the 2026 administrative territories in EPSG:3059.

    Adds one derived column beyond the file's own four:

      * `is_city` — True for the 7 valstspilsētas. Derived from `atrib`
        (city codes are 0001000-0007000) rather than from the name, because the
        name test (`endswith(" nov.")`) is a string convention and the code is
        the actual classification. The two should agree; that they do is asserted.

    `is_city` is load-bearing downstream: NMPD's 12-minute target applies to the
    four largest cities, its 15-minute target to the rest, and its published
    figures collapse all 7 into one row.

    Returns:
        `(gdf, audit)` with `fid, nosaukums, atrib, is_city, geometry`.

    Raises:
        ValueError: if the layer is missing, or the feature count differs from
            `BOUNDARIES_N_FEATURES` or the city count from `BOUNDARIES_N_CITIES`.
            All are stated in config, and a mismatch means the file changed —
            which is a decision for a person, not something to absorb silently.
    """
    audit = audit or Audit()

    try:
        gdf = gpd.read_file(path, layer=layer)
    except Exception as exc:  # pyogrio raises its own error type
        raise ValueError(
            f"could not read layer {layer!r} from {path.name}: {exc}"
        ) from exc

    audit.record(
        step="read_boundaries",
        rows_in=len(gdf),
        rows_out=len(gdf),
        cells_nulled=0,
        reason=f"{path.name} layer {layer!r}",
    )

    if len(gdf) != BOUNDARIES_N_FEATURES:
        raise ValueError(
            f"{path.name} has {len(gdf)} features, expected {BOUNDARIES_N_FEATURES} "
            f"({BOUNDARIES_N_CITIES} valstspilsētas + 35 novadi). The territorial "
            "geography changed — reconcile it against the NMPD join before use."
        )

    gdf = to_working_crs(gdf, name=path.name)
    assert_plausibly_lv(gdf, name=path.name)

    # Classification from the code, cross-checked against the naming convention.
    by_code = pd.to_numeric(gdf["atrib"], errors="coerce") < CITY_CODE_MAX
    by_name = ~gdf["nosaukums"].str.endswith(" nov.")
    if not by_code.equals(by_name):
        disagree = gdf.loc[by_code != by_name, "nosaukums"].tolist()
        raise ValueError(
            f"the ATVK code and the name convention disagree on {disagree}. The "
            "code is authoritative, but a disagreement means the file changed."
        )

    gdf["is_city"] = by_code
    if int(gdf["is_city"].sum()) != BOUNDARIES_N_CITIES:
        raise ValueError(
            f"found {int(gdf['is_city'].sum())} valstspilsētas, expected "
            f"{BOUNDARIES_N_CITIES}"
        )

    audit.record(
        step="classify_territories",
        rows_in=len(gdf),
        rows_out=len(gdf),
        cells_nulled=0,
        reason=(
            f"{BOUNDARIES_N_CITIES} valstspilsētas / "
            f"{len(gdf) - BOUNDARIES_N_CITIES} novadi, by ATVK code; note Latvia "
            "has 36 novadi — Varakļānu nov. is absent from this file"
        ),
    )
    return gdf, audit


def load_crosswalk(path=BOUNDARIES_CROSSWALK_CSV) -> pd.DataFrame:
    """The 120-row old→new territory mapping from the 2021 reform.

    Needed by Phase 5: the traffic workbooks span 2012-2023, and territory names
    and codes changed on 1 July 2021. One new territory can absorb several old
    ones (Aizkraukles novads took in Jaunjelgavas novads among others), so the
    mapping is many-to-one and a naive name join across the boundary mismatches
    without ever erroring.
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def assign_municipality(points: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame,
                        audit: Audit | None = None
                        ) -> tuple[gpd.GeoDataFrame, Audit]:
    """Spatial-join points onto territories, keeping the unmatched visible.

    Used for depots in Phase 2 and for grid cells in Phase 4.

    Every point must land somewhere, and points that do not are the single most
    useful diagnostic in the project: an unmatched depot means the CRS is wrong,
    while an unmatched grid cell usually means a coastal cell whose centroid
    falls just offshore. Those are different problems with the same symptom, so
    the audit records the count and the caller decides — nothing is dropped here.

    Returns:
        `(gdf, audit)` — `points` plus `municipality`, `municipality_atrib` and
        `is_city`, null where no territory contains the point.

        The territory columns are renamed on the way out rather than carried
        through as `nosaukums`/`atrib`. Both sides of this join legitimately use
        `nosaukums` — it is the depot's name on one side and the municipality's
        on the other — so keeping the source names produces a silent suffix
        collision on real data, and an output column whose meaning depends on
        what was joined.
    """
    audit = audit or Audit()

    # geopandas only *warns* on a CRS mismatch and then joins anyway, which
    # produces an empty or nonsensical result that looks like "no points matched".
    # In a project whose central risk is a degree/metre mix, that has to be an error.
    left, right = points.crs, boundaries.crs
    if left is None or right is None or left.to_epsg() != right.to_epsg():
        raise ValueError(
            f"CRS mismatch: points are EPSG:{left.to_epsg() if left else None}, "
            f"territories are EPSG:{right.to_epsg() if right else None}. geopandas "
            "would warn and join anyway, giving zero matches that look like a data "
            "problem rather than a CRS one. Call to_working_crs on both first."
        )

    rename = {"nosaukums": "municipality", "atrib": "municipality_atrib"}
    carried = [c for c in ("nosaukums", "atrib", "is_city") if c in boundaries.columns]
    territories = boundaries[carried + ["geometry"]].rename(columns=rename)

    joined = gpd.sjoin(
        points,
        territories,
        how="left",            # left, so unmatched points survive as nulls
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")

    # A point on a shared border can match two polygons and duplicate the row.
    # Keep the first match rather than letting the row count drift.
    if len(joined) > len(points):
        joined = joined[~joined.index.duplicated(keep="first")]

    unmatched = int(joined["municipality"].isna().sum()) if "municipality" in joined else 0
    audit.record(
        step="assign_municipality",
        rows_in=len(points),
        rows_out=len(joined),
        cells_nulled=unmatched,
        reason=(
            f"{unmatched} of {len(points)} point(s) fell outside every territory, "
            "kept with a null municipality — for depots this means the CRS is "
            "wrong; for grid cells it is usually a centroid just offshore"
        ),
    )
    return joined, audit
