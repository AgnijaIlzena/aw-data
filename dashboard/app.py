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

import sys
from pathlib import Path

# Le paquet vit dans src/. En local on passe PYTHONPATH=src ; sur un hebergeur
# on ne controle pas l'environnement, donc on ajoute le chemin nous-memes.
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

from actionwise.config import (
    COUNTRY_NAMES,
    DUCKDB_PATH,
    FOCUS_COUNTRIES,
    RESILIENCE_TARGET_DAYS,
)

LOGO = Path(__file__).parent / "assets" / "actionwise-logo.jpg"

st.set_page_config(
    page_title="ActionWise — Readiness",
    page_icon=str(LOGO) if LOGO.exists() else "🛟",
    layout="wide",
)

# ── Palette ActionWise ─────────────────────────────────────────────────────
# Relevée sur le logo : autruche corail, lettrage vert ardoise, fond sauge.
# Le tableau de bord, le produit et la soutenance partagent ainsi les mêmes couleurs.
BG = "#F4F7F6"       # sauge très clair
SURFACE = "#FFFFFF"
BORDER = "#CFDCDA"   # sauge du logo, assombrie pour servir de filet
INK = "#2F4A49"      # vert ardoise assombri, pour le corps de texte
SAGE = "#DCE5E4"     # la sauge exacte du logo

# Quatre teintes volontairement éloignées : une série voisine d'une autre doit
# rester distinguable sur un vidéoprojecteur, y compris en niveaux de gris.
ACCENT = "#2E4C4B"   # vert ardoise profond — la série principale
WARN = "#D06A66"     # corail de l'autruche — ce qui alerte, ou le pays suivi
GOOD = "#D9A441"     # ambre (jeton produit) — ce qui va bien
FAINT = "#BACBC9"    # sauge pâle — l'arrière-plan d'un graphique, jamais du texte
MUTED = "#5F7472"    # ardoise désaturé : filets, repères et texte secondaire

