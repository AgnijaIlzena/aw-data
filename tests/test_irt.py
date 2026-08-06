"""Tests for the 2PL item bank.

An IRT model is easy to get subtly wrong and hard to notice, so these tests fit
on *synthetic data with known parameters* and check that the truth comes back.
If the estimator cannot recover difficulties it planted itself, nothing it says
about preparedness is worth reading.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.models.irt import (
    diagnose_dimensionality,
    face_validity,
    fit_2pl,
    item_fit,
    response_matrix,
    score_ability,
    theta_to_pri,
)


def simulate(n: int = 3000, seed: int = 7) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Responses from a known 2PL, laid out like the real cleaned frame."""
    rng = np.random.default_rng(seed)
    true_b = np.array([-1.5, -0.5, 0.5, 1.5])
    true_a = np.array([1.2, 1.4, 1.1, 1.3])
    theta = rng.normal(size=n)
    p = 1 / (1 + np.exp(-true_a * (theta[:, None] - true_b)))
    cols = [f"act_i{i}" for i in range(len(true_b))]
    df = pd.DataFrame((rng.random((n, len(true_b))) < p).astype(float), columns=cols)
    return df, true_b, cols


def test_response_matrix_is_integer_and_complete_case():
    """girth indexes with the response values, so floats and bools break it."""
    df, _, cols = simulate(50)
    df.loc[0, cols[0]] = np.nan
    matrix, index = response_matrix(df, cols)
    assert matrix.dtype.kind == "i"
    assert len(matrix) == 49 and 0 not in index


def test_fit_recovers_planted_difficulties():
    df, true_b, cols = simulate()
    bank = fit_2pl(df, cols)
    est = bank.set_index("item")["difficulty"].reindex([c.removeprefix("act_") for c in cols])
    assert np.corrcoef(est.to_numpy(), true_b)[0, 1] > 0.99
    assert np.abs(est.to_numpy() - true_b).max() < 0.4


def test_bank_is_sorted_easiest_first():
    df, _, cols = simulate()
    bank = fit_2pl(df, cols)
    assert bank["difficulty"].is_monotonic_increasing


def test_harder_items_are_less_often_endorsed():
    df, _, cols = simulate()
    bank = fit_2pl(df, cols)
    assert bank["p_observed"].is_monotonic_decreasing


def test_ability_tracks_the_number_of_items_endorsed():
    df, _, cols = simulate(1500)
    bank = fit_2pl(df, cols)
    theta = score_ability(df, bank, cols)
    assert theta.notna().all()
    assert theta.corr(df[cols].sum(axis=1)) > 0.95


def test_theta_to_pri_is_a_percentile():
    pri = theta_to_pri(pd.Series([-np.inf, 0.0, np.inf]))
    assert pri.iloc[0] == pytest.approx(0.0)
    assert pri.iloc[1] == pytest.approx(50.0)
    assert pri.iloc[2] == pytest.approx(100.0)


def test_item_fit_is_near_one_when_the_model_is_true():
    """Data generated *by* a 2PL should fit a 2PL."""
    df, _, cols = simulate(3000)
    bank = fit_2pl(df, cols)
    fit = item_fit(df, bank, score_ability(df, bank, cols), cols)
    assert fit["infit"].between(0.7, 1.3).all()
    assert not fit["misfitting"].any()


def test_face_validity_rejects_an_inverted_bank():
    """The guard must actually fire — a check that never fails protects nothing."""
    bad = pd.DataFrame(
        {
            "item": ["grab_bag", "flashlight_candles", "training_exercise",
                     "first_aid_kit", "neighbourhood_discussion", "emergency_food_drink"],
            # grab_bag easier than a flashlight: substantively impossible
            "difficulty": [-2.0, 2.0, -1.5, 1.5, -1.0, 1.0],
            "p_observed": [0.08, 0.53, 0.09, 0.41, 0.08, 0.32],
        }
    )
    assert not bool(face_validity(bad)["pass"].all())


def test_face_validity_accepts_a_sensible_bank():
    good = pd.DataFrame(
        {
            "item": ["flashlight_candles", "first_aid_kit", "emergency_food_drink",
                     "grab_bag", "training_exercise", "neighbourhood_discussion"],
            "difficulty": [-0.4, 0.2, 0.6, 4.0, 4.0, 5.3],
            "p_observed": [0.53, 0.41, 0.32, 0.08, 0.09, 0.08],
        }
    )
    assert bool(face_validity(good)["pass"].all())


def test_dimensionality_split_partitions_the_bank():
    bank = pd.DataFrame(
        {
            "item": list("abcdef"),
            "discrimination": [1.5, 1.4, 1.5, 0.5, 0.6, 0.4],
            "difficulty": [0.1, 0.2, 0.3, 4.0, 4.1, 4.2],
            "p_observed": [0.5, 0.4, 0.3, 0.1, 0.1, 0.1],
        }
    )
    dims = diagnose_dimensionality(bank, split_at=1.0)
    assert dims["n_items"].tolist() == [3, 3]
    assert dims.loc[0, "mean_a"] > dims.loc[1, "mean_a"]
