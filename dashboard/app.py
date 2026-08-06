"""ActionWise readiness dashboard.

Run with:  streamlit run dashboard/app.py

This module **reads DuckDB and nothing else**. It never imports from
`actionwise.indices` or `actionwise.models`, and never recomputes an index —
enforced by tests/test_dashboard_isolation.py.

That rule exists because of the predecessor project: `virality-code`'s dashboard
bypassed its own pipeline entirely, loading a spreadsheet and recomputing every
index in memory, which left 3.9 GB of pipeline output that nothing read and two
divergent definitions of the same number. Here the pipeline is the only place an
index is defined, and the dashboard is a view over its results.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from actionwise.config import DUCKDB_PATH, RESILIENCE_TARGET_DAYS

st.set_page_config(page_title="ActionWise — Readiness", page_icon="🛟", layout="wide")

ACCENT = "#2563eb"
WARN = "#dc2626"
GOOD = "#059669"
MUTED = "#64748b"


# ── data access — the only way this file touches data ──────────────────────

@st.cache_data(show_spinner="Reading DuckDB…")
def q(sql: str) -> pd.DataFrame:
    """Run a read-only query against the shared cache."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


@st.cache_data
def available_tables() -> set[str]:
    return set(q("SELECT table_name FROM duckdb_tables()")["table_name"])


def require(*tables: str) -> bool:
    missing = [t for t in tables if t not in available_tables()]
    if missing:
        st.warning(
            f"Missing table(s): {', '.join(missing)}. Run the pipeline scripts first — "
            "see the README."
        )
        return False
    return True


def pct(v: float) -> str:
    return "—" if pd.isna(v) else f"{v * 100:.1f}%"


# ── pages ──────────────────────────────────────────────────────────────────

def page_overview() -> None:
    st.title("The knowing–doing gap")
    st.caption(
        "Europeans know what to do to prepare for a crisis. Most still haven't done it. "
        "Eurobarometer ZA8841 · 26,405 respondents · 27 Member States · fieldwork Feb–Mar 2024"
    )

    if not require("gap_cells_eu", "rhi_bands_eu", "pri_by_country"):
        return

    cells = q("SELECT * FROM gap_cells_eu")
    gap = float(cells.loc[cells["cell"] == "gap", "weighted_share"].iloc[0])
    converted = float(cells.loc[cells["cell"] == "converted", "weighted_share"].iloc[0])

    bands = q("SELECT * FROM rhi_bands_eu")
    under_1day = float(bands.loc[bands["band"] == 1, "share"].iloc[0])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aware but hasn't acted", pct(gap), help="Share of all person × measure pairs")
    c2.metric("Aware and acted", pct(converted))
    c3.metric("Conversion rate", pct(converted / (converted + gap)),
              help="Of those who saw information, how many acted")
    c4.metric("Households with ≤1 day of resilience", pct(under_1day))

    st.divider()
    left, right = st.columns([3, 2])

    with left:
        st.subheader("Every person × measure falls in one of four cells")
        order = ["converted", "gap", "intrinsic", "unreached"]
        d = cells.set_index("cell").loc[order].reset_index()
        fig = px.bar(
            d, x="weighted_share", y="cell", orientation="h", text=d["weighted_share"].map(pct),
            color="cell",
            color_discrete_map={"gap": WARN, "converted": GOOD, "intrinsic": ACCENT,
                                "unreached": MUTED},
            labels={"weighted_share": "share of observations", "cell": ""},
        )
        fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "**gap** = saw information, did not act. The largest single cell, and the "
            "addressable one."
        )

    with right:
        st.subheader("Readiness by country")
        pri = q("SELECT * FROM pri_by_country ORDER BY mean_pri DESC")
        fig = px.bar(
            pri, x="mean_pri", y="country", orientation="h",
            color=pri["country"].eq("LV").map({True: "Latvia", False: "Other"}),
            color_discrete_map={"Latvia": WARN, "Other": MUTED},
            labels={"mean_pri": "mean PRI (0–100)", "country": ""},
        )
        fig.update_layout(showlegend=False, height=560, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)


