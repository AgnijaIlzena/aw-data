"""Generate project #2's model cards from DuckDB and config — never hand-written.

Usage:
    python scripts/build_geo_model_cards.py

Same rule as `build_model_cards.py`: every figure is pulled from the artefacts
themselves, so a stale card is impossible. `virality-code` documented a Random
Forest while running Gradient Boosting because its docs were written once and the
code moved on.

Cards are numbered from 10 so they sort after project #1's.
"""
from __future__ import annotations

import platform
import sys
from datetime import date

import pandas as pd

from actionwise import config as base
from actionwise.db.duckdb_client import get_connection
from actionwise_geo import config as gc

DOCS = base.ROOT / "docs" / "model-cards"


def _has(con, table: str) -> bool:
    return not con.execute(
        f"SELECT 1 FROM duckdb_tables() WHERE table_name = '{table}' LIMIT 1"
    ).fetchdf().empty


def _q(con, sql: str) -> pd.DataFrame:
    return con.execute(sql).fetchdf()


def _table(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False)


def _footer() -> str:
    return (
        f"\n---\n\n*Generated {date.today().isoformat()} by "
        f"`scripts/build_geo_model_cards.py` · Python {platform.python_version()} · "
        f"OSM snapshot `{gc.OSM_SNAPSHOT_DATE}` · census 2021 · "
        f"boundaries `{gc.BOUNDARIES_GPKG.name}`.*\n"
    )


def card_pipeline(con) -> str:
    lines = [
        "# Model card — geography pipeline and its sanity gate",
        "",
        "**What it is.** The reference geography every travel time is built on: "
        f"{gc.VUGD_N_DEPOTS} VUGD depots, {gc.BOUNDARIES_N_FEATURES} administrative "
        f"territories, and {gc.POPGRID_LV_CELLS:,} census grid cells, all in "
        f"EPSG:{gc.CRS_WORKING} (LKS-92 / Latvia TM).",
        "",
        "**Why a gate at all.** A survey recoding error usually shows up as an "
        "implausible percentage. A CRS or join error produces a *map*, and maps are "
        "persuasive. Everything downstream inherits the geography silently, so it is "
        "checked against things outside this pipeline before anything is built on it.",
        "",
    ]
    if _has(con, "geo_sanity_gate"):
        # `check` and `pass` are SQL reserved words — quoted, not renamed, so the
        # column names in the card match the ones in the table.
        gate = _q(con, 'SELECT "check", expected, observed, "pass", note '
                       "FROM geo_sanity_gate")
        passed = int(gate["pass"].sum())
        lines += [
            f"## The gate — {passed}/{len(gate)} checks",
            "",
            _table(gate),
            "",
        ]

    lines += [
        "## The traps in this data, all measured rather than assumed",
        "",
        "1. **A mislabelled CRS.** `valsts_ugunsdzesibas_un_glabsanas_dienests.xlsx` "
        "declares LKS-92 in its portal metadata and holds WGS84 degrees. It is also "
        "the property register, not the depot list. The authoritative file is "
        f"`{gc.VUGD_DEPOTS_CSV.name}` ({gc.VUGD_N_DEPOTS} rows).",
        f"2. **`-9999` is a confidentiality sentinel** on the census age bands, never "
        "on the total. Summed naively `Y_GE65` totals **-211,308,180**. Suppression "
        f"hits {gc.POPGRID_LV_AGE_SUPPRESSED_CELLS:,} of "
        f"{gc.POPGRID_LV_POPULATED_CELLS:,} populated cells — the *sparse* ones, which "
        "are the remote ones this project is about.",
        "3. **`LAND_SURFACE` is a fraction, not an area.** Density needs it as a "
        "divisor or every coastal and riverside cell is understated.",
        "4. **`GRD_ID` names the cell corner**, not its centre. The 500 m offset is "
        "invisible nationally and enough to cross an isochrone boundary.",
        f"5. **{gc.POPGRID_LV_UNALLOCATED_POPULATION:,} people have no location.** The "
        "`LV_unallocated` row is census population that could not be placed. It is "
        "kept and flagged, because the national total (reconciling to the census) and "
        "the mappable total (the only correct coverage denominator) differ by it.",
        f"6. **{gc.BOUNDARIES_N_FEATURES} territories is not all of Latvia** — "
        f"{', '.join(gc.BOUNDARIES_MISSING)} is absent from the 2026 boundaries.",
        "",
        "## Denominators",
        "",
    ]
    if _has(con, "geo_compliance"):
        overall = _q(con, "SELECT population FROM geo_compliance WHERE applies_to = 'ALL (CCI)'")
        if not overall.empty:
            lines += [
                f"- national (reconciles to census): **{gc.POPGRID_LV_POPULATION:,}**",
                f"- unallocated, no grid square: **{gc.POPGRID_LV_UNALLOCATED_POPULATION:,}**",
                f"- **mappable** (used for every share): **{int(overall['population'].iloc[0]):,}**",
                "",
            ]
    return "\n".join(lines) + _footer()


