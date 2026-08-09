"""Traffic intensity — six sheets, six schemas, one long table.

Two workbooks (2012-2021 and 2014-2023) × three road classes. No two sheets
agree on how to spell a column, and one disagreement silently destroys the data:

  * road number is `Ceļa Nr.` on four sheets and `ceļa Nr.` on two
  * road name is `posms`, `ceļa nosaukums` or `Ceļa nosaukums`
  * chainage is `no km` or `no\\nkm` — with an embedded newline
  * the first year is `2014` or `≤2014`, a left-censored band
  * heavy-vehicle share is `2014\\nKT%` or `2015 KT%`
  * `Galvenie` carries ~100 empty `Unnamed:` columns from merged header cells

And the one that corrupts everything if missed: **`Ceļa Nr.` is null on 96 of
111 Galvenie rows**. A null means "same road as the row above", so without a
forward-fill every continuation segment loses its road and the join to OSM drops
it silently.

Road numbers are also written differently per sheet — `A-14` on Galvenie,
`P99` and `V1487` elsewhere, `V 1398` in the km markers, `A14` in OSM. Every one
goes through `normalise_road_ref`.

Pure readers and transforms.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from actionwise.data.cleaner_eb547 import Audit
from actionwise_geo.config import (
    TRAFFIC_CENSORED_LOW_AADT,
    TRAFFIC_CENSORED_TOKEN,
    TRAFFIC_JUNK_COL_PREFIX,
    TRAFFIC_KM_FROM_ALIASES,
    TRAFFIC_KM_TO_ALIASES,
    TRAFFIC_NAME_ALIASES,
    TRAFFIC_ROAD_ALIASES,
    TRAFFIC_SHEETS,
    TRAFFIC_XLSX_2012_2021,
    TRAFFIC_XLSX_2014_2023,
)

_YEAR = re.compile(r"^(?:≤)?(?P<year>(?:19|20)\d{2})(?P<heavy>\s*kt%)?$")


def normalise_road_ref(values) -> pd.Series:
    """`"A-14"`, `"V 1398"`, `"a14"` -> `"A14"`.

    The single normaliser used by the traffic sheets, the km markers and the OSM
    `ref` tag. Skipping it costs 1,322 roads' worth of joins that fail without
    raising.
    """
    return (
        pd.Series(values).astype("string")
        .str.replace(r"[\s\-]", "", regex=True)
        .str.upper()
        .replace("", pd.NA)
    )


def _normalise_header(name) -> str:
    return re.sub(r"\s+", " ", str(name).replace("\n", " ")).strip().lower()


def _find(columns: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        if alias in columns:
            return columns[alias]
    return None


def parse_aadt(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse a traffic column, keeping the censoring visible.

    `"≤100"` is a real value — the quietest roads in the country, which are
    exactly the ones with the longest response times. It is parsed as 100 and
    flagged, never dropped and never nulled.

    Returns:
        `(aadt, censored)`.
    """
    text = values.astype("string").str.strip()
    censored = text.str.startswith(TRAFFIC_CENSORED_TOKEN).fillna(False)
    numeric = pd.to_numeric(
        text.str.replace(TRAFFIC_CENSORED_TOKEN, "", regex=False), errors="coerce"
    )
    numeric = numeric.mask(censored & numeric.isna(), TRAFFIC_CENSORED_LOW_AADT)
    return numeric.astype(float), censored


