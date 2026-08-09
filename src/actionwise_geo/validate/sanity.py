"""Phase 2 gate — prove the geography is right before anything is built on it.

The counterpart of `actionwise.sanity`, which reproduces DG ECHO's published
marginals for project #1. The failure mode here is different and worse. A survey
recoding error usually shows up as an implausible percentage; a CRS or join error
produces a *map*, and maps are persuasive. Every number downstream — travel time,
coverage, compliance — inherits the geography silently.

So each check below compares against something outside this pipeline: the census,
the depot register's own regional breakdown, or an arithmetic identity that
cannot hold by accident.

One check is deliberately NOT here. Comparing the grid's density classes with
EB547's `d25` looked like a gate in the plan, and it is not one — see
`density_class_comparison`. It is reported as a diagnostic instead.

Written as a module, not notebook cells, so it also runs under pytest.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

from actionwise_geo.config import (
    CRS_WORKING,
    DEGURBA_URBAN_CENTRE_MIN,
    DEGURBA_URBAN_CLUSTER_MIN,
    DEPOTS_PER_REGION,
    POPGRID_LV_CELLS,
    POPULATION_LV_CENSUS_2021,
    RIGA_POPULATION_SHARE,
    SANITY_MAX_OFFSHORE_M,
    SANITY_MAX_UNPLACED_POPULATION_SHARE,
    SANITY_POPULATION_TOLERANCE,
    VUGD_N_DEPOTS,
)
from actionwise_geo.data.boundaries import assign_municipality


def run_gate(depots: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame,
             grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Run every geography check and return one row per check.

    Args:
        depots: from `data.depots.load_depots`.
        boundaries: from `data.boundaries.load_boundaries`.
        grid: from `data.popgrid.load_population_grid`.

    Returns:
        A frame with `check, expected, observed, pass, note`.
    """
    checks: list[dict] = []

    def add(check: str, expected, observed, ok: bool, note: str = "") -> None:
        checks.append({"check": check, "expected": expected, "observed": observed,
                       "pass": bool(ok), "note": note})

    # ── 1. Every layer is in the working CRS ───────────────────────────────
    for name, layer in (("depots", depots), ("boundaries", boundaries), ("grid", grid)):
        epsg = layer.crs.to_epsg() if layer.crs is not None else None
        add(f"CRS of {name}", f"EPSG:{CRS_WORKING}", f"EPSG:{epsg}",
            epsg == CRS_WORKING, "metres, not degrees")

    # ── 2. National population against the census ──────────────────────────
    population = int(grid["T"].sum())
    delta = abs(population - POPULATION_LV_CENSUS_2021) / POPULATION_LV_CENSUS_2021
    add("grid population vs census 2021", f"{POPULATION_LV_CENSUS_2021:,}",
        f"{population:,}", delta <= SANITY_POPULATION_TOLERANCE,
        f"{delta:.2%} apart, tolerance {SANITY_POPULATION_TOLERANCE:.0%}")

    add("grid cell count", f"{POPGRID_LV_CELLS:,}", f"{len(grid):,}",
        len(grid) == POPGRID_LV_CELLS, "Latvia only")

    # ── 3. The depot register against its own breakdown ────────────────────
    add("depot count", VUGD_N_DEPOTS, len(depots), len(depots) == VUGD_N_DEPOTS)

    observed_regions = depots["regiona_piederiba"].value_counts().to_dict()

    def _regions(counts: dict) -> str:
        """Compact so the gate table stays readable — a raw dict wrecks the width."""
        return " ".join(f"{name.split()[0][:3]}={n}" for name, n in counts.items())

    add("depots per region", _regions(DEPOTS_PER_REGION), _regions(observed_regions),
        observed_regions == DEPOTS_PER_REGION,
        "the register states its own expected answer")

    # ── 4. Every depot lands in a municipality ─────────────────────────────
    # The check that catches a CRS error the bbox test would pass: a frame can
    # sit inside Latvia's bounding box and still be systematically displaced.
    #
    # assign_municipality refuses a CRS mismatch outright. That is correct for a
    # library and wrong for a gate, whose job is to report every problem it can
    # see rather than stop at the first — so the refusal is caught and recorded.
    try:
        placed, _ = assign_municipality(depots, boundaries)
        matched = int(placed["municipality"].notna().sum())
        add("depots inside a municipality", f"{VUGD_N_DEPOTS}/{VUGD_N_DEPOTS}",
            f"{matched}/{len(depots)}", matched == len(depots),
            "a miss means the layers disagree about where Latvia is")
    except ValueError as exc:
        add("depots inside a municipality", f"{VUGD_N_DEPOTS}/{VUGD_N_DEPOTS}",
            "refused", False, str(exc).split(".")[0])

    # ── 5. Population conservation across the spatial join ─────────────────
    populated = grid[(grid["T"] > 0) & grid.geometry.notna()]
    try:
        joined, _ = assign_municipality(populated, boundaries)
    except ValueError as exc:
        add("population conserved by the join", "identity holds", "refused", False,
            str(exc).split(".")[0])
        return pd.DataFrame(checks)
    inside = joined["municipality"].notna()

    placed_pop = int(joined.loc[inside, "T"].sum())
    unplaced_pop = int(joined.loc[~inside, "T"].sum())
    mappable = int(populated["T"].sum())
    add("population conserved by the join", f"{mappable:,}",
        f"{placed_pop:,} + {unplaced_pop:,}", placed_pop + unplaced_pop == mappable,
        "an identity — it cannot hold by accident")

    share_unplaced = unplaced_pop / mappable if mappable else 0.0
    add("population outside every territory", f"< {SANITY_MAX_UNPLACED_POPULATION_SHARE:.0%}",
        f"{share_unplaced:.2%}", share_unplaced <= SANITY_MAX_UNPLACED_POPULATION_SHARE,
        f"{int((~inside).sum())} cells")

    # ── 6. Unplaced cells are coastal, not lost ────────────────────────────
    # Coastal rounding puts a centroid a few hundred metres offshore; a broken
    # CRS puts it hundreds of kilometres away. Only the distance tells them apart.
    if (~inside).any():
        offshore = joined.loc[~inside].geometry.apply(
            lambda point: boundaries.distance(point).min()
        )
        worst = float(offshore.max())
        add("unplaced cells are coastal", f"all within {SANITY_MAX_OFFSHORE_M:.0f} m",
            f"max {worst:.0f} m, median {offshore.median():.0f} m",
            worst <= SANITY_MAX_OFFSHORE_M,
            "1 km centroids landing just offshore where the coast cuts a cell")

    # ── 7. Rīga is about a third of the country ────────────────────────────
    # A spatial check: it fails when grid and boundaries are each fine but the
    # join between them is wrong.
    riga = joined.loc[joined["municipality"] == "Rīga", "T"].sum()
    riga_share = float(riga / grid["T"].sum())
    lo, hi = RIGA_POPULATION_SHARE
    add("Rīga's share of the population", f"{lo:.0%}-{hi:.0%}", f"{riga_share:.1%}",
        lo <= riga_share <= hi, f"{int(riga):,} people; CSP: 'every third resident'")

    return pd.DataFrame(checks)