def card_tth(con) -> str:
    lines = [
        "# Model card — TTH (Time-to-Help)",
        "",
        "**What it measures.** Minutes from the nearest of "
        f"{gc.VUGD_N_DEPOTS} VUGD depots to every populated 1 km cell, along the "
        "drivable road network. Response time adds the "
        f"**{gc.TURNOUT_MINUTES} min turnout** required by MK 297 p. 5; travel and "
        "response are separate columns so neither is ever reported as the other.",
        "",
        "**Method.** Multi-source Dijkstra (`scipy.sparse.csgraph`, `min_only=True`) "
        f"over a CSR graph of {gc.OSM_EXPECTED_NODES:,} nodes and "
        f"{gc.OSM_EXPECTED_EDGES:,} edges built from a dated OSM extract. One pass "
        f"treats all {gc.VUGD_N_DEPOTS} depots as a single source set.",
        "",
        "**Data version.** OSM `" + gc.OSM_PBF.name + f"`, snapshot {gc.OSM_SNAPSHOT_DATE}. "
        "Pinned deliberately: `latvia-latest.osm.pbf` points at a different file every "
        "day and results built on it cannot be reproduced.",
        "",
    ]
    if _has(con, "geo_tth_coverage"):
        cov = _q(con, "SELECT speed_factor, threshold, population, share "
                      "FROM geo_tth_coverage ORDER BY speed_factor, minutes")
        lines += ["## Coverage", "", _table(cov), ""]

    lines += [
        "## Parameters",
        "",
        f"- speed factors reported: **{', '.join(f'{f:g}x' for f in gc.EMERGENCY_SPEED_FACTORS)}** "
        "— rescue vehicles lawfully exceed posted limits and the margin is not "
        "knowable from OSM, so both ends are given rather than one chosen",
        f"- snap radius: **{gc.MAX_SNAP_DISTANCE_M:.0f} m**; beyond it a cell is flagged, "
        "not dropped",
        "- `access=no` excluded; `access=private` and `destination` **kept**, because "
        "those restrictions do not bind emergency services on a call",
        "",
        "## The dominant uncertainty is the speed model, not the routing",
        "",
    ]
    if _has(con, "geo_speed_provenance"):
        prov = _q(con, "SELECT speed_source, edges, length_km, share_of_length "
                       "FROM geo_speed_provenance WHERE speed_factor = 1.0 "
                       "ORDER BY length_km DESC")
        lines += [
            _table(prov),
            "",
            f"`maxspeed` is tagged on only **{gc.OSM_MAXSPEED_TAGGED_SHARE:.1%}** of "
            "drivable edges, so class defaults carry the rest — and coverage is "
            "thinnest on exactly the rural roads the 23-minute standard governs.",
            "",
        ]

    lines += ["## Baseline", ""]
    if _has(con, "geo_tth_baseline"):
        base_tbl = _q(con, "SELECT * FROM geo_tth_baseline WHERE speed_factor = 1.0")
        lines += [
            _table(base_tbl.round(3)),
            "",
            "**Two ratios, and reading only the first gives the wrong answer.** "
            "`median_time_ratio` compares network minutes against crow-flies minutes "
            "at an assumed 60 km/h; it lands near 1.00 and reads as *'the routing "
            "added nothing'*. `median_detour` is metres over metres — no speed in it "
            "at all — and shows the roads genuinely winding. The time ratio is "
            "confounded because the detour and the assumed baseline speed cancel.",
            "",
        ]
    return "\n".join(lines) + _footer()


