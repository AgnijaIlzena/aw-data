"""Project #2 pages — Time-to-Help.

Registered conditionally by `app.py`: they appear only once the `geo_*` tables
exist, and vanish cleanly if those tables are dropped. Kept in their own module
so project #2's dashboard can be removed in one step, exactly as Phase 11 can.

**Reads DuckDB and nothing else.** No import from `actionwise_geo.indices`,
`.network` or `.data` — enforced by tests/test_dashboard_isolation.py. Every
number here was computed by a pipeline script and written to a table.
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from actionwise.config import RESILIENCE_TARGET_DAYS
from dashboard._db import minutes, pct, q, require

ACCENT = "#2563eb"
WARN = "#dc2626"
GOOD = "#059669"


def page_coverage() -> None:
    st.title("Legal coverage — MK noteikumi Nr. 297")
    st.caption(
        "8 minutes in a pilsēta/ciems/mazciems holding a VUGD unit, 23 minutes "
        "elsewhere, both measured from depot departure. Plus 90 seconds turnout."
    )
    if not require("geo_compliance", "geo_settlements"):
        return

    compliance = q("SELECT * FROM geo_compliance ORDER BY target_min")
    overall = compliance[compliance["applies_to"] == "ALL (CCI)"]

    left, middle, right = st.columns(3)
    if not overall.empty:
        left.metric("Coverage Compliance Index", pct(overall["compliance"].iloc[0]),
                    help="Share reaching help within the target that applies THERE")
    served = compliance[compliance["applies_to"] == "served settlement"]
    if not served.empty:
        middle.metric("In 8-minute settlements", pct(served["compliance"].iloc[0]),
                      help=f"{int(served['population'].iloc[0]):,} people")
    elsewhere = compliance[compliance["applies_to"] == "elsewhere"]
    if not elsewhere.empty:
        right.metric("Elsewhere (23 min)", pct(elsewhere["compliance"].iloc[0]),
                     help=f"{int(elsewhere['population'].iloc[0]):,} people")

    st.info(
        "**Why two targets and not one.** A single national *'% within 8 minutes'* "
        "would judge rural Latvia against a standard the law does not apply to it; "
        "*'% within 23 minutes'* would flatter the cities. Each cell is measured "
        "against the target that binds where it is."
    )

    st.subheader("Settlements")
    st.dataframe(q("SELECT * FROM geo_settlements"), width="stretch",
                 hide_index=True)

    if "geo_compliance_by_municipality" in _tables():
        st.subheader("Worst-served municipalities")
        by_muni = q(
            "SELECT \"group\" AS municipality, population, mean_response_min, "
            "share_on_8min_standard, compliance, thin_cell "
            "FROM geo_compliance_by_municipality ORDER BY compliance LIMIT 15"
        )
        st.dataframe(by_muni, width="stretch", hide_index=True)
        st.caption(
            "Rīga appears near the top because 99% of it sits in a depot-served "
            "settlement and is therefore held to the strict 8-minute standard — "
            "more people miss their legal target there than anywhere else."
        )

    if "geo_floor_sensitivity" in _tables():
        st.subheader("Where does a settlement end?")
        st.caption(
            "Settlements are grown by contiguity on the census grid and stop at a "
            "municipality boundary. The density floor is the most arguable choice "
            "in the phase, so the index is reported across the range."
        )
        st.dataframe(q("SELECT * FROM geo_floor_sensitivity ORDER BY density_floor"),
                     width="stretch", hide_index=True)


def page_time_to_help() -> None:
    st.title("Time-to-Help")
    st.caption(
        "Minutes from the nearest of 87 VUGD depots along the real road network, "
        "for every populated 1 km cell."
    )
    if not require("geo_tth", "geo_tth_coverage"):
        return

    factors = sorted(q("SELECT DISTINCT speed_factor FROM geo_tth")["speed_factor"])
    factor = st.radio(
        "Emergency-vehicle speed", factors, horizontal=True,
        format_func=lambda f: ("posted legal limits" if f == 1.0 else f"{f:g}× limits"),
    )
    st.caption(
        "Rescue vehicles lawfully exceed posted limits and the margin is not "
        "knowable from OSM, so both ends are reported rather than one chosen."
    )

    tth = q(f"SELECT * FROM geo_tth WHERE speed_factor = {factor}")
    weighted = (tth["response_minutes"] * tth["population"]).sum() / tth["population"].sum()

    left, middle, right = st.columns(3)
    left.metric("Mean response", minutes(weighted))
    left.caption("population-weighted, incl. 90 s turnout")
    middle.metric("Cells", f"{len(tth):,}")
    unreachable = int(tth.loc[~tth["reachable"].astype(bool), "population"].sum())
    right.metric("Unreachable", f"{unreachable:,}", help="people in cells no depot reaches")

    coverage = q(f"SELECT * FROM geo_tth_coverage WHERE speed_factor = {factor}")
    st.subheader("Population by response time")
    st.dataframe(coverage, width="stretch", hide_index=True)

    st.subheader("Distribution")
    usable = tth[tth["response_minutes"].notna()]
    figure = px.histogram(
        usable, x="response_minutes", y="population", nbins=60,
        labels={"response_minutes": "response time (min)", "population": "people"},
        color_discrete_sequence=[ACCENT],
    )
    figure.add_vline(x=8, line_dash="dash", line_color=GOOD,
                     annotation_text="8 min (served settlements)")
    figure.add_vline(x=23, line_dash="dash", line_color=WARN,
                     annotation_text="23 min (elsewhere)")
    st.plotly_chart(figure, width="stretch")

    if "geo_tth_baseline" in _tables():
        st.subheader("Has the routing earned its complexity?")
        baseline = q(f"SELECT * FROM geo_tth_baseline WHERE speed_factor = {factor}")
        st.dataframe(baseline, width="stretch", hide_index=True)
        st.warning(
            "**Read both ratios.** `median_time_ratio` compares network minutes "
            "against crow-flies minutes at an assumed 60 km/h — it lands near "
            "1.00 and would read as *'routing added nothing'*. `median_detour` is "
            "metres over metres, with no speed in it, and shows the roads winding "
            "by about 23%. The first is confounded; the second is not."
        )

    if "geo_speed_provenance" in _tables():
        with st.expander("Where do the speeds come from?"):
            st.dataframe(
                q(f"SELECT * FROM geo_speed_provenance WHERE speed_factor = {factor}"),
                width="stretch", hide_index=True,
            )
            st.caption(
                "`maxspeed` is tagged on only 18.5% of drivable edges, so the "
                "class defaults drive four fifths of the network — and coverage is "
                "thinnest on exactly the rural roads the 23-minute standard governs. "
                "The speed model, not the routing, is the dominant uncertainty here."
            )


def page_matrix() -> None:
    st.title("Preparedness × Proximity")
    st.caption(
        "Project #1 measures how many days a household lasts. Project #2 measures "
        "how many minutes until help arrives. This is the pair."
    )
    if not require("geo_matrix"):
        return

    matrix = q("SELECT * FROM geo_matrix")

    st.error(
        "**The two axes run in opposite directions.** Rural Latvia is slower to "
        "reach *and better stocked*; the cities are quick to reach *and least "
        "prepared*. Remoteness and unpreparedness do not compound here — they "
        "partly cancel, which means one national message cannot serve both."
    )

    display = matrix.copy()
    display["under 3 days"] = display.apply(
        lambda r: f"{r['share_under_target_certain']:.0%}–"
                  f"{r['share_under_target_upper']:.0%}", axis=1
    )
    st.dataframe(
        display[["community_class", "population", "mean_response_min",
                 "share_beyond_23min", "mean_rhi_days", "under 3 days",
                 "n", "n_effective", "thin_cell"]],
        width="stretch", hide_index=True,
    )
    st.caption(
        f"'under 3 days' is a **bracket**, not a point: EB547's band 2 is literally "
        f"'2-3 days', so whether those households clear the {RESILIENCE_TARGET_DAYS:.0f}-day "
        "target is unknowable from the answer. Intervals use Kish's effective "
        "sample size, not the raw row count."
    )

    figure = px.bar(
        matrix, x="community_class", y="mean_response_min",
        labels={"community_class": "", "mean_response_min": "minutes to help"},
        color_discrete_sequence=[ACCENT],
    )
    second = px.line(matrix, x="community_class", y="mean_rhi_days")
    second.update_traces(yaxis="y2", line_color=WARN, mode="lines+markers")
    figure.add_traces(second.data)
    figure.update_layout(
        yaxis2=dict(title="days of supplies", overlaying="y", side="right"),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(figure, width="stretch")

    if "geo_riga_contrast" in _tables():
        st.subheader("Rīga vs the rest")
        st.dataframe(q("SELECT * FROM geo_riga_contrast"), width="stretch",
                     hide_index=True)
        st.caption(
            "The only NUTS3 comparison made: LV006 is exactly the city of Rīga, so "
            "the survey and the map agree without a crosswalk. The other five "
            "regions are not reported — no verified municipality-to-NUTS3 crosswalk "
            "exists in the source data, and inventing one would put a guess under "
            "the headline."
        )

    if "geo_class_calibration" in _tables():
        with st.expander("How the classes were made comparable"):
            st.dataframe(q("SELECT * FROM geo_class_calibration"), width="stretch",
                         hide_index=True)
            st.caption(
                "Measured density and self-reported community type split Latvia "
                "differently — someone in a dense Rīga suburb may reasonably answer "
                "'small or middle sized town'. The density cutoffs are set to "
                "reproduce the survey's own population shares, so both sides "
                "describe the same three groups of people."
            )


def page_validation() -> None:
    st.title("Validation")
    st.caption("Two external checks. One passes; the other is a documented null.")
    if not require("geo_validation_national", "geo_validation_ranks"):
        return

    national = q("SELECT * FROM geo_validation_national")
    row = national.iloc[0]
    left, right = st.columns(2)
    left.metric("VUGD published mean arrival", minutes(row["published_mean_arrival_min"]))
    right.metric("Model mean response", minutes(row["model_mean_response_min"]),
                 delta=f"{row['delta_min']:+.1f} min")
    if bool(row["pass"]):
        st.success(
            "**Passes.** The model sits below the published figure by the expected "
            "margin — it excludes call-handling time and assumes optimal routing, "
            "so a gap of 1–3 minutes is the right shape. Landing *above* would mean "
            "the speed model is wrong."
        )

    st.subheader("Rank check against NMPD ambulance compliance")
    ranks = q("SELECT * FROM geo_validation_ranks ORDER BY p")
    st.dataframe(ranks, width="stretch", hide_index=True)

    if not bool(ranks["significant"].any()):
        st.warning(
            "**Null result — reported as such.** No predictor reaches significance, "
            "the Euclidean baseline included. At a 25-minute rural target the model "
            "places 93–100% of every municipality within reach while observed "
            "compliance runs 70–93%; that gap is operational — crew availability, "
            "dispatch, handover, and an ambulance network sited independently of "
            "the fire one — not spatial. The model is neither confirmed nor refuted."
        )
    st.caption(
        "The model's own positive controls do pass: response time correlates with "
        "density (ρ = −0.32), with depots per head (ρ = −0.43), and with the "
        "Euclidean baseline (ρ = +0.82). The failure belongs to the comparison, "
        "not to the model."
    )

    with st.expander("What this comparison cannot see"):
        st.markdown(
            "- the 7 valstspilsētas are **one aggregate row carrying 54%** of all "
            "priority 1–2 calls, and cannot be mapped\n"
            "- NMPD ambulance station locations are **not published**; the model "
            "routes from VUGD fire depots, a different network\n"
            "- compliance is weighted by **calls**, the model by **residents** — "
            "the elderly and rural generate more priority 1–2 calls per head\n"
            "- 2025 is a partial year and is excluded"
        )


def page_traffic() -> None:
    st.title("Traffic")
    st.caption("Twelve years of observed vehicle counts on 1,335 Latvian roads.")
    if not require("geo_tth_traffic"):
        return

    result = q("SELECT * FROM geo_tth_traffic ORDER BY damping")
    st.dataframe(result, width="stretch", hide_index=True)

    free = result.loc[result["damping"] == 0.0, "mean_response_min"]
    worst = result["mean_response_min"].max()
    if not free.empty:
        st.info(
            f"**Congestion does not matter here.** Even treating a fire engine as "
            f"an ordinary car in the queue, the national mean response moves from "
            f"{free.iloc[0]:.2f} to {worst:.2f} minutes and the CCI does not move "
            "at all. Latvia's roads are empty by the standards of a capacity "
            "function — the median secondary road carries **eleven vehicles in the "
            "peak hour**."
        )
        st.caption(
            "This does *not* say urban response is unaffected by traffic. It says "
            "link congestion is not the mechanism: what delays a vehicle in Rīga is "
            "junction and signal delay, which neither AADT nor a BPR function "
            "captures, and the counts cover the numbered network while urban "
            "driving happens largely on unnumbered streets."
        )

    if "geo_traffic_overlap" in _tables():
        st.subheader("Cross-check between the two publications")
        st.dataframe(q("SELECT * FROM geo_traffic_overlap"), width="stretch",
                     hide_index=True)
        st.caption(
            "The 2012–2021 and 2014–2023 workbooks overlap on 2014–2021. They agree "
            "on 98.4% of rows with a median difference of zero — a free consistency "
            "test that a naive de-duplication would have discarded."
        )

    if "geo_congestion_summary" in _tables():
        with st.expander("Where the adjustment bites, by road class"):
            st.dataframe(q("SELECT * FROM geo_congestion_summary"), width="stretch",
                         hide_index=True)


def page_geo_method() -> None:
    st.title("Method & limitations — Time-to-Help")
    st.markdown(
        f"""