FONT = "Barlow, system-ui, -apple-system, Segoe UI, sans-serif"

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stMetric, button, input, select, textarea,
h1, h2, h3, h4, h5, h6 { font-family: 'Barlow', system-ui, sans-serif !important; }
h1, h2, h3 { color: #2F4A49; letter-spacing: -0.01em; }
section[data-testid="stSidebar"] { background: #DCE5E4; border-right: 1px solid #CFDCDA; }
[data-testid="stMetricValue"] { color: #3B5958; }
</style>
""",
    unsafe_allow_html=True,
)

pio.templates["actionwise"] = go.layout.Template(
    layout=dict(
        font=dict(family=FONT, color=INK, size=13),
        paper_bgcolor=BG,
        plot_bgcolor=SURFACE,
        colorway=[ACCENT, WARN, GOOD, FAINT, "#6E9996", "#B8524E"],
        xaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        yaxis=dict(gridcolor=BORDER, zerolinecolor=BORDER, linecolor=BORDER),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        colorscale=dict(sequential=[[0, SAGE], [1, ACCENT]]),
    )
)
pio.templates.default = "actionwise"
px.defaults.template = "actionwise"


# ── data access — the only way this file touches data ──────────────────────

# Defined once in dashboard/_db.py, re-exported here because every page below
# already calls them by these names.
from dashboard._db import available_tables, q, require  # noqa: E402
from dashboard.i18n import LANGS, set_lang, t  # noqa: E402


def pct(v: float) -> str:
    return "—" if pd.isna(v) else f"{v * 100:.1f}%"


# ── pages ──────────────────────────────────────────────────────────────────

def page_overview() -> None:
    st.title(t('The knowing–doing gap'))
    st.caption(
        t("Europeans know what to do to prepare for a crisis. Most still haven't done it. Eurobarometer ZA8841 · 26,405 respondents · 27 Member States · fieldwork Feb–Mar 2024")
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
        st.subheader(t('Every person × measure falls in one of four cells'))
        order = ["converted", "gap", "intrinsic", "unreached"]
        d = cells.set_index("cell").loc[order].reset_index()
        fig = px.bar(
            d, x="weighted_share", y="cell", orientation="h", text=d["weighted_share"].map(pct),
            color="cell",
            color_discrete_map={"gap": WARN, "converted": GOOD, "intrinsic": ACCENT,
                                "unreached": FAINT},
            labels={"weighted_share": t('share of observations'), "cell": ""},
        )
        fig.update_layout(showlegend=False, height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        st.caption(
            t('**gap** = saw information, did not act. The largest single cell, and the addressable one.')
        )

    with right:
        st.subheader(t('Readiness by country'))
        pri = q("SELECT * FROM pri_by_country ORDER BY mean_pri DESC")
        fig = px.bar(
            pri, x="mean_pri", y="country", orientation="h",
            color=pri["country"].eq("LV").map({True: "Latvia", False: "Other"}),
            color_discrete_map={"Latvia": WARN, "Other": FAINT},
            labels={"mean_pri": t('mean PRI (0–100)'), "country": ""},
        )
        fig.update_layout(showlegend=False, height=560, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")


def page_gap() -> None:
    st.title(t('Which measures information actually converts'))
    if not require("gap_table_eu"):
        return

    tables = available_tables()
    scopes = {"EU": "gap_table_eu"} | {
        COUNTRY_NAMES.get(c, c): f"gap_table_{c.lower()}"
        for c in FOCUS_COUNTRIES
        if f"gap_table_{c.lower()}" in tables
    }
    scope = st.radio("Scope", list(scopes), horizontal=True)
    table = q(f"SELECT * FROM {scopes[scope]} ORDER BY conversion DESC")

    st.subheader(t('Conversion versus lift'))
    st.caption(
        t('**Conversion** = of those who saw information, how many acted. **Lift** = how many times more likely to have acted if aware. High lift with low conversion is where information helps but is not enough — and where a guided tool beats a leaflet.')
    )
    fig = px.scatter(
        table, x="conversion", y="lift", text="label", size="pct_did_overall",
        labels={"conversion": t('conversion P(acted | aware)'), "lift": t('lift (× more likely)')},
        color="lift", color_continuous_scale="Blues",
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.add_hline(y=1.0, line_dash="dot", line_color=MUTED)
    fig.update_layout(height=520, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

    st.subheader(t('Per measure'))
    show = table[["label", "pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware",
                  "gap", "lift"]].copy()
    for c in ("pct_did_overall", "pct_did_if_aware", "pct_did_if_not_aware", "gap"):
        show[c] = show[c].map(pct)
    show["lift"] = table["lift"].map(lambda v: "—" if pd.isna(v) else f"{v:.2f}×")
    show.columns = ["Measure", "Did it", "Did it (aware)", "Did it (unaware)", "Gap", "Lift"]
    st.dataframe(show, width="stretch", hide_index=True)


# Which barrier a SHAP feature belongs to — used only to colour the chart, so
# "capability vs information" reads at a glance rather than needing the legend.
_DRIVER_GROUPS = {
    "prep_no_time_or_money": "capability barrier",
    "prep_needs_more_info": "information barrier",
    "info_feels_informed": "information barrier",
    "info_trusts_official_info": "information barrier",
    "info_info_easy_to_find": "information barrier",
    "info_knows_where_abroad": "information barrier",
}
_DRIVER_COLOURS = {
    "capability barrier": WARN,
    "information barrier": ACCENT,
    "other": FAINT,
}


def page_drivers() -> None:
    st.title(t('What predicts the gap'))
    st.caption(
        t('Not how big the gap is — Phase 3 answers that — but *why* someone sits in it. Two candidate explanations are measured separately by the survey: **qc8_3**, no time or money to prepare, and **qc8_5**, needs more information. They imply opposite products, so telling them apart matters.')
    )
    if not require("gap_shap", "gap_model_comparison"):
        return

    comparison = q("SELECT * FROM gap_model_comparison")
    full = comparison[comparison["model"] == "full model"].iloc[0]
    demo = comparison[comparison["model"] == "demographics only"].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Full model, R²", f"{full['r2_oof']:.3f}",
              help="Out-of-fold — the model never saw these rows during training")
    c2.metric("Demographics only, R²", f"{demo['r2_oof']:.3f}",
              help="Worse than guessing the average — demographics alone explain nothing")
    c3.metric("Mean predictor, R²", "0.000", help="The honest floor, by definition")
    st.caption(
        t("**Tested on countries the model never trained on.** 5-fold cross-validation, grouped by country rather than split at random, so a country's whole data is held out in each round and predicted blind. The R² above is computed only from those held-out predictions — never from data the model was trained on. Demographics alone score *below* zero, i.e. worse than a flat average; only adding the barrier and attitude questions makes the model useful.")
    )

    st.subheader(t('Every model beside its baseline'))
    shown = comparison.copy()
    shown["r2_oof"] = shown["r2_oof"].map("{:.4f}".format)
    shown["mae_oof"] = shown["mae_oof"].map("{:.4f}".format)
    st.dataframe(shown, width="stretch", hide_index=True)

    st.divider()
    st.subheader(t('Ranked by SHAP — how much each factor moves the prediction'))
    st.caption(
        t('SHAP opens the model back up after fitting: for every prediction, it assigns each feature a share of the credit or blame. The bars are the average size of that contribution, ranked — this is what turns a black-box prediction into a stated, checkable finding.')
    )
    shap_tbl = q("SELECT * FROM gap_shap ORDER BY mean_abs_shap DESC")
    shap_tbl["rank"] = range(1, len(shap_tbl) + 1)
    shap_tbl["group"] = shap_tbl["feature"].map(_DRIVER_GROUPS).fillna("other")

    fig = px.bar(
        shap_tbl.sort_values("mean_abs_shap"), x="mean_abs_shap", y="feature",
        orientation="h", color="group",
        color_discrete_map=_DRIVER_COLOURS,
        labels={"mean_abs_shap": t('mean |SHAP value| (average influence on the prediction)'),
               "feature": "", "group": ""},
    )
    fig.update_layout(height=620, margin=dict(t=10, b=10), legend=dict(orientation="h", y=1.05))
    st.plotly_chart(fig, width="stretch")

    capability_rank = int(shap_tbl.loc[shap_tbl["feature"] == "prep_no_time_or_money", "rank"].iloc[0])
    info_rank = int(shap_tbl.loc[shap_tbl["feature"] == "prep_needs_more_info", "rank"].iloc[0])
    st.info(
        f"**Capability ranks {capability_rank} of {len(shap_tbl)}. Information ranks "
        f"{info_rank}.** People are not mostly stuck for want of a leaflet — a better "
        "guide will not close this gap on its own. Cheaper kit, reminders, or "
        "community provision are the products that match what the data says."
    )

    if "gap_barrier_direction" in available_tables():
        st.subheader(t('The two barriers, head to head'))
        direction = q("SELECT * FROM gap_barrier_direction")
        show = direction.copy()
        show["spread_agree_minus_disagree"] = show["spread_agree_minus_disagree"].map(pct)
        show.columns = ["Barrier", "Feature", "Gap, agree vs disagree"]
        st.dataframe(show, width="stretch", hide_index=True)
        st.caption(
            "Among people who agree they lack time or money, the gap runs "
            f"{direction.iloc[0]['spread_agree_minus_disagree']:.1%} wider than among "
            "those who disagree — more than double the same comparison for "
            "'needs more information'. Same conclusion, seen a second way."
        )


def page_rhi() -> None:
    st.title(t('Resilience horizon — how long a household could cope'))
    if not require("rhi_bands_eu", "rhi_bands_lv", "rhi_binding_eu", "rhi_by_country"):
        return

    st.caption(
        f"The minimum across five lifelines — water, power, gas, food, medication. "
        f"A household with a month of food and one day of water has a one-day horizon. "
        f"Target: {RESILIENCE_TARGET_DAYS:.0f} days."
    )

    left, right = st.columns(2)
    with left:
        st.subheader(t('Distribution of the weakest lifeline'))
        eu = q("SELECT *, 'EU' AS scope FROM rhi_bands_eu")
        lv = q("SELECT *, 'Latvia' AS scope FROM rhi_bands_lv")
        both = pd.concat([eu, lv])
        fig = px.bar(both, x="label", y="share", color="scope", barmode="group",
                     color_discrete_map={"EU": FAINT, "Latvia": ACCENT},
                     labels={"share": t('share of households'), "label": ""})
        fig.update_layout(height=380, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")

    with right:
        st.subheader(t('Which lifeline runs out first'))
        binding = q("SELECT * FROM rhi_binding_eu ORDER BY share_binding DESC")
        fig = px.bar(binding, x="share_binding", y="domain", orientation="h",
                     text=binding["share_binding"].map(pct), color_discrete_sequence=[ACCENT],
                     labels={"share_binding": t('share of households where it binds'), "domain": ""})
        fig.update_layout(height=380, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")
        st.caption(
            t('Water and power are ~91% of all binding constraints. Food is under 2% — yet food is the most commonly stockpiled item.')
        )

    st.subheader(t('Country ranking — most exposed first'))
    st.caption(
        t("Reported as a range, not a point: the '2–3 days' band straddles the 72-hour target, so the true share below target lies between these two columns.")
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
    st.plotly_chart(fig, width="stretch")


def page_item_bank() -> None:
    st.title(t('Item bank — what each measure tells us'))
    if not require("item_bank", "item_fit", "item_dimensionality"):
        return

    bank = q("SELECT * FROM item_bank ORDER BY difficulty")
    st.caption(
        t('2PL item response theory. **Difficulty** is how far along the trait you must be before the measure becomes likely; **discrimination** is how sharply it separates prepared from unprepared.')
    )

    fig = px.scatter(
        bank, x="difficulty", y="discrimination", text="label", size="p_observed",
        color="discrimination", color_continuous_scale="Blues",
        labels={"difficulty": t('difficulty (b)'), "discrimination": t('discrimination (a)')},
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.update_layout(height=480, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

    st.subheader(t('The battery measures two things, not one'))
    dims = q("SELECT * FROM item_dimensionality")
    for _, row in dims.iterrows():
        st.markdown(
            f"**{row['group']}** — {int(row['n_items'])} items · mean a = {row['mean_a']} · "
            f"mean b = {row['mean_b']}  \n<span style='color:{MUTED}'>{row['items']}</span>",
            unsafe_allow_html=True,
        )
    st.info(
        t('Discrimination splits cleanly into a sharp group (supplies you buy and store) and a flat group (things you do and arrange). 2PL assumes a single trait, so PRI is dominated by the sharp group. A two-dimensional model is the principled next step.')
    )

    st.subheader(t('Item fit'))
    fit = q("SELECT f.item, b.label, f.infit, f.outfit, f.misfitting "
            "FROM item_fit f JOIN item_bank b USING (item) ORDER BY f.outfit")
    st.dataframe(fit, width="stretch", hide_index=True)
    st.caption(t('Productive range is 0.5–1.5. All 13 items fall inside it.'))


def page_country() -> None:
    st.title(t('Country versus Europe'))
    if not require("holdout_transfer", "holdout_difficulty_compare"):
        return

    transfer = q("SELECT * FROM holdout_transfer")
    available = [c for c in FOCUS_COUNTRIES if c in set(transfer["country"])]
    if not available:
        st.warning(t('No focus country has been scored yet — run scripts/run_holdout.py.'))
        return

    iso = st.radio(
        "Country", available, horizontal=True,
        format_func=lambda c: COUNTRY_NAMES.get(c, c),
    )
    name = COUNTRY_NAMES.get(iso, iso)
    row = transfer[transfer["country"] == iso].iloc[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("θ correlation", f"{row['theta_correlation']:.4f}",
              help=f"Pooled bank (EU without {name}) vs a {name}-only bank")
    c2.metric("Mean |PRI difference|", f"{row['mean_abs_pri_difference']:.2f} pts")
    c3.metric(f"{name} respondents", f"{int(row['n_target']):,}")

    if bool(row["passes_transfer"]):
        st.success(
            f"A bank calibrated without {name} ranks its respondents essentially as "
            "their own bank would, so pooling all of Europe to estimate the item "
            f"parameters is justified — which matters because {int(row['n_target']):,} "
            "respondents cannot calibrate 13 items alone."
        )
    else:
        st.error(
            f"Pooled and native scores diverge for {name}. The items do not behave the "
            "same way there, and the pooled bank should not be used unexamined."
        )

    # The transfer quality is itself comparable across countries, and the
    # difference is a finding: the same method does not fit every country equally.
    if len(available) > 1:
        with st.expander("How well does pooling transfer, country by country?"):
            side = transfer[transfer["country"].isin(available)][
                ["country", "n_target", "theta_correlation", "theta_rank_correlation",
                 "difficulty_correlation", "mean_abs_pri_difference", "passes_transfer"]
            ].round(4)
            st.dataframe(side, width="stretch", hide_index=True)
            best = transfer.loc[transfer["theta_correlation"].idxmax(), "country"]
            st.caption(
                f"All pass the 0.95 threshold, but not equally — {COUNTRY_NAMES.get(best, best)} "
                "transfers most cleanly. A lower correlation means that country's "
                "preparedness items sit in a different order than the European average, "
                "so its scores lean more on the pooled bank's assumptions."
            )

    st.subheader(f"Where {name} genuinely differs")
    comp = q(f"SELECT * FROM holdout_difficulty_compare WHERE country = '{iso}' ORDER BY delta")
    fig = px.bar(
        comp, x="delta", y="label", orientation="h",
        color=comp["delta"].lt(0).map({True: f"Easier in {name}", False: f"Harder in {name}"}),
        color_discrete_map={f"Easier in {name}": ACCENT, f"Harder in {name}": WARN},
        labels={"delta": t('difficulty difference (native − pooled)'), "label": ""},
    )
    fig.update_layout(height=460, margin=dict(t=10, b=10), legend_title="")
    st.plotly_chart(fig, width="stretch")
    st.caption(
        t("Negative means the action is *more common* there than the European average, positive means rarer. This is the shape of a country's preparedness culture, not its overall level.")
    )

    st.subheader(t('PRI percentiles — the benchmark the product shows'))
    table_name = f"pri_percentiles_{iso.lower()}"
    if table_name in available_tables():
        pct_table = q(f"SELECT * FROM {table_name}")
        st.dataframe(pct_table, width="stretch", hide_index=True)
        if bool(pct_table["thin_cell"].any()):
            st.warning(
                t('Age bands flagged `thin_cell` are built on fewer than 100 effective respondents. Show the national figure there instead of the band.')
            )
    else:
        st.info(f"`{table_name}` not built yet — run scripts/run_holdout.py.")


def page_composite() -> None:
    st.title(t('Composite readiness — how much should each index count?'))
    if not require("pri_respondents", "rhi_respondents", "pgi_respondents"):
        return

    st.caption(
        t('The three indices measure different things: how much you have done (PRI), how long you could last (RHI), and how much of what you know about you have skipped (PGI). Weighting them is a judgement, not a fact — so it is exposed rather than hidden.')
    )

    c1, c2, c3 = st.columns(3)
    w_pri = c1.slider("PRI — measures taken", 0.0, 1.0, 0.4, 0.05)
    w_rhi = c2.slider("RHI — days of autonomy", 0.0, 1.0, 0.4, 0.05)
    w_gap = c3.slider("PGI — known but not done (inverted)", 0.0, 1.0, 0.2, 0.05)

    total = w_pri + w_rhi + w_gap
    if total == 0:
        st.warning(t('Set at least one weight above zero.'))
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
        t('Move the sliders. The ranking re-sorts live — which is the point: the ordering is a consequence of a weighting choice, and the choice is visible.')
    )

    with c2:
        fig = px.bar(
            ranked, x="score", y="country", orientation="h",
            color=ranked["country"].eq("LV").map({True: "Latvia", False: "Other"}),
            color_discrete_map={"Latvia": WARN, "Other": FAINT},
            labels={"score": t('composite readiness (0–100)'), "country": ""},
        )
        fig.update_layout(showlegend=False, height=640, margin=dict(t=10, b=10),
                          yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")


def page_fema() -> None:
    """Phase 11 (optional). Listed only when its tables exist — deleting them
    removes the page, so nothing here needs unpicking to drop the phase."""
    st.title(t('United States comparison — item-level conversion'))
    st.caption(
        t("FEMA's National Household Survey asks awareness and action over the *same* twelve measures, so conversion can be computed per message. Europe asks awareness once, globally — which is why this cannot be done on EB547.")
    )

    aci = q("SELECT * FROM fema_aci ORDER BY aci DESC")
    fig = px.scatter(
        aci, x="aci", y="lift", text="label", size="share_aware",
        labels={"aci": t('conversion P(did | aware of this measure)'), "lift": t('lift')},
        color="lift", color_continuous_scale="Oranges",
    )
    fig.update_traces(textposition="top center", textfont_size=10)
    fig.add_hline(y=1.0, line_dash="dot", line_color=MUTED)
    fig.update_layout(height=480, margin=dict(t=20, b=10), coloraxis_showscale=False)
    st.plotly_chart(fig, width="stretch")

    if "fema_stage_of_change" in available_tables():
        st.subheader(t('Stage of change'))
        stages = q("SELECT * FROM fema_stage_of_change ORDER BY stage")
        fig = px.bar(stages, x="share", y="label", orientation="h",
                     color_discrete_sequence=[ACCENT],
                     labels={"share": t('share of households'), "label": ""})
        fig.update_layout(height=320, margin=dict(t=10, b=10))
        st.plotly_chart(fig, width="stretch")
        st.caption(
            t("A validated intention→action ladder with no EB547 equivalent — the empirical grounding for the avatar's progression.")
        )

    if "fema_eu_comparison" in available_tables():
        st.subheader(t('Europe versus United States'))
        st.warning(
            t('**Comparison only, never pooled.** FEMA measures a 12-month flow; EB547 measures a lifetime stock. Directions are comparable; levels are not.')
        )
        st.dataframe(q("SELECT * FROM fema_eu_comparison"), width="stretch",
                     hide_index=True)

    st.info(
        t("FEMA NHS is a **repeated cross-section** — roughly 5,000 different people each year, not a panel. Any trend here is an aggregate trend; nothing in this data supports predicting an individual's transition from aware to acted.")
    )


def page_method() -> None:
    st.title(t('Method, and what this cannot tell you'))

    st.subheader(t('The gate'))
    st.markdown(
        t('Nothing downstream was trusted until the pipeline reproduced figures the European Commission published from this same survey — all seven within ±0.6 points.')
    )
    if "gap_model_comparison" in available_tables():
        st.subheader(t('Driver model against its baselines'))
        st.dataframe(q("SELECT * FROM gap_model_comparison"), width="stretch",
                     hide_index=True)
        st.caption(
            t('Grouped 5-fold CV by country. Demographics alone score *below* the mean predictor — who you are barely predicts preparedness.')
        )
    if "rhi_model_summary" in available_tables():
        st.subheader(t('Ordered probit on the horizon bands'))
        st.dataframe(q("SELECT * FROM rhi_model_summary"), width="stretch",
                     hide_index=True)
        st.caption(t('Two of five domains do not beat their baseline. Reported, not hidden.'))

    st.subheader(t('Limitations'))
    st.markdown(
        t((
            '- **Self-reported throughout.** Nobody checked a cupboard. These are *perceived* horizons and *claimed* measures.\n'
            '- **One snapshot, February–March 2024.** No trend, no causal design.\n'
            '- **Association, not causation.** People who saw information and acted may simply be the sort of people who do both.\n'
            '- **Latvia is 1,008 respondents.** Enough for national figures, thin once split by age — bands below 100 respondents are flagged in the tables.\n'
            "- **The action battery has no time window.** It asks what you have *already* adopted, so it is a lifetime stock, not a 12-month flow. It is not comparable to FEMA's equivalent without adjustment.\n"
            '- **The battery is not unidimensional** (see Item bank). PRI is dominated by the supplies items.'
        ))
    )


# ── shell ──────────────────────────────────────────────────────────────────

PAGES = {
    "Overview": page_overview,
    "The gap": page_gap,
    "What predicts the gap": page_drivers,
    "Resilience horizon": page_rhi,
    "Item bank": page_item_bank,
    "Country vs Europe": page_country,
    "Composite (live weights)": page_composite,
    "Method & limitations": page_method,
}


def main() -> None:
    # La langue est choisie avant tout rendu : chaque t() plus bas en depend.
    # Liste deroulante et non boutons radio : les tests de rendu pilotent la
    # page par at.radio[0], qui doit rester le selecteur de page.
    picked = st.sidebar.selectbox(
        "Language / Langue",
        list(LANGS),
        format_func=lambda c: LANGS[c],
        key="lang",
        label_visibility="collapsed",
    )
    set_lang(picked)

    if LOGO.exists():
        # Le fond du logo est la sauge de la barre latérale : il s'y fond.
        st.sidebar.image(str(LOGO), width="stretch")
    else:
        st.sidebar.title(t('ActionWise'))
    st.sidebar.caption(t('Readiness indices from Eurobarometer ZA8841'))

    if not DUCKDB_PATH.exists():
        st.error(f"No database at {DUCKDB_PATH}. Run `python scripts/run_pipeline.py` first.")
        return

    pages = {t(name): fn for name, fn in PAGES.items()}
    tables = available_tables()

    if "fema_aci" in tables:
        # Optional Phase 11 — appears only once its tables are built.
        pages[t("US comparison (FEMA)")] = page_fema

    choice = st.sidebar.radio(t("Page"), list(pages), label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(
        t('Every figure is read from DuckDB. This dashboard never recomputes an index — the pipeline is the only place they are defined.')
    )
    pages[choice]()


main()
