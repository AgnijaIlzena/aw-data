"""Centralised paths, survey constants and index coefficients.

Imported by the pipeline, the notebooks and the dashboard. Nothing here is
recomputed elsewhere — if a number is used in two places, it lives here.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# ROOT is the actionwise-data repo; RNCP_ROOT is its parent, which also holds
# dati/ (the shared raw store) and ACTIONWISE/ (the docs).
ROOT = Path(__file__).resolve().parents[2]
RNCP_ROOT = ROOT.parent

# Raw data is NOT inside this repo. It lives in RNCP/dati/ and is treated as
# immutable: the pipeline only ever reads from it. This keeps the 133 MB OSM
# extract and the 540 MB Eurostat archive from being duplicated, and makes the
# immutable-raw rule structural rather than a convention someone has to remember.
DATA_RAW = RNCP_ROOT / "dati"

DATA_INTERIM = ROOT / "data" / "interim"
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_DB = ROOT / "data" / "db"

DUCKDB_PATH = DATA_DB / "actionwise.duckdb"

# ---------------------------------------------------------------------------
# Source files
# ---------------------------------------------------------------------------
EB547_SAV = DATA_RAW / "ZA8841_v1-0-0.sav"

# ---------------------------------------------------------------------------
# Eurobarometer ZA8841 — survey structure
# Verified by reading the file directly on 2026-08-05. See
# ACTIONWISE/DATA_PROJECT_BRIEF.md §3.2b for provenance.
# ---------------------------------------------------------------------------

EB547_EXPECTED_SHAPE = (26405, 668)

# Weights. Verified empirically on 2026-08-05 — the labels alone are misleading.
#
#   w1  "result from target (redressment)" — national weight. 28 territories,
#        no nulls. Use for Latvia and every per-country figure.
#   w92 "total (all samples)"              — 28 territories, no nulls.
#        This is the correct EU-wide weight.
#   w22 "EU27"                             — DO NOT USE for EU totals. It is the
#        *pre-2013* EU27, i.e. before Croatia acceded: all 1,001 Croatian
#        respondents have a null w22, so any figure computed with it silently
#        drops a Member State. The file's own "EU27B" labels on w85/w86 confirm
#        Eurobarometer keeps two different EU27 definitions.
#
# The commonly cited `W3`/`WEX` do not exist in this file at all.
WEIGHT_NATIONAL = "w1"
WEIGHT_EU = "w92"
WEIGHT_EU27_LEGACY = "w22"  # kept for reference only; excludes Croatia

# How the published toplines are computed. DG ECHO reports "37% feel well
# prepared" as a share of ALL respondents, with "Don't know" left in the
# denominator — not as a share of those giving a substantive answer. Computed
# the other way the same figure is 39.3%, which is why this is stated here
# rather than left to whoever writes the next query.
TOPLINE_COUNTS_DK_IN_DENOMINATOR = True

# Every QC scale variable carries two off-scale codes. Left as numerics they are
# catastrophic: "Don't know" (6) would outrank "More than 7 days" (4).
QC_OFF_SCALE_CODES = (5, 6)

# The 13 household preparedness measures (qc6.1 … qc6.13), coded 0/1.
# qc6.14 = Other, qc6.15 = Don't know (spontaneous), qc6t = count.
QC6_ITEMS = {
    "qc6.1": "emergency_food_drink",
    "qc6.2": "emergency_water",
    "qc6.3": "flashlight_candles",
    "qc6.4": "battery_radio",
    "qc6.5": "first_aid_kit",
    "qc6.6": "documents_safe",
    "qc6.7": "grab_bag",            # the "Sac 72h" — ActionWise's flagship module
    "qc6.8": "signed_up_alerts",
    "qc6.9": "training_exercise",
    "qc6.10": "knows_official_plan",
    "qc6.11": "family_contact_plan",  # the WHO step of the 5W wizard
    "qc6.12": "neighbourhood_discussion",
    "qc6.13": "home_protection",
}
# Human-readable labels for charts and tables, keyed by the cleaned column suffix.
QC6_LABELS = {
    "emergency_food_drink": "Emergency food & drink stock",
    "emergency_water": "Emergency water (cooking, hygiene)",
    "flashlight_candles": "Flashlight or candles",
    "battery_radio": "Battery-powered radio",
    "first_aid_kit": "First-aid kit",
    "documents_safe": "Key documents copied / stored safely",
    "grab_bag": "Grab-bag ready for evacuation",
    "signed_up_alerts": "Signed up for official alerts",
    "training_exercise": "Took part in training or a drill",
    "knows_official_plan": "Knows the local emergency plan",
    "family_contact_plan": "Agreed family contact method",
    "neighbourhood_discussion": "Discussed protection with neighbours",
    "home_protection": "Invested in home protection",
}

QC6_OTHER = "qc6.14"   # "Other" — counted by qc6t, but not one of the 13
QC6_DK = "qc6.15"      # if 1, the 13 items are unanswered — not zero

# The survey's own count, used to validate ours. Two traps, both verified:
#   * it counts the 13 items PLUS "Other" (qc6.14)
#   * it is BANDED — code 5 means "5 or more", not exactly 5 (6 = Don't know)
# Compared correctly, min(derived_count_incl_other, 5) == qc6t for 23,912 of
# 23,912 non-DK respondents: an exact match.
QC6_TOTAL = "qc6t"
QC6_TOTAL_TOP_BAND = 5

# The five resilience-horizon domains (qc7_1 … qc7_5).
# Scale: 1 = 1 day or less · 2 = 2-3 days · 3 = 4-7 days · 4 = More than 7 days
QC7_DOMAINS = {
    "qc7_1": "water",
    "qc7_2": "power",
    "qc7_3": "gas_heating",
    "qc7_4": "food",
    "qc7_5": "medication",   # 5 = "Not applicable" here means no chronic treatment
}

# Interval midpoints, in days. The top band is open-ended (">7 days") so 10 is a
# censored stand-in, not an estimate — RHI is reported as "3+ days" above the cap.
QC7_MIDPOINT_DAYS = {1: 1.0, 2: 2.5, 3: 5.5, 4: 10.0}
QC7_CENSOR_ABOVE = 7.0

# 4-point agreement scales, running 1 = Totally agree → 4 = Totally disagree.
# Higher raw value means LESS agreement, so these get reversed during cleaning.
QC_AGREE_MAX = 4
QC5_ITEMS = {
    "qc5_1": "saw_info_last_12m",   # the awareness side of the gap
    "qc5_2": "feels_informed",
    "qc5_3": "trusts_official_info",
    "qc5_4": "info_easy_to_find",
    "qc5_5": "knows_where_abroad",
}
QC8_ITEMS = {
    "qc8_1": "prep_helps_cope",
    "qc8_2": "feels_well_prepared",
    "qc8_3": "no_time_or_money",     # capability barrier
    "qc8_4": "prep_info_easy",
    "qc8_5": "needs_more_info",      # information barrier
    "qc8_6": "knows_alert_channel",
    "qc8_7": "knows_what_to_do",
    "qc8_8": "employer_encourages",
    "qc8_9": "services_encourage",
}

# Demographics kept for the driver model.
DEMOGRAPHIC_ITEMS = {
    "d10": "gender",
    "d11": "age",
    "d11r2": "age_band",
    "d25": "community_type",
    "d60": "bill_difficulties",
    "d63": "social_class",
}

# Context items used only as *predictors* of the gap (Phase 6). Deliberately
# excludes anything derived from qc6, which is what the gap is computed from —
# feeding those back in would be leakage dressed up as a finding.
CONTEXT_ITEMS = {
    "qc3.15": "no_disaster_experience",   # 1 = has NOT experienced one in 10 years
    "qc3t": "n_disasters_experienced",
    "qc2a": "top_personal_risk",          # categorical, 13 hazard types
    "qc1a": "top_country_risk",           # categorical
    "qc10": "trusts_emergency_services",
    "qc11": "volunteers_for_responders",
}

ID_VARS = ["uniqid", "serialid", "isocntry"]

# ---------------------------------------------------------------------------
# Index coefficients — starting values, meant to be re-estimated.
# Never hardcode these inside an index function.
# ---------------------------------------------------------------------------

# PRI = w_K * theta_K + w_A * theta_A. EB547 measures action only, so w_A = 1.0
# until FEMA supplies a knowledge trait. Kept explicit so the composite is
# visible rather than implied.
PRI_WEIGHTS = {"knowledge": 0.0, "action": 1.0}

# The published target the product is built around.
RESILIENCE_TARGET_DAYS = 3.0

# ---------------------------------------------------------------------------
# Phase 2 sanity gate — DG ECHO's published figures for this survey.
# Nothing downstream is trusted until the pipeline reproduces these.
# Source: DG ECHO press summary, 30 Sept 2024; Verian topline.
# ---------------------------------------------------------------------------
PUBLISHED_MARGINALS = {
    "qc8_2_agree_eu27": 0.37,      # "feel well prepared" — fewer than 4 in 10
    "qc8_5_agree_eu27": 0.65,      # "need more information" — almost 2 in 3
    "qc7_5_over_7d_eu27": 0.34,    # medication
    "qc7_4_over_7d_eu27": 0.29,    # food
    "qc7_3_over_7d_eu27": 0.20,    # cooking / heating
    "qc8_2_agree_SI": 0.65,        # highest country
    "qc8_2_agree_MT": 0.25,        # lowest country
}
SANITY_TOLERANCE = 0.03  # absolute, on proportions
