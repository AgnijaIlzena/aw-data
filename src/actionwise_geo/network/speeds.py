"""Speed assignment — the dominant source of uncertainty in this project.

`maxspeed` is tagged on only 18.5% of drivable edges, so `DEFAULT_SPEEDS_KMH`
decides the travel time on four fifths of the network, and coverage is worst on
exactly the rural roads the 23-minute standard is about.

That is why nothing here picks a single number and calls the result a fact. The
emergency uplift is applied as a factor the caller supplies, and every headline
figure is reported at both ends of `EMERGENCY_SPEED_FACTORS` — the spread *is*
the uncertainty statement.

Pure transforms over columns. No I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from actionwise_geo.config import DEFAULT_SPEEDS_KMH, OSM_NONNUMERIC_MAXSPEED

MPH_TO_KMH = 1.609344

# OSM implicit-speed tokens. Only 18 edges in this extract carry them, all near
# the eastern border, but they are mapped rather than dropped so the count of
# "unparsed" stays honest.
IMPLICIT_SPEEDS_KMH = {
    "ru:urban": 60.0,     # Russian urban default
    "ru:rural": 90.0,     # Russian rural default
    "lv:urban": 50.0,
    "lv:rural": 90.0,
    "walk": 5.0,
}

# A road tagged `maxspeed=none` (derestricted) has no limit, not zero. Falling
# back to the class default is the conservative reading.
NO_LIMIT_TOKENS = {"none", "signals", "variable", "unknown"}

# Speeds outside this range are tagging errors, not roads.
MIN_PLAUSIBLE_KMH = 5.0
MAX_PLAUSIBLE_KMH = 140.0


def parse_maxspeed(values: pd.Series) -> pd.Series:
    """Parse the OSM `maxspeed` tag to km/h, leaving anything unrecognised null.

    The tag is free text. This handles the forms that actually occur:
    plain numbers (`"90"`), imperial (`"30 mph"`), and implicit country
    conventions (`"RU:urban"`). Unrecognised values become null so they fall
    through to the class default rather than silently becoming zero — a zero
    speed is an infinite travel time, which would carve fake holes in the
    coverage map.

    Returns:
        Float64 km/h, null where unparseable.
    """
    text = values.astype("string").str.strip().str.lower()

    # Plain numeric, the overwhelming majority.
    speed = pd.to_numeric(text, errors="coerce").astype("Float64")

    # Imperial, e.g. "30 mph".
    mph = text.str.extract(r"^(\d+(?:\.\d+)?)\s*mph$", expand=False)
    speed = speed.fillna(pd.to_numeric(mph, errors="coerce") * MPH_TO_KMH)

    # Implicit conventions.
    speed = speed.fillna(text.map(IMPLICIT_SPEEDS_KMH).astype("Float64"))

    # Explicit "no limit" tokens fall through to the class default.
    speed = speed.mask(text.isin(NO_LIMIT_TOKENS))

    # Tagging errors: 0 km/h, 999 km/h.
    return speed.mask((speed < MIN_PLAUSIBLE_KMH) | (speed > MAX_PLAUSIBLE_KMH))


def assign_speeds(edges: pd.DataFrame, factor: float = 1.0,
                  defaults: dict[str, float] | None = None) -> pd.DataFrame:
    """Give every edge a speed in km/h, and say where the number came from.

    Args:
        edges: needs `maxspeed` and `highway`.
        factor: emergency-vehicle uplift. Rescue vehicles lawfully exceed posted
            limits, and the size of that margin is not knowable from OSM — so it
            is a parameter, reported as a range, never a constant baked in here.
        defaults: override the per-class fallback table.

    Returns:
        `edges` plus `speed_kmh` and `speed_source` ("tagged" / "class_default" /
        "global_default"). `speed_source` exists so any figure can be reported
        with the share of its network that was inferred rather than measured.
    """
    table = defaults if defaults is not None else DEFAULT_SPEEDS_KMH
    out = edges.copy()

    tagged = parse_maxspeed(out["maxspeed"]) if "maxspeed" in out else pd.Series(
        pd.NA, index=out.index, dtype="Float64"
    )

    highway = out["highway"].astype("string").str.split(";").str[0].str.strip()
    class_default = highway.map(table).astype("Float64")

    # Anything with an unknown highway class still has to be routable — an
    # unroutable edge is a hole in the map, which is worse than a rough speed.
    global_default = float(np.median(list(table.values())))

    speed = tagged.copy()
    source = pd.Series("tagged", index=out.index, dtype="object")

    use_class = speed.isna() & class_default.notna()
    speed = speed.mask(speed.isna(), class_default)
    source = source.mask(use_class, "class_default")

    use_global = speed.isna()
    speed = speed.fillna(global_default)
    source = source.mask(use_global, "global_default")

    out["speed_kmh"] = (speed.astype(float) * factor).clip(
        lower=MIN_PLAUSIBLE_KMH, upper=MAX_PLAUSIBLE_KMH * max(factor, 1.0)
    )
    out["speed_source"] = source
    return out


def travel_time_minutes(length_m, speed_kmh) -> pd.Series:
    """Minutes to traverse an edge.

    Note `length_m` must be the pyrosm `length` COLUMN, not a GeoDataFrame's
    `.length` property. The two share a name and differ by a factor of about
    100,000: `edges.length` returns shapely's geometric length, which for an
    unprojected frame is in DEGREES, and only emits a warning. `edges["length"]`
    is pyrosm's metric length. Verified against EPSG:3059 geometry to 0.22%.
    """
    minutes = (pd.Series(length_m).astype(float) / 1000.0) / pd.Series(
        speed_kmh
    ).astype(float) * 60.0
    return minutes.replace([np.inf, -np.inf], np.nan)


def speed_provenance(edges: pd.DataFrame) -> pd.DataFrame:
    """Where the network's speeds came from, weighted by length.

    Reported beside every travel-time figure. Counting edges understates the
    issue — what matters is the share of *road* running on an assumed speed.
    """
    grouped = edges.groupby("speed_source", dropna=False)
    summary = pd.DataFrame({
        "edges": grouped.size(),
        "length_km": grouped["length"].sum() / 1000.0,
    })
    summary["share_of_length"] = summary["length_km"] / summary["length_km"].sum()
    return summary.sort_values("length_km", ascending=False).reset_index()