def load_traffic_sheet(path, sheet: str, audit: Audit | None = None
                       ) -> tuple[pd.DataFrame, Audit]:
    """Read one sheet into long format: one row per (road, segment, year)."""
    audit = audit or Audit()
    raw = pd.read_excel(path, sheet_name=sheet)
    rows_in = len(raw)

    # 1. drop the merged-header debris
    raw = raw[[c for c in raw.columns
               if not str(c).startswith(TRAFFIC_JUNK_COL_PREFIX)]]

    lookup = {_normalise_header(c): c for c in raw.columns}
    road_col = _find(lookup, TRAFFIC_ROAD_ALIASES)
    name_col = _find(lookup, TRAFFIC_NAME_ALIASES)
    km_from = _find(lookup, TRAFFIC_KM_FROM_ALIASES)
    km_to = _find(lookup, TRAFFIC_KM_TO_ALIASES)
    if road_col is None or km_from is None or km_to is None:
        raise ValueError(
            f"{path.name} [{sheet}]: could not find the road/chainage columns among "
            f"{sorted(lookup)}"
        )

    # 2. forward-fill the road number — a null means "same road as above"
    missing_before = int(raw[road_col].isna().sum())
    road = normalise_road_ref(raw[road_col].ffill())
    audit.record(
        step=f"forward_fill_road[{path.name}:{sheet}]",
        rows_in=rows_in,
        rows_out=rows_in,
        cells_nulled=missing_before,
        reason=(
            f"{missing_before} of {rows_in} rows carried no road number; a null "
            "means 'same road as the row above', so without this every "
            "continuation segment loses its road and drops out of the join"
        ),
    )

    # 3. split year columns into AADT and heavy-vehicle share
    aadt_cols: dict[int, str] = {}
    heavy_cols: dict[int, str] = {}
    for normalised, original in lookup.items():
        match = _YEAR.match(normalised)
        if not match:
            continue
        year = int(match.group("year"))
        (heavy_cols if match.group("heavy") else aadt_cols)[year] = original

    frames = []
    for year, column in sorted(aadt_cols.items()):
        aadt, censored = parse_aadt(raw[column])
        heavy = (
            pd.to_numeric(raw[heavy_cols[year]], errors="coerce")
            if year in heavy_cols else pd.Series(np.nan, index=raw.index)
        )
        frames.append(pd.DataFrame({
            "road": road,
            "road_name": raw[name_col] if name_col else pd.NA,
            "km_from": pd.to_numeric(raw[km_from], errors="coerce"),
            "km_to": pd.to_numeric(raw[km_to], errors="coerce"),
            "year": year,
            "aadt": aadt,
            "aadt_censored": censored,
            "heavy_pct": heavy,
            "sheet": sheet,
            "source": path.name,
        }))

    long = pd.concat(frames, ignore_index=True)
    usable = long["road"].notna() & long["aadt"].notna() & (long["km_to"] > long["km_from"])
    audit.record(
        step=f"reshape_traffic[{path.name}:{sheet}]",
        rows_in=rows_in,
        rows_out=int(usable.sum()),
        cells_nulled=int((~usable).sum()),
        reason=(
            f"{rows_in} segments x {len(aadt_cols)} years -> long; dropped rows "
            "with no road, no AADT, or a non-positive segment length"
        ),
    )
    return long[usable].reset_index(drop=True), audit


def load_traffic(paths=(TRAFFIC_XLSX_2014_2023, TRAFFIC_XLSX_2012_2021),
                 audit: Audit | None = None) -> tuple[pd.DataFrame, Audit]:
    """All six sheets, harmonised and stacked.

    The two workbooks overlap on 2014-2021. The overlap is **kept**, tagged by
    `source`, so `overlap_agreement` can check the two publications against each
    other — a free consistency test that a naive de-duplication would discard.
    """
    audit = audit or Audit()
    frames = []
    for path in paths:
        for sheet in TRAFFIC_SHEETS:
            frame, audit = load_traffic_sheet(path, sheet, audit=audit)
            frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    audit.record(
        step="combine_traffic",
        rows_in=sum(len(f) for f in frames),
        rows_out=len(combined),
        cells_nulled=0,
        reason=(
            f"{combined['road'].nunique():,} roads, "
            f"{combined['year'].min()}-{combined['year'].max()}; the two workbooks "
            "overlap on 2014-2021 and the overlap is kept for cross-checking"
        ),
    )
    return combined, audit


def overlap_agreement(traffic: pd.DataFrame) -> pd.DataFrame:
    """Do the two publications agree where they overlap?

    A free external check: the same road, segment and year appears in both
    workbooks. Large disagreement would mean one of them was revised, and any
    figure built on the union would depend on which row won.
    """
    keys = ["road", "km_from", "km_to", "year"]
    pivot = (
        traffic.pivot_table(index=keys, columns="source", values="aadt",
                            aggfunc="first")
        .dropna()
    )
    if pivot.shape[1] < 2:
        return pd.DataFrame()

    left, right = pivot.columns[:2]
    diff = (pivot[left] - pivot[right]).abs()
    base = pivot[[left, right]].mean(axis=1)
    return pd.DataFrame([{
        "overlapping_rows": int(len(pivot)),
        "identical": int((diff == 0).sum()),
        "share_identical": float((diff == 0).mean()),
        "median_abs_diff": float(diff.median()),
        "median_rel_diff": float((diff / base.replace(0, np.nan)).median()),
    }])


def latest_year(traffic: pd.DataFrame) -> pd.DataFrame:
    """One AADT per road segment: the most recent observation available.

    Where the two workbooks both cover a year, the newer publication wins —
    stated here rather than left to whichever row pandas happened to keep.
    """
    ordered = traffic.sort_values(["year", "source"], ascending=[False, True])
    return ordered.drop_duplicates(subset=["road", "km_from", "km_to"], keep="first")