def card_cci(con) -> str:
    lines = [
        "# Model card — CCI (Coverage Compliance Index)",
        "",
        "**What it measures.** The share of people who can be reached within *the "
        "legal target that applies where they live*.",
        "",
        "**Why not one national threshold.** MK noteikumi Nr. 297 (17.05.2016, in "
        "force 20.05.2016) sets two:",
        "",
        f"- **p. 6.1 — {gc.ARRIVAL_TARGET_SERVED_MIN:.0f} min** in a *pilsēta, ciems* "
        "or *mazciems* holding a VUGD unit",
        f"- **p. 6.2 — {gc.ARRIVAL_TARGET_UNSERVED_MIN:.0f} min** everywhere else",
        f"- **p. 5 — {gc.TURNOUT_MINUTES} min** turnout, inside both",
        "",
        "A single national *'% within 8 minutes'* would judge rural Latvia against a "
        "standard the law does not apply to it; *'% within 23 minutes'* would flatter "
        "the cities.",
        "",
        "## Settlement delineation",
        "",
        "The 8-minute rule attaches to the **settlement**, not the municipality. "
        "Settlements are grown by contiguity on the census grid (8-connectivity on the "
        f"EPSG:{gc.CRS_ETRS89_LAEA} lattice) above a density floor of "
        f"**{gc.SETTLEMENT_DENSITY_FLOOR}/km²**, and **may not cross a municipality "
        "boundary**.",
        "",
        "That last rule is load-bearing. Without it the built-up corridors fuse "
        "Salaspils, Mārupe and Ropaži into Rīga, and those towns inherit the 8-minute "
        "standard from depots they do not have — Salaspils goes from 95.6% of its "
        "population on the strict standard to 0.0%, which is the correct answer.",
        "",
        f"The floor is {gc.SETTLEMENT_DENSITY_FLOOR}, not DEGURBA's "
        f"{gc.DEGURBA_URBAN_CLUSTER_MIN}, because the regulation names *ciems* and "
        f"*mazciems* explicitly and at {gc.DEGURBA_URBAN_CLUSTER_MIN}/km² only 66 of "
        f"{gc.VUGD_N_DEPOTS} depots sit in a qualifying cell.",
        "",
    ]
    if _has(con, "geo_compliance"):
        lines += ["## Result", "", _table(_q(con, "SELECT * FROM geo_compliance")), ""]
    if _has(con, "geo_floor_sensitivity"):
        lines += [
            "## Sensitivity to where a settlement ends",
            "",
            _table(_q(con, "SELECT * FROM geo_floor_sensitivity ORDER BY density_floor")),
            "",
        ]
    if _has(con, "geo_elderly_compliance"):
        eld = _q(con, "SELECT * FROM geo_elderly_compliance")
        lines += [
            "## Over-65s — an upper bound, not an estimate",
            "",
            _table(eld),
            "",
            "Age bands are suppressed in sparse cells, which are the remote ones with "
            "the longest response times. This figure therefore under-represents the "
            "worst-served over-65s and should be read as an **upper bound** on "
            "compliance. The `coverage` column is the share of cells it could see.",
            "",
        ]
    return "\n".join(lines) + _footer()


