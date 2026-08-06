"""Tests for Phase 11 (optional FEMA / ACI module).

These run on synthetic data, so they pass whether or not the FEMA files have been
downloaded — the module has to be correct before the data arrives, not after.

Column discovery gets the most attention: FEMA ships "unedited raw data" with
headers that vary by year, so the failure mode is not a crash but a table full of
nulls that still looks like a result.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.fema import config as fcfg
from actionwise.fema.aci import _binary, aci_by_year, aci_table, stage_distribution
from actionwise.fema.loader import FemaDataMissing, available_years, discover_columns, find_weight

CROSSWALK = pytest.importorskip("pathlib") and None  # keep import list tidy


def synthetic(n: int = 2000, seed: int = 5, year: int = 2023) -> pd.DataFrame:
    """Paired A3/PREPB columns where awareness genuinely doubles the action rate."""
    rng = np.random.default_rng(seed)
    data = {"survey_year": year, "weight": rng.uniform(0.5, 2.0, n)}
    for item in ("alerts", "supplies", "neighbours"):
        keyword = {"alerts": "alerts", "supplies": "supplies", "neighbours": "neighbors"}[item]
        aware = rng.binomial(1, 0.6, n)
        acted = rng.binomial(1, np.where(aware == 1, 0.4, 0.2))
        data[f"A3_{keyword}"] = aware.astype(float)
        data[f"PREPB_{keyword}"] = acted.astype(float)
    data[fcfg.STAGE_VAR] = rng.integers(1, 6, n).astype(float)
    return pd.DataFrame(data)


# ── column discovery ───────────────────────────────────────────────────────

def test_discovery_pairs_awareness_with_action():
    report = discover_columns(synthetic())
    paired = report[report["paired"]]
    assert set(paired["item"]) == {"alerts", "supplies", "neighbours"}
    row = paired.set_index("item").loc["alerts"]
    assert row["awareness_col"].startswith("A3")
    assert row["action_col"].startswith("PREPB")


def test_discovery_reports_unpaired_items_rather_than_dropping_them():
    """An item present on only one side must be visible, not silently absent."""
    df = synthetic().drop(columns=["PREPB_alerts"])
    report = discover_columns(df)
    alerts = report.set_index("item").loc["alerts"]
    # unmatched columns land as NaN once the report becomes a DataFrame
    assert pd.notna(alerts["awareness_col"])
    assert pd.isna(alerts["action_col"])
    assert bool(alerts["paired"]) is False
    assert len(report) == len(fcfg.ITEMS), "every item gets a row, matched or not"


def test_discovery_on_an_unrecognised_file_pairs_nothing():
    report = discover_columns(pd.DataFrame({"foo": [1], "bar": [2]}))
    assert not report["paired"].any()


def test_find_weight_prefers_a_known_name_then_falls_back():
    assert find_weight(pd.DataFrame({"weight": [1.0]})) == "weight"
    assert find_weight(pd.DataFrame({"nhs_final_wt": [1.0]})) == "nhs_final_wt"
    assert find_weight(pd.DataFrame({"x": [1.0]})) is None


# ── response coding ────────────────────────────────────────────────────────

def test_binary_handles_the_codings_fema_actually_uses():
    assert _binary(pd.Series([1.0, 0.0])).tolist() == [1.0, 0.0]
    assert _binary(pd.Series([1, 2, 1])).tolist() == [1.0, 0.0, 1.0]     # CATI 1/2
    assert _binary(pd.Series(["Yes", "No"])).tolist() == [1.0, 0.0]


def test_binary_nulls_unknown_codes_rather_than_guessing():
    out = _binary(pd.Series([1.0, 0.0, 9.0, 99.0]))
    assert out.iloc[0] == 1.0 and out.iloc[1] == 0.0
    assert out.iloc[2:].isna().all(), "refusal/DK codes must not become zeros"


# ── ACI ────────────────────────────────────────────────────────────────────

def test_aci_recovers_the_planted_conversion_and_lift():
    df = synthetic(6000)
    table = aci_table(df, discover_columns(df), "weight")
    assert len(table) == 3
    assert table["aci"].between(0.35, 0.45).all()
    assert table["lift"].between(1.7, 2.3).all()


def test_conversion_and_gap_are_complementary():
    df = synthetic()
    table = aci_table(df, discover_columns(df), "weight")
    assert (table["aci"] + table["gap"]).tolist() == pytest.approx([1.0] * len(table))


def test_unpaired_items_are_excluded_from_the_table():
    df = synthetic().drop(columns=["PREPB_alerts"])
    table = aci_table(df, discover_columns(df), "weight")
    assert "alerts" not in set(table["item"])
    assert len(table) == 2


def test_weighting_is_recorded_in_the_output():
    df = synthetic()
    mapping = discover_columns(df)
    assert bool(aci_table(df, mapping, "weight")["weighted"].all()) is True
    assert bool(aci_table(df, mapping, None)["weighted"].any()) is False


def test_by_year_keeps_years_separate_and_flags_the_caveat():
    df = pd.concat([synthetic(1500, seed=1, year=2022),
                    synthetic(1500, seed=2, year=2023)], ignore_index=True)
    out = aci_by_year(df, discover_columns(df), "weight")
    assert set(out["survey_year"]) == {2022, 2023}
    assert "cross-section" in out.attrs["caveat"]


# ── stage of change ────────────────────────────────────────────────────────

def test_stage_distribution_covers_the_ladder_and_sums_to_one():
    df = synthetic(3000)
    stages = stage_distribution(df, fcfg.STAGE_VAR, "weight")
    assert len(stages) == len(fcfg.STAGE_LABELS)
    assert stages["share"].sum() == pytest.approx(1.0)


# ── the crosswalk ──────────────────────────────────────────────────────────

def test_crosswalk_documents_the_recall_window_mismatch():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "actionwise" / "fema" / "crosswalk.csv"
    cw = pd.read_csv(path)
    assert {"eb547_item", "fema_item", "match_quality", "eb547_recall",
            "fema_recall", "note"} <= set(cw.columns)

    matched = cw.dropna(subset=["eb547_item", "fema_item"])
    assert (matched["eb547_recall"] != matched["fema_recall"]).all(), (
        "every matched pair must record that the recall windows differ — a 12-month "
        "flow and a lifetime stock are not the same quantity"
    )
    assert set(matched["match_quality"]) <= {"exact", "partial"}
    assert (matched["match_quality"] == "exact").sum() >= 5


def test_crosswalk_records_that_the_grab_bag_has_no_us_equivalent():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "actionwise" / "fema" / "crosswalk.csv"
    cw = pd.read_csv(path)
    grab = cw[cw["eb547_item"] == "grab_bag"].iloc[0]
    assert pd.isna(grab["fema_item"]), "ActionWise's Sac 72h is a Europe-only item"


# ── graceful absence ───────────────────────────────────────────────────────

def test_missing_data_raises_with_instructions_not_a_bare_path():
    if available_years():
        pytest.skip("FEMA data is present in this checkout")
    from actionwise.fema.loader import require_data

    with pytest.raises(FemaDataMissing) as exc:
        require_data()
    message = str(exc.value)
    assert "fema.gov" in message
    assert "browser" in message.lower()
