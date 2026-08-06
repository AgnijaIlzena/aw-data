"""Tests for the Resilience Horizon Index.

The interesting cases are all about *absence*: a domain that does not apply, a
domain that went unanswered, and the difference between the two. Getting those
wrong produces a number that looks fine and is wrong, which is the failure mode
this whole project is organised against.
"""
import pandas as pd
import pytest

from actionwise.indices.rhi import (
    DOMAIN_COLS,
    band_distribution,
    binding_domain_profile,
    compute_rhi,
    target_bounds,
)


def _row(**bands) -> pd.DataFrame:
    """One respondent; unnamed domains are left unanswered."""
    data = {c: [pd.NA] for c in DOMAIN_COLS}
    for domain, value in bands.items():
        data[f"days_{domain}"] = [value]
    data["w_eu"] = [1.0]
    data["w_national"] = [1.0]
    return pd.DataFrame(data)


def test_rhi_is_the_minimum_not_the_average():
    """A month of food and one day of water is a one-day household."""
    df = _row(water=1, power=4, gas_heating=4, food=4, medication=4)
    out = compute_rhi(df)
    assert out["rhi_band"].iloc[0] == 1
    assert out["rhi_binding_domain"].iloc[0] == "water"


def test_binding_domain_identifies_the_weakest_lifeline():
    df = _row(water=4, power=3, gas_heating=2, food=4, medication=4)
    out = compute_rhi(df)
    assert out["rhi_binding_domain"].iloc[0] == "gas_heating"
    assert out["rhi_band"].iloc[0] == 2


def test_not_applicable_domain_does_not_count_as_a_failure():
    """Someone taking no medication has no medication horizon — that is not a zero."""
    df = _row(water=3, power=3, gas_heating=3, food=3)
    df["days_medication_not_applicable"] = [True]
    out = compute_rhi(df, min_domains=4)
    assert out["rhi_band"].iloc[0] == 3
    # All five domains accounted for: four answered, one genuinely inapplicable.
    assert bool(out["rhi_partial"].iloc[0]) is False


def test_unanswered_domain_marks_the_result_as_an_upper_bound():
    """The minimum over a subset can only overstate the true horizon."""
    df = _row(water=3, power=3, gas_heating=3, food=3)  # medication simply missing
    out = compute_rhi(df, min_domains=4)
    assert bool(out["rhi_partial"].iloc[0]) is True


def test_too_few_domains_yields_no_score():
    df = _row(water=1, power=2)
    out = compute_rhi(df, min_domains=3)
    assert pd.isna(out["rhi_band"].iloc[0])
    assert pd.isna(out["rhi_binding_domain"].iloc[0])


def test_days_estimate_follows_the_band_midpoints():
    df = _row(water=2, power=3, gas_heating=3, food=4, medication=4)
    out = compute_rhi(df)
    assert out["rhi_band"].iloc[0] == 2
    assert out["rhi_days"].iloc[0] == pytest.approx(2.5)


def test_target_bounds_bracket_rather_than_impute():
    """Band 2 straddles 72h, so the answer is a range, not a point."""
    df = pd.concat(
        [
            _row(water=1, power=1, gas_heating=1, food=1, medication=1),  # certainly below
            _row(water=2, power=2, gas_heating=2, food=2, medication=2),  # straddles
            _row(water=4, power=4, gas_heating=4, food=4, medication=4),  # certainly above
        ],
        ignore_index=True,
    )
    b = target_bounds(compute_rhi(df), weight="w_eu")
    assert b["below_target_certain"] == pytest.approx(1 / 3)
    assert b["below_target_upper"] == pytest.approx(2 / 3)
    assert b["below_target_certain"] <= b["below_target_upper"]


def test_band_distribution_sums_to_one():
    df = pd.concat(
        [_row(water=b, power=4, gas_heating=4, food=4, medication=4) for b in (1, 2, 3, 4)],
        ignore_index=True,
    )
    dist = band_distribution(compute_rhi(df), weight="w_eu")
    assert dist["share"].sum() == pytest.approx(1.0)


def test_binding_profile_shares_sum_to_one():
    df = pd.concat(
        [
            _row(water=1, power=4, gas_heating=4, food=4, medication=4),
            _row(water=4, power=1, gas_heating=4, food=4, medication=4),
        ],
        ignore_index=True,
    )
    prof = binding_domain_profile(compute_rhi(df), weight="w_eu")
    assert prof["share_binding"].sum() == pytest.approx(1.0)
    assert set(prof.loc[prof["share_binding"] > 0, "domain"]) == {"water", "power"}