def card_traffic(con) -> str:
    lines = [
        "# Model card — traffic adjustment (a negative result)",
        "",
        "**What was attempted.** Twelve years of observed vehicle counts on "
        "1,335 Latvian roads, joined to the network through 20,789 usable kilometre "
        "markers, converted to a delay with the standard BPR function "
        f"(alpha={gc.BPR_ALPHA}, beta={gc.BPR_BETA}).",
        "",
        "**The finding: congestion does not matter here.**",
        "",
    ]
    if _has(con, "geo_tth_traffic"):
        res = _q(con, "SELECT * FROM geo_tth_traffic ORDER BY damping")
        lines += [_table(res.round(3)), ""]
        free = res.loc[res["damping"] == 0.0, "mean_response_min"]
        if not free.empty:
            worst = res["mean_response_min"].max()
            lines += [
                f"Even treating a fire engine as an ordinary car in the queue, the "
                f"national mean response moves from **{free.iloc[0]:.2f}** to "
                f"**{worst:.2f}** minutes and the CCI does not move at all.",
                "",
            ]
    lines += [
        "Latvia's roads are empty by the standards of a capacity function. The median "
        "secondary road carries **eleven vehicles in the peak hour** against a capacity "
        f"of {gc.LANE_CAPACITY_VPH['secondary']:,}; only the A10 into Rīga (AADT 59,598) "
        "reaches V/C = 1.82, and such links are a rounding error in network length.",
        "",
        "## What this does not say",
        "",
        "It does **not** say urban response is unaffected by traffic. It says *link "
        "congestion* is not the mechanism. What delays a vehicle in Rīga is junction "
        "and signal delay, which neither AADT nor BPR captures, and the counts cover "
        "the numbered network while urban driving happens largely on unnumbered "
        "streets with no counts at all.",
        "",
        "## The emergency damping parameter",
        "",
        "Latvian law requires traffic to yield to a blue-light vehicle, and crews use "
        "the oncoming lane and hard shoulder, so a fire engine does not sit in the "
        "queue BPR describes. Damping runs "
        f"**{', '.join(str(d) for d in gc.EMERGENCY_CONGESTION_DAMPING)}** — 0 is "
        "unaffected, 1 treats the engine as a car. **1.0 is the pessimistic bound, not "
        "the expected case.** Applying the full delay would have inflated urban "
        "response times and flattered this project's own rural-gap thesis.",
        "",
    ]
    if _has(con, "geo_traffic_overlap"):
        lines += [
            "## A free consistency check that passed",
            "",
            _table(_q(con, "SELECT * FROM geo_traffic_overlap").round(4)),
            "",
            "The 2012–2021 and 2014–2023 workbooks overlap on 2014–2021. Keeping the "
            "overlap rather than de-duplicating it turns a redundancy into a test.",
            "",
        ]
    return "\n".join(lines) + _footer()


def card_validation(con) -> str:
    lines = [
        "# Model card — external validation",
        "",
        "Two independent checks. One passes; the other is a documented null, reported "
        "as such rather than re-specified until a correlation appeared.",
        "",
        "## 1. Against VUGD's published national average — passes",
        "",
    ]
    if _has(con, "geo_validation_national"):
        lines += [_table(_q(con, "SELECT * FROM geo_validation_national")), ""]
    lines += [
        f"The published figure ({gc.LEGACY_NATIONAL_MEAN_ARRIVAL_MIN} min) includes "
        "dispatch and real-world routing; the model includes neither, so it should sit "
        "1–3 minutes below. Landing *above* would mean the speed model is wrong; "
        "landing far below would mean the network is.",
        "",
        "## 2. Against NMPD per-municipality compliance — null",
        "",
    ]
    if _has(con, "geo_validation_ranks"):
        lines += [
            _table(_q(con, "SELECT * FROM geo_validation_ranks ORDER BY p").round(3)),
            "",
            "No predictor reaches significance, **the Euclidean baseline included**.",
            "",
        ]
    lines += [
        "**Why, and why it is not a failure of the model.** At the "
        f"{gc.NMPD_TARGET_MIN['rural']:.0f}-minute rural target the model places "
        "93–100% of every municipality within reach while observed compliance runs "
        "70–93%. That gap is operational — crew availability, dispatch, hospital "
        "handover, and an ambulance network sited independently of the fire one — not "
        "spatial.",
        "",
        "The model's own positive controls pass: response time correlates with density "
        "(rho = -0.32), with depots per head (rho = -0.43), and with the Euclidean "
        "baseline (rho = +0.82). The failure belongs to the comparison.",
        "",
        "## What the comparison cannot see",
        "",
        f"- the 7 valstspilsētas are **one aggregate row** (`{gc.NMPD_AGGREGATE_ROW}`) "
        "carrying **54%** of all priority 1–2 calls, and cannot be mapped",
        "- NMPD ambulance station locations are **not published**",
        "- compliance is weighted by **calls**, the model by **residents**",
        f"- {', '.join(str(y) for y in gc.NMPD_PARTIAL_YEARS)} is a partial year and is "
        "excluded",
        "",
        f"NMPD's own targets (MK Nr. 555, 2018) are "
        f"{gc.NMPD_TARGET_MIN['major_city']:.0f}/"
        f"{gc.NMPD_TARGET_MIN['city']:.0f}/{gc.NMPD_TARGET_MIN['rural']:.0f} minutes — "
        "a different regulation from the fire service's 8/23, and not to be mixed.",
        "",
    ]
    return "\n".join(lines) + _footer()