### What is computed

Travel time from the nearest of **87 VUGD depots** across a routable graph of
**1.35 M nodes / 1.38 M edges** built from a dated OpenStreetMap extract, for every
populated **1 km census cell**. Response time adds the **90-second turnout**
required by MK 297 p. 5.

Compliance is measured against the target that legally applies where each cell
is: **8 minutes** in a settlement holding a depot, **23 minutes** elsewhere.
Settlements are grown by contiguity on the census grid and **stop at a
municipality boundary** — without that rule the built-up corridors fuse
Salaspils, Mārupe and Ropaži into Rīga, and those towns inherit the 8-minute
standard from depots they do not have.

### What it does not do

- **Travel time, not total response time.** The minutes before a call is placed
  and the dispatch decision are not modelled.
- **Speeds are mostly inferred.** `maxspeed` is tagged on 18.5% of drivable
  edges; class defaults carry the rest, and coverage is worst on rural roads.
  Every figure is reported at both 1.0× and 1.2× the posted limit.
- **Ambulances are a different service.** The NMPD comparison is a rank check on
  geography, never a calibration, and it returns null.
- **Age detail is thin where it matters most.** The over-65 figure covers 35% of
  cells; suppression concentrates in sparse cells, which are the remote ones. It
  is an **upper bound** on compliance.
- **A snapshot.** OSM as at the recorded date; census as at 1 January 2021.
- **Availability is not modelled.** The map says where a crew *can* reach, not
  whether one was free.

### The 3-day target

Project #1's resilience horizon uses **{RESILIENCE_TARGET_DAYS:.0f} days**, and
this project imports that constant rather than restating it — two copies of a
headline number is how a dossier ends up quoting two different figures.

### Sources

VUGD depot register and LVC kilometre markers, data.gov.lv (CC0) · OpenStreetMap
Latvia extract, Geofabrik · Eurostat Census 2021 1 km grid V3 · LVC traffic
intensity 2012–2023 · VARAM/VZD administrative territories (CC0) · NMPD priority
1–2 response statistics 2022–2025 (CC0) · MK noteikumi Nr. 297 (17.05.2016) and
Nr. 555 (2018).
        """
    )


def _tables() -> set[str]:
    from dashboard._db import available_tables

    return available_tables()


GEO_PAGES = {
    "Time-to-Help": page_time_to_help,
    "Legal coverage": page_coverage,
    "Preparedness × Proximity": page_matrix,
    "Traffic": page_traffic,
    "Validation": page_validation,
    "Method — Time-to-Help": page_geo_method,
}
