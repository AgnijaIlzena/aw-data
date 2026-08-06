"""Tests for weighted quantiles and the benchmark tables.

These back the single most user-visible number in the product — "better prepared
than N% of Latvians" — so the weighting has to be right. An unweighted percentile
would compare the user to whoever answered the phone rather than to the country.
"""
import numpy as np
import pandas as pd
import pytest

from actionwise.indices.percentiles import benchmark, percentile_table
from actionwise.weighting import weighted_percentile_of, weighted_quantile


def test_equal_weights_reproduce_the_unweighted_median():
    v = pd.Series([1.0, 2, 3, 4, 5, 6, 7, 8, 9])
    w = pd.Series([1.0] * 9)
    assert weighted_quantile(v, w, 0.5) == pytest.approx(np.median(v), abs=1e-9)


def test_weights_move_the_median():
    """Piling weight onto the low values must drag the median down."""
    v = pd.Series([1.0, 2.0, 10.0])
    assert weighted_quantile(v, pd.Series([1.0, 1.0, 1.0]), 0.5) == pytest.approx(2.0)
    heavy_low = weighted_quantile(v, pd.Series([50.0, 50.0, 1.0]), 0.5)
    assert heavy_low < 2.0


def test_quantiles_are_monotonic():
    rng = np.random.default_rng(0)
    v = pd.Series(rng.normal(size=500))
    w = pd.Series(rng.uniform(0.5, 2.0, size=500))
    qs = [weighted_quantile(v, w, q) for q in (0.1, 0.25, 0.5, 0.75, 0.9)]
    assert qs == sorted(qs)


def test_zero_and_missing_weights_are_ignored():
    v = pd.Series([1.0, 2.0, 100.0])
    w = pd.Series([1.0, 1.0, 0.0])
    assert weighted_quantile(v, w, 0.5) == pytest.approx(1.5)


def test_percentile_of_is_bounded_and_ordered():
    v = pd.Series(np.arange(100, dtype=float))
    w = pd.Series(np.ones(100))
    low = weighted_percentile_of(10, v, w)
    high = weighted_percentile_of(90, v, w)
    assert 0 <= low < high <= 100
    assert weighted_percentile_of(50, v, w) == pytest.approx(50.0, abs=1.0)


def test_percentile_table_flags_thin_cells():
    rng = np.random.default_rng(1)
    df = pd.DataFrame(
        {
            "pri": rng.uniform(0, 100, 260),
            "w_national": 1.0,
            # one band with 10 rows, one with 250
            "age_band": [1.0] * 10 + [2.0] * 250,
        }
    )
    table = percentile_table(df, "pri", "age_band", "w_national", min_rows=100)
    flags = table.set_index("group")["thin_cell"]
    assert bool(flags["1.0"]) is True
    assert bool(flags["2.0"]) is False
    assert bool(flags["all"]) is False


def test_percentile_table_always_includes_the_pooled_row():
    """A thin band should be able to fall back on the national figure."""
    df = pd.DataFrame({"pri": [10.0, 50.0, 90.0], "w_national": 1.0, "age_band": [1.0, 1.0, 2.0]})
    table = percentile_table(df, "pri", "age_band", "w_national")
    assert "all" in set(table["group"])


def test_benchmark_produces_the_product_sentence():
    df = pd.DataFrame({"pri": np.arange(0, 100, dtype=float), "w_national": 1.0})
    result = benchmark(75.0, df, "pri", "w_national")
    assert 70 <= result["percentile"] <= 80
    assert "better prepared than" in result["sentence"]
    assert result["n_reference"] == 100


def test_benchmark_handles_an_empty_reference():
    df = pd.DataFrame({"pri": [np.nan, np.nan], "w_national": [1.0, 1.0]})
    result = benchmark(50.0, df, "pri", "w_national")
    assert result["percentile"] is None
    assert "not enough" in result["sentence"]
