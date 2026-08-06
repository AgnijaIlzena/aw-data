"""FEMA National Household Survey — constants.

Phase 11 is self-contained in this package so it can be deleted in one step.
See docs/PHASE11-FEMA.md for what removing it involves.

Provenance note, stated because it matters for how defensively the loader is
written: these item names come from reading the **2022 survey instrument** end to
end (39 pages). The column *headers in the released data files* have not been
verified — FEMA ships "unedited raw data" and the codebook is inside each year's
ZIP. So the loader discovers columns rather than assuming them, and says clearly
what it found when the match fails.
"""
from __future__ import annotations

from actionwise.config import DATA_RAW

# Drop the yearly ZIPs (or their extracted CSVs) here.
FEMA_DIR = DATA_RAW / "fema_nhs"

# Years published by FEMA. 2022 is the one whose instrument was verified.
YEARS = (2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023)
VERIFIED_INSTRUMENT_YEAR = 2022

# The twelve preparedness actions, asked TWICE over the same list:
#   A3    "what information have you read, seen or heard ..."  -> awareness
#   PREPB "what have you done to prepare ..."                  -> action
# That pairing is the whole reason this phase exists: it is the only place where
# awareness and action are observed for the *same* item, which is what makes a
# per-message conversion rate computable. EB547 asks awareness once, globally.
ITEMS = {
    "alerts": "Sign up for alerts and warnings",
    "make_plan": "Make a plan",
    "rainy_day": "Save for a rainy day",
    "drills": "Practice emergency drills or habits",
    "family_comms": "Test family communication plan",
    "documents": "Safeguard documents",
    "neighbours": "Plan with neighbours",
    "supplies": "Assemble or update supplies",
    "community": "Get involved in your community",
    "home_safer": "Make your home safer",
    "evacuation_routes": "Know evacuation routes",
    "insure_property": "Document and insure property",
}

AWARENESS_PREFIX = "A3"
ACTION_PREFIX = "PREPB"

# Stage-of-change ladder — the validated intention->action scale that has no
# equivalent in EB547, and the second reason for this phase.
STAGE_VAR = "ST_STG1"
STAGE_LABELS = {
    1: "Not prepared, no intention",
    2: "Not prepared, intends within a year",
    3: "Not prepared, intends within six months",
    4: "Prepared for less than a year",
    5: "Prepared over a year, still preparing",
}

# Duration items — the FEMA counterpart to EB547's qc7 resilience horizon.
DURATION_VARS = {"SUPP": "supplies_last", "POWE": "without_power", "RUNW": "without_water"}

# Efficacy, experience, risk.
CONTEXT_VARS = {
    "C1": "response_efficacy",
    "C2": "self_efficacy",
    "GENEXP1": "has_experienced_disaster",
    "L1": "perceived_likelihood",
}

# FEMA ships design weights; the exact column name varies by year, so candidates
# are tried in order and the first present wins.
WEIGHT_CANDIDATES = ("weight", "WEIGHT", "wgt", "WGT", "finalwt", "FINALWT", "nhs_weight")

# ---------------------------------------------------------------------------
# The recall-window mismatch — load-bearing, not bookkeeping.
# ---------------------------------------------------------------------------
# FEMA PREPB asks what you did "in the last year"  -> a 12-month FLOW.
# EB547 qc6  asks what you have "already adopted"  -> a lifetime STOCK.
# The two are comparable in *direction* and never poolable in level. Any code
# that averages them is comparing different quantities.
FEMA_RECALL_WINDOW = "12 months"
EB547_RECALL_WINDOW = "lifetime (no window)"

# Published figures for the gate, from FEMA's 2023 summary.
PUBLISHED_2023 = {
    "heard_any_information": 0.89,
    "took_three_or_more_actions": 0.57,
    "assembled_supplies": 0.48,
    "made_a_plan": 0.37,
    "planned_with_neighbours": 0.12,
    "got_involved_in_community": 0.14,
}
SANITY_TOLERANCE = 0.03