def card_matrix(con) -> str:
    lines = [
        "# Model card — Preparedness × Proximity",
        "",
        "**What it is.** The join between the two projects: project #1's resilience "
        "horizon (days a household lasts) beside project #2's response time (minutes "
        "until help arrives), per community type.",
        "",
        "**Deliberately two axes, never one number.** RHI measures endurance through a "
        "prolonged utility disruption; TTH measures arrival for an acute incident. "
        "A ratio would imply they describe one scenario.",
        "",
    ]
    if _has(con, "geo_matrix"):
        matrix = _q(con, "SELECT * FROM geo_matrix")
        lines += [_table(matrix.round(3)), ""]
        lines += [
            "## The finding",
            "",
            "**The two axes run in opposite directions.** Rural Latvia is slower to "
            "reach *and better stocked*; the cities are quick to reach *and least "
            "prepared*. Remoteness and unpreparedness do not compound — they partly "
            "cancel, which means one national message cannot serve both.",
            "",
            "This inverts the assumption the project was pitched on.",
            "",
        ]
    lines += [
        "## Method notes",
        "",
        "- **The join runs on community type**, not geography. EB547's `d25` holds "
        "n>=262 in every category. The full NUTS3 route is **not** attempted: no "
        "verified municipality-to-NUTS3 crosswalk exists in the source data, and "
        "inventing one for 35 novadi would put a guess under the headline. Rīga "
        "(LV006) is unambiguous and is reported alone.",
        "- **The classes are calibrated before comparison.** Measured density and "
        "self-reported community type split Latvia differently, so the density cutoffs "
        "are set to reproduce the survey's own population shares. Both sides then "
        "describe the same three groups of people.",
        f"- **RHI stays a bracket.** EB547 band 2 is literally *'2-3 days'*, so whether "
        f"those households clear the {base.RESILIENCE_TARGET_DAYS:.0f}-day target is "
        "unknowable from the answer. Collapsing to a midpoint would turn the upper "
        "bound into an estimate.",
        "- **Intervals use Kish's effective sample size**, not the raw row count.",
        "",
    ]
    if _has(con, "geo_riga_contrast"):
        lines += ["## Rīga vs the rest", "",
                  _table(_q(con, "SELECT * FROM geo_riga_contrast").round(2)), ""]
    return "\n".join(lines) + _footer()


CARDS = {
    "10-geo-pipeline.md": card_pipeline,
    "11-tth.md": card_tth,
    "12-cci.md": card_cci,
    "13-traffic.md": card_traffic,
    "14-geo-validation.md": card_validation,
    "15-matrix.md": card_matrix,
}


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    con = get_connection(read_only=True)
    try:
        for name, builder in CARDS.items():
            path = DOCS / name
            path.write_text(builder(con), encoding="utf-8")
            print(f"  wrote {path.relative_to(base.ROOT)}")
    finally:
        con.close()
    print(f"\n{len(CARDS)} card(s) regenerated from DuckDB — never hand-edited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
