"""Tests for the weighting helpers and the gap index.

Index functions are pure column transforms, so they can be tested on small
hand-built frames where the right answer is known by inspection. That is the
whole reason for keeping I/O out of them.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.indices.pgi import ACTION_COLS, gap_cells, gap_table, person_pgi
from actionwise.weighting import (
    effective_n,
    share_ci,
    weighted_mean,
    weighted_share,
)


# ── weighting ──────────────────────────────────────────────────────────────

def test_weighted_mean_respects_weights():
    df = pd.DataFrame({"v": [0.0, 10.0], "w": [3.0, 1.0]})
    assert weighted_mean(df, "v", "w") == pytest.approx(2.5)


def test_weighted_share_denominator_convention():
    """The two conventions must differ, and differ in the documented direction."""
    df = pd.DataFrame({"flag": [1.0, 0.0, np.nan, np.nan], "w": [1.0] * 4})
    # Excluding nulls: 1 of 2 substantive answers.
    assert weighted_share(df, "flag", "w", fillna=False) == pytest.approx(0.5)
    # Published convention: nulls count as false but stay in the denominator.
    assert weighted_share(df, "flag", "w", fillna=True) == pytest.approx(0.25)


def test_non_positive_and_missing_weights_are_dropped():
    df = pd.DataFrame({"v": [1.0, 1.0, 0.0], "w": [np.nan, -1.0, 2.0]})
    assert weighted_mean(df, "v", "w") == pytest.approx(0.0)


def test_effective_n_never_exceeds_row_count_and_equals_it_when_flat():
    flat = pd.DataFrame({"w": [1.0] * 10})
    assert effective_n(flat, "w") == pytest.approx(10.0)

    skewed = pd.DataFrame({"w": [9.0] + [0.1] * 9})
    assert effective_n(skewed, "w") < 10.0


def test_share_ci_brackets_the_estimate():
    lo, hi = share_ci(0.5, 100)
    assert lo < 0.5 < hi
    assert (lo, hi) == pytest.approx((0.402, 0.598), abs=0.01)


# ── gap index ──────────────────────────────────────────────────────────────

def _frame(n: int = 200) -> pd.DataFrame:
    """Half aware, and the aware half acts twice as often on every measure."""
    rng = np.random.default_rng(0)
    aware = np.array([True, False] * (n // 2))
    df = pd.DataFrame({"saw_info": aware, "w_eu": 1.0})
    for col in ACTION_COLS:
        p = np.where(aware, 0.6, 0.3)
        df[col] = rng.binomial(1, p).astype("float64")
    return df


def test_gap_cells_partition_the_observations():
    cells = gap_cells(_frame(), weight="w_eu")
    assert set(cells["cell"]) == {"converted", "gap", "intrinsic", "unreached"}
    assert cells["weighted_share"].sum() == pytest.approx(1.0)


def test_gap_table_conversion_and_gap_are_complementary():
    t = gap_table(_frame(), weight="w_eu")
    assert len(t) == len(ACTION_COLS)
    assert (t["conversion"] + t["gap"]).tolist() == pytest.approx([1.0] * len(t))
    assert t["conversion"].between(0, 1).all()


def test_gap_table_recovers_a_planted_lift():
    """Aware respondents act twice as often, so lift should sit near 2."""
    t = gap_table(_frame(4000), weight="w_eu")
    assert t["lift"].mean() == pytest.approx(2.0, abs=0.15)


def test_person_pgi_is_null_for_the_unaware():
    """Someone who saw no information has no knowing-doing gap to measure."""
    df = _frame(4)
    pgi = person_pgi(df)
    assert pgi[df["saw_info"]].notna().all()
    assert pgi[~df["saw_info"]].isna().all()


def test_person_pgi_endpoints():
    df = pd.DataFrame({"saw_info": [True, True], "w_eu": [1.0, 1.0]})
    for col in ACTION_COLS:
        df[col] = [1.0, 0.0]          # first did everything, second did nothing
    pgi = person_pgi(df)
    assert pgi.iloc[0] == pytest.approx(0.0)   # aware and fully acted -> no gap
    assert pgi.iloc[1] == pytest.approx(1.0)   # aware and did nothing -> total gap


def test_person_pgi_difficulty_weighting_shifts_the_score():
    """Skipping a hard item should cost less than skipping an easy one."""
    df = pd.DataFrame({"saw_info": [True], "w_eu": [1.0]})
    for i, col in enumerate(ACTION_COLS):
        df[col] = [0.0 if i == 0 else 1.0]     # skipped only the first item
    flat = person_pgi(df).iloc[0]
    discounted = person_pgi(df, difficulty={ACTION_COLS[0].removeprefix("act_"): 0.1}).iloc[0]
    assert discounted < flat