def density_class_distribution(grid: gpd.GeoDataFrame) -> pd.Series:
    """Population share by per-cell density class, using Eurostat's thresholds.

    NOT strict DEGURBA. The official definition also requires contiguity
    clustering — an urban centre is a connected group of dense cells above a
    total population floor, not any cell over 1,500/km². Classifying cell by cell
    overstates urban centres here (52.8% against roughly 46% published).

    The deviation is recorded in the model card rather than corrected, because
    the classification is used only to select which legal threshold applies, and
    a per-cell rule is the conservative choice: it assigns the *stricter*
    8-minute standard to more cells than strict DEGURBA would.
    """
    populated = grid[(grid["T"] > 0) & grid["density"].notna()]

    def classify(density: float) -> str:
        if density >= DEGURBA_URBAN_CENTRE_MIN:
            return "urban_centre"
        if density >= DEGURBA_URBAN_CLUSTER_MIN:
            return "urban_cluster"
        return "rural"

    classes = populated["density"].map(classify)
    return populated.groupby(classes)["T"].sum() / populated["T"].sum()


def density_class_comparison(grid: gpd.GeoDataFrame,
                             survey_shares: dict[str, float]) -> pd.DataFrame:
    """Compare measured density classes with EB547's self-reported `d25`.

    **A diagnostic, not a gate check.** The plan listed this as a pass/fail test
    expecting the same rank order. It is not one, and the measured figures show
    why:

        grid   urban_centre 52.8%  urban_cluster 21.8%  rural 25.4%
        d25    large town   38.9%  small-mid     32.1%  rural 29.1%

    The rank orders genuinely differ — the grid puts rural above cluster, the
    survey puts small-mid town above rural — and neither is wrong, because they
    measure different things:

      * `d25` is what a respondent *says* their area is. Someone in a dense
        Rīga suburb may reasonably answer "small or middle sized town".
      * the middle category is the loosest in both, and "small or middle sized
        town" and "urban cluster" are not the same definition.
      * per-cell classification overstates urban centres, as above.

    Gating on this would either block the project on a spurious failure or force
    a tolerance so wide it asserts nothing. It is reported so the divergence is
    visible and explained — which is the honest use of a comparison between two
    constructs that were never meant to coincide.

    Args:
        grid: the population grid.
        survey_shares: EB547 `d25` shares keyed `rural`, `urban_cluster`,
            `urban_centre` — weighted by `w1`, Latvia only.

    Returns:
        One row per class with both shares and the gap in percentage points.
    """
    measured = density_class_distribution(grid)
    rows = []
    for cls in ("urban_centre", "urban_cluster", "rural"):
        grid_share = float(measured.get(cls, 0.0))
        survey_share = float(survey_shares.get(cls, float("nan")))
        rows.append({
            "class": cls,
            "grid_share": round(grid_share, 4),
            "survey_share": round(survey_share, 4),
            "gap_pp": round((grid_share - survey_share) * 100, 1),
        })
    out = pd.DataFrame(rows)
    out.attrs["warning"] = (
        "Measured density vs self-reported community type — different constructs. "
        "Reported for visibility, never gated on."
    )
    return out


def format_gate(result: pd.DataFrame) -> str:
    """Render the gate for a terminal, mirroring `actionwise.sanity.format_gate`."""
    passed = int(result["pass"].sum())
    total = len(result)
    body = result.assign(**{"pass": result["pass"].map({True: "PASS", False: "FAIL"})})
    with pd.option_context("display.width", 180, "display.max_colwidth", 50):
        table = body.to_string(index=False)
    verdict = (
        f"GATE PASSED — {passed}/{total} geography checks hold. Travel times can "
        "be built on this."
        if passed == total
        else f"GATE FAILED — {passed}/{total} hold. STOP: fix the CRS, the join or "
        "the readers before computing a single travel time."
    )
    return f"{table}\n\n{verdict}"