def page_gap() -> None:
    st.title("Which measures information actually converts")
    if not require("gap_table_eu", "gap_table_lv"):
        return

    scope = st.radio("Scope", ["EU", "Latvia"], horizontal=True)
    table = q(f"SELECT * FROM gap_table_{'eu' if scope == 'EU' else 'lv'} ORDER BY conversion DESC")

    st.subheader("Conversion versus lift")
    st.caption(
        "**Conversion** = of those who saw information, how many acted. "
        "**Lift** = how many times more likely to have acted if aware. "
        "High lift with low conversion is where information helps but is not enough — "
        "and where a guided tool beats a leaflet."
    )
    fig = px.scatter(
        table, x="conversion", y="lift", text="label", size="pct_did_overall",
        labels={"conversion": "conversion  P(acted | aware)", "lift": "lift  (× more likely)"},
        color="lift", color_continuous_scale="Blues",
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.add_hline(y=1.0, line_dash="dot", line_color=MUTED)
    fig.update_layout(height=520, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Per measure")
    show = table[["label", "pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware",
                  "gap", "lift"]].copy()
    for c in ("pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware", "gap"):
        show[c] = show[c].map(pct)
    show["lift"] = table["lift"].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}×")
    show.columns = ["Measure", "Did it", "Did it (aware)", "Did it (unaware)", "Gap", "Lift"]
    st.dataframe(show, use_container_width=True, hide_index=True)


def page_rhi() -> None:
    st.title("Resilience horizon — how long a household could cope")
    if not require("rhi_bands_eu", "rhi_bands_lv", "rhi_binding_eu", "rhi_by_country"):
        return

    st.caption(
        f"The minimum across five lifelines — water, power, gas, food, medication. "
        f"A household with a month of food and one day of water has a one-day horizon. "
        f"Target: {RESILIENCE_TARGET_DAYS:.0f} days."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Distribution of the weakest lifeline")
        eu = q("SELECT *, 'EU' AS scope FROM rhi_bands_eu")
        lv = q("SELECT *, 'Latvia' AS scope FROM rhi_bands_lv")
        both = pd.concat([eu, lv])
        fig = px.bar(both, x="label", y="share", color="scope", barmode="group",
                     color_discrete_map={"EU": MUTED, "Latvia": ACCENT},
                     labels={"share": "share of households", "label": ""})
        fig.update_layout(height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("Which lifeline runs out first")
        binding = q("SELECT * FROM rhi_binding_eu ORDER BY share_binding DESC")
        fig = px.bar(binding, x="share_binding", y="domain", orientation="h",
                     text=binding["share_binding"].map(pct), color_discrete_sequence=[ACCENT],
                     labels={"share_binding": "share of households where it binds", "domain": ""})
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Water and power are ~91% of all binding constraints. Food is under 2% — "
            "yet food is the most commonly stockpiled item."
        )

    st.subheader("Country ranking — most exposed first")
    st.caption(
        "Reported as a range, not a point: the '2–3 days' band straddles the 72-hour "
        "target, so the true share below target lies between these two columns."
    )
    ranking = q("SELECT * FROM rhi_by_country ORDER BY below_target_certain DESC")
    fig = go.Figure()
    fig.add_bar(y=ranking["country"], x=ranking["below_target_certain"], orientation="h",
                name="certainly below target", marker_color=WARN)
    fig.add_bar(y=ranking["country"],
                x=ranking["below_target_upper"] - ranking["below_target_certain"],
                orientation="h", name="possibly below (2–3 day band)", marker_color="#fca5a5")
    fig.update_layout(barmode="stack", height=620, margin=dict(t=10, b=10),
                      yaxis={"categoryorder": "total ascending"},
                      xaxis_title="share of households below target")
    st.plotly_chart(fig, use_container_width=True)


def page_item_bank() -> None:
    st.title("Item bank — what each measure tells us")
    if not require("item_bank", "item_fit", "item_dimensionality"):
        return

    bank = q("SELECT * FROM item_bank ORDER BY difficulty")
    st.caption(
        "2PL item response theory. **Difficulty** is how far along the trait you must be "
        "before the measure becomes likely; **discrimination** is how sharply it separates "
        "prepared from unprepared."
    )

    fig = px.scatter(
        bank, x="difficulty", y="discrimination", text="label", size="p_observed",
        color="discrimination", color_continuous_scale="Blues",
        labels={"difficulty": "difficulty (b)", "discrimination": "discrimination (a)"},
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.update_layout(height=480, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("The battery measures two things, not one")
    dims = q("SELECT * FROM item_dimensionality")
    for _, row in dims.iterrows():
        st.markdown(
            f"**{row['group']}** — {int(row['n_items'])} items · mean a = {row['mean_a']} · "
            f"mean b = {row['mean_b']}  \n<span style='color:{MUTED}'>{row['items']}</span>",
            unsafe_allow_html=True,
        )
    st.info(
        "Discrimination splits cleanly into a sharp group (supplies you buy and store) and "
        "a flat group (things you do and arrange). 2PL assumes a single trait, so PRI is "
        "dominated by the sharp group. A two-dimensional model is the principled next step."
    )

    st.subheader("Item fit")
    fit = q("SELECT f.item, b.label, f.infit, f.outfit, f.misfitting "
            "FROM item_fit f JOIN item_bank b USING (item) ORDER BY f.outfit")
    st.dataframe(fit, use_container_width=True, hide_index=True)
    st.caption("Productive range is 0.5–1.5. All 13 items fall inside it.")


def page_latvia() -> None:
    st.title("Latvia versus Europe")
    if not require("holdout_transfer", "holdout_difficulty_compare", "pri_percentiles_lv"):
        return

    t = q("SELECT * FROM holdout_transfer").iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("θ correlation", f"{t['theta_correlation']:.4f}",
              help="Pooled bank (EU without Latvia) vs a Latvia-only bank")
    c2.metric("Mean |PRI difference|", f"{t['mean_abs_pri_difference']:.2f} pts")
    c3.metric("Latvian respondents", f"{int(t['n_target']):,}")
    st.success(
        "A bank calibrated without Latvia ranks Latvians essentially as their own bank "
        "would, so pooling all of Europe to estimate the item parameters is justified — "
        "which matters because 1,008 respondents cannot calibrate 13 items alone."
    )

    st.subheader("Where Latvia genuinely differs")
    comp = q("SELECT * FROM holdout_difficulty_compare ORDER BY delta")
    fig = px.bar(
        comp, x="delta", y="label", orientation="h",
        color=comp["delta"].lt(0).map({True: "Easier in Latvia", False: "Harder in Latvia"}),
        color_discrete_map={"Easier in Latvia": GOOD, "Harder in Latvia": WARN},
        labels={"delta": "difficulty difference (native − pooled)", "label": ""},
    )
    fig.update_layout(height=460, margin=dict(t=10, b=10), legend_title="")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Latvians prepare socially and informally — neighbours, family contact, documents — "
        "and skip institutional channels: training, official alerts, formal home protection."
    )

    st.subheader("PRI percentiles — the benchmark the product shows")
    lv = q("SELECT * FROM pri_percentiles_lv")
    st.dataframe(lv, use_container_width=True, hide_index=True)
    if bool(lv["thin_cell"].any()):
        st.warning(
            "Age bands flagged `thin_cell` are built on fewer than 100 respondents. "
            "Show the national figure there instead of the band."
        )


def page_composite() -> None:
    st.title("Composite readiness — how much should each index count?")
    if not require("pri_respondents", "rhi_respondents", "pgi_respondents"):
        return

    st.caption(
        "The three indices measure different things: how much you have done (PRI), how long "
        "you could last (RHI), and how much of what you know about you have skipped (PGI). "
        "Weighting them is a judgement, not a fact — so it is exposed rather than hidden."
    )

    c1, c2, c3 = st.columns(3)
    w_pri = c1.slider("PRI — measures taken", 0.0, 1.0, 0.4, 0.05)
    w_rhi = c2.slider("RHI — days of autonomy", 0.0, 1.0, 0.4, 0.05)
    w_gap = c3.slider("PGI — known but not done (inverted)", 0.0, 1.0, 0.2, 0.05)

    total = w_pri + w_rhi + w_gap
    if total == 0:
        st.warning("Set at least one weight above zero.")
        return
    st.caption(f"Σ = {total:.2f} — weights are renormalised, so only their ratio matters.")

    scores = q(
        """
        SELECT p.country_grouped AS country, p.w_national,
               p.pri,
               (r.rhi_band - 1) / 3.0 * 100 AS rhi_norm,
               (1 - g.pgi) * 100            AS gap_norm
        FROM pri_respondents p
        JOIN rhi_respondents r USING (uniqid)
        JOIN pgi_respondents g USING (uniqid)
        WHERE p.pri IS NOT NULL AND r.rhi_band IS NOT NULL AND g.pgi IS NOT NULL
        """
    )
    scores["composite"] = (
        w_pri * scores["pri"] + w_rhi * scores["rhi_norm"] + w_gap * scores["gap_norm"]
    ) / total

    ranked = (
        scores.assign(wx=scores["composite"] * scores["w_national"])
        .groupby("country")
        .apply(lambda d: pd.Series({"score": d["wx"].sum() / d["w_national"].sum(),
                                    "n": len(d)}), include_groups=False)
        .reset_index()
        .sort_values("score", ascending=False)
    )
    lv_rank = int(ranked.reset_index(drop=True).index[ranked["country"].eq("LV").values][0]) + 1

    c1, c2 = st.columns([2, 3])
    c1.metric("Latvia's rank", f"{lv_rank} of {len(ranked)}")
    c1.metric("Latvia's composite", f"{float(ranked.loc[ranked['country'] == 'LV', 'score'].iloc[0]):.1f}")
    c1.info(
        "Move the sliders. The ranking re-sorts live — which is the point: the ordering "
        "is a consequence of a weighting choice, and the choice is visible."
    )

    with c2:
        fig = px.bar(
            ranked, x="score", y="country", orientation="h",
            color=ranked["country"].eq("LV").map({True: "Latvia", False: "Other"}),
            color_discrete_map={"Latvia": WARN, "Other": MUTED},
            labels={"score": "composite readiness (0–100)", "country": ""},
        )
        fig.update_layout(showlegend=False, height=640, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)


def page_fema() -> None:
    """Phase 11 (optional). Listed only when its tables exist — deleting them
    removes the page, so nothing here needs unpicking to drop the phase."""
    st.title("United States comparison — item-level conversion")
    st.caption(
        "FEMA's National Household Survey asks awareness and action over the *same* "
        "twelve measures, so conversion can be computed per message. Europe asks "
        "awareness once, globally — which is why this cannot be done on EB547."
    )

    aci = q("SELECT * FROM fema_aci ORDER BY aci DESC")
    fig = px.scatter(
        aci, x="aci", y="lift", text="label", size="share_aware",
        labels={"aci": "conversion  P(did | aware of this measure)", "lift": "lift"},
        color="lift", color_continuous_scale="Oranges",
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.add_hline(y=1.0, line_dash="dot", line_color=MUTED)
    fig.update_layout(height=480, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    if "fema_stage_of_change" in available_tables():
        st.subheader("Stage of change")
        stages = q("SELECT * FROM fema_stage_of_change ORDER BY stage")
        fig = px.bar(stages, x="share", y="label", orientation="h",
                     color_discrete_sequence=[ACCENT],
                     labels={"share": "share of households", "label": ""})
        fig.update_layout(height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "A validated intention→action ladder with no EB547 equivalent — the "
            "empirical grounding for the avatar's progression."
        )

    if "fema_eu_comparison" in available_tables():
        st.subheader("Europe versus United States")
        st.warning(
            "**Comparison only, never pooled.** FEMA measures a 12-month flow; EB547 "
            "measures a lifetime stock. Directions are comparable; levels are not."
        )
        st.dataframe(q("SELECT * FROM fema_eu_comparison"), use_container_width=True,
                     hide_index=True)

    st.info(
        "FEMA NHS is a **repeated cross-section** — roughly 5,000 different people each "
        "year, not a panel. Any trend here is an aggregate trend; nothing in this data "
        "supports predicting an individual's transition from aware to acted."
    )


def page_method() -> None:
    st.title("Method, and what this cannot tell you")

    st.subheader("The gate")
    st.markdown(
        "Nothing downstream was trusted until the pipeline reproduced figures the European "
        "Commission published from this same survey — all seven within ±0.6 points."
    )
    if "gap_model_comparison" in available_tables():
        st.subheader("Driver model against its baselines")
        st.dataframe(q("SELECT * FROM gap_model_comparison"), use_container_width=True,
                     hide_index=True)
        st.caption(
            "Grouped 5-fold CV by country. Demographics alone score *below* the mean "
            "predictor — who you are barely predicts preparedness."
        )
    if "rhi_model_summary" in available_tables():
        st.subheader("Ordered probit on the horizon bands")
        st.dataframe(q("SELECT * FROM rhi_model_summary"), use_container_width=True,
                     hide_index=True)
        st.caption("Two of five domains do not beat their baseline. Reported, not hidden.")

    st.subheader("Limitations")
    st.markdown(
        """
- **Self-reported throughout.** Nobody checked a cupboard. These are *perceived* horizons
  and *claimed* measures.
- **One snapshot, February–March 2024.** No trend, no causal design.
- **Association, not causation.** People who saw information and acted may simply be the
  sort of people who do both.
- **Latvia is 1,008 respondents.** Enough for national figures, thin once split by age —
  bands below 100 respondents are flagged in the tables.
- **The action battery has no time window.** It asks what you have *already* adopted, so it
  is a lifetime stock, not a 12-month flow. It is not comparable to FEMA's equivalent
  without adjustment.
- **The battery is not unidimensional** (see Item bank). PRI is dominated by the
  supplies items.
        """
    )


# ── shell ──────────────────────────────────────────────────────────────────

PAGES = {
    "Overview": page_overview,
    "The gap": page_gap,
    "Resilience horizon": page_rhi,
    "Item bank": page_item_bank,
    "Latvia vs Europe": page_latvia,
    "Composite (live weights)": page_composite,
    "Method & limitations": page_method,
}


def main() -> None:
    st.sidebar.title("🛟 ActionWise")
    st.sidebar.caption("Readiness indices from Eurobarometer ZA8841")

    pages = dict(PAGES)
    if DUCKDB_PATH.exists() and "fema_aci" in available_tables():
        # Optional Phase 11 — appears only once its tables are built.
        pages["US comparison (FEMA)"] = page_fema

    choice = st.sidebar.radio("Page", list(pages), label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(
        "Every figure is read from DuckDB. This dashboard never recomputes an index — "
        "the pipeline is the only place they are defined."
    )
    if not DUCKDB_PATH.exists():
        st.error(f"No database at {DUCKDB_PATH}. Run `python scripts/run_pipeline.py` first.")
        return
    pages[choice]()


main()
