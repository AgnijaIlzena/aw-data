"""Locate and read FEMA NHS files, and work out which columns are which.

FEMA publishes one ZIP per year containing "unedited raw data" plus a codebook,
and the column headers are not stable across years. So instead of hardcoding
names, this discovers them: for each of the twelve items it looks for a column
whose name contains the battery prefix (A3 / PREPB) and something identifying
the item, and reports what it matched.

If discovery fails, it fails loudly with the candidate columns listed — a silent
mismatch here would produce an ACI table full of nulls that still looked like a
result.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

from actionwise.fema.config import (
    ACTION_PREFIX,
    AWARENESS_PREFIX,
    FEMA_DIR,
    ITEMS,
    WEIGHT_CANDIDATES,
)

# Words that identify each item inside a column name or label. Deliberately
# generous — matching is confirmed by the report, not assumed.
ITEM_KEYWORDS = {
    "alerts": ("alert", "warning"),
    "make_plan": ("plan",),
    "rainy_day": ("rainy", "saving", "save"),
    "drills": ("drill", "practice", "habit"),
    "family_comms": ("communication", "comms"),
    "documents": ("document", "safeguard"),
    "neighbours": ("neighbor", "neighbour"),
    "supplies": ("supply", "supplies"),
    "community": ("community", "involve"),
    "home_safer": ("home", "safer"),
    "evacuation_routes": ("evacuat", "route"),
    "insure_property": ("insur", "property"),
}


class FemaDataMissing(FileNotFoundError):
    """Raised with instructions rather than a bare path."""


def available_years() -> dict[int, Path]:
    """Year -> file, for whatever has been downloaded so far."""
    if not FEMA_DIR.exists():
        return {}
    found: dict[int, Path] = {}
    for path in sorted(FEMA_DIR.iterdir()):
        if path.suffix.lower() not in (".zip", ".csv", ".xlsx"):
            continue
        m = re.search(r"(20\d{2})", path.name)
        if m:
            found.setdefault(int(m.group(1)), path)
    return found


def require_data() -> dict[int, Path]:
    years = available_years()
    if not years:
        raise FemaDataMissing(
            f"No FEMA NHS files in {FEMA_DIR}.\n\n"
            "FEMA blocks automated downloads, so fetch them in a browser:\n"
            "  1. open https://www.fema.gov/about/openfema/data-sets/national-household-survey\n"
            "  2. download the yearly packages (start with 2022 and 2023)\n"
            f"  3. put the .zip files in {FEMA_DIR}\n"
            "     — the year must appear in the filename, e.g. fema_nhs_2023.zip\n\n"
            "No registration or API key is needed; it is only the bot protection "
            "that blocks scripted access."
        )
    return years


def read_year(path: Path) -> pd.DataFrame:
    """Read one year's data, reaching inside a ZIP if necessary."""
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, low_memory=False, encoding_errors="replace")
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path)

    with zipfile.ZipFile(path) as z:
        members = [n for n in z.namelist() if n.lower().endswith((".csv", ".xlsx"))]
        if not members:
            raise ValueError(f"{path.name} contains no .csv or .xlsx: {z.namelist()[:10]}")
        # Prefer the largest member — the raw data, not the codebook or summary.
        member = max(members, key=lambda n: z.getinfo(n).file_size)
        with z.open(member) as fh:
            if member.lower().endswith(".csv"):
                return pd.read_csv(fh, low_memory=False, encoding_errors="replace")
            return pd.read_excel(fh)


def discover_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map each item to its awareness and action column, reporting what matched.

    Returns one row per item with the resolved column names (or None), so the
    caller can print the mapping and see at a glance whether the file really has
    the paired structure this phase depends on.
    """
    lowered = {c: c.lower() for c in df.columns}

    def find(prefix: str, keywords: tuple[str, ...]) -> str | None:
        pl = prefix.lower()
        candidates = [c for c, lc in lowered.items() if lc.startswith(pl) or f"_{pl}" in lc]
        for col in candidates:
            if any(k in lowered[col] for k in keywords):
                return col
        return None

    rows = []
    for item, keywords in ITEM_KEYWORDS.items():
        aware = find(AWARENESS_PREFIX, keywords)
        action = find(ACTION_PREFIX, keywords)
        rows.append(
            {
                "item": item,
                "label": ITEMS[item],
                "awareness_col": aware,
                "action_col": action,
                "paired": bool(aware and action),
            }
        )
    return pd.DataFrame(rows)


def find_weight(df: pd.DataFrame) -> str | None:
    for candidate in WEIGHT_CANDIDATES:
        if candidate in df.columns:
            return candidate
    for col in df.columns:
        if "weight" in col.lower() or col.lower().endswith("wt"):
            return col
    return None


def load_all(years: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Concatenate the available years, tagging each row with its survey year.

    Returns (data, discovery_report). Years are stacked rather than merged: FEMA
    NHS is a repeated cross-section, not a panel — different respondents each
    wave — so there is nobody to follow over time.
    """
    found = require_data()
    wanted = sorted(set(years) & set(found)) if years else sorted(found)
    if not wanted:
        raise FemaDataMissing(f"None of {years} available; found {sorted(found)}")

    frames, reports = [], []
    for year in wanted:
        df = read_year(found[year])
        df["survey_year"] = year
        frames.append(df)
        reports.append(discover_columns(df).assign(survey_year=year))

    return pd.concat(frames, ignore_index=True), pd.concat(reports, ignore_index=True)
