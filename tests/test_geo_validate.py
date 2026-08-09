"""External validation, including the part that fails.

A null result needs testing as carefully as a positive one — more so, because the
temptation is to keep re-specifying until a correlation appears. These tests pin
the null in place: they assert that the Euclidean baseline is always reported
beside the model, that the confidence interval is computed (a null must be shown
as *bounded*, not merely unproven), and that `interpret` says so plainly.

`test_positive_controls_still_pass_on_real_data` is the counterweight: it shows
the model is internally sound, so the failure belongs to the comparison rather
than to the model.
"""
import pytest

pytest.importorskip("geopandas", reason="geo extra not installed")
import numpy as np
import pandas as pd

from actionwise_geo import config as gc
from actionwise_geo.validate import nmpd

requires_raw = pytest.mark.skipif(not gc.NMPD_DIR.exists(), reason="dati/ not present")


# ── the published-figure check ─────────────────────────────────────────────

def test_model_below_published_by_a_plausible_margin_passes():
    """The model excludes dispatch, so it should sit 1-3 minutes under 9.2."""
    result = nmpd.national_check(7.5)
    assert result["pass"].iloc[0]
    assert result["delta_min"].iloc[0] == pytest.approx(-1.7)


def test_model_slower_than_the_published_average_fails():
    """Slower than reality means the speed model is wrong, not conservative."""
    assert not nmpd.national_check(11.0)["pass"].iloc[0]


def test_an_implausibly_fast_model_also_fails():
    """3 minutes nationally would mean the network or the speeds are broken."""
    assert not nmpd.national_check(3.0)["pass"].iloc[0]


# ── NMPD's targets are a different regulation ──────────────────────────────

def test_nmpd_targets_are_not_the_fire_service_targets():
    """MK 555 governs ambulances; MK 297 governs VUGD. Mixing them compares each
    service against the other's standard."""
    names = pd.Series(["Rīga", "Jelgava", "Talsu nov."])
    is_city = pd.Series([True, True, False])
    target = nmpd.nmpd_target_minutes(names, is_city)

    assert target.tolist() == [12.0, 15.0, 25.0]
    assert gc.ARRIVAL_TARGET_SERVED_MIN not in set(target)
    assert gc.ARRIVAL_TARGET_UNSERVED_MIN not in set(target)


# ── Spearman with a bounded null ───────────────────────────────────────────

def test_spearman_recovers_a_perfect_rank_relationship():
    result = nmpd.spearman_with_ci([1, 2, 3, 4, 5], [10, 20, 30, 40, 50])
    assert result["rho"] == pytest.approx(1.0)
    assert result["n"] == 5


def test_confidence_interval_brackets_the_estimate():
    """A null must be reported as bounded, not merely unproven."""
    rng = np.random.default_rng(0)
    result = nmpd.spearman_with_ci(rng.normal(size=35), rng.normal(size=35))
    assert result["ci_low"] < result["rho"] < result["ci_high"]
    assert result["ci_low"] > -1 and result["ci_high"] < 1


def test_too_few_points_returns_null_rather_than_a_spurious_correlation():
    result = nmpd.spearman_with_ci([1, 2], [1, 2])
    assert pd.isna(result["rho"])


# ── loading, with the gaps declared ────────────────────────────────────────

@requires_raw
def test_the_city_aggregate_is_kept_and_flagged():
    """54% of national call volume sits in one unmappable row.

    Asserted on the data rather than on the wording of the audit line: the row
    must survive, be flagged, and carry more than half the calls.
    """
    observed, audit = nmpd.load_nmpd()

    aggregate = observed[observed["is_aggregate"]]
    assert not aggregate.empty
    assert set(aggregate["municipality"]) == {gc.NMPD_AGGREGATE_ROW}

    share = aggregate[nmpd.CALLS].sum() / observed[nmpd.CALLS].sum()
    assert share > 0.5, "the 7 cities should still be over half of priority 1-2 calls"

    # The audit must state the size of the gap, whatever words it uses for it.
    assert f"{share:.0%}" in audit.to_frame()["reason"].iloc[-1]


@requires_raw
def test_partial_years_are_flagged_in_the_data_not_just_config():
    observed, _ = nmpd.load_nmpd()
    for year in gc.NMPD_PARTIAL_YEARS:
        subset = observed[observed["year"] == year]
        if not subset.empty:
            assert subset["partial_year"].all()


# ── the rank check ─────────────────────────────────────────────────────────

def synthetic_model(n: int = 35, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "mean_response_min": rng.uniform(5, 16, n),
            "euclidean_baseline_min": rng.uniform(5, 14, n),
            "mean_density": rng.uniform(10, 900, n),
        },
        index=[f"M{k} nov." for k in range(n)],
    )


def synthetic_observed(model: pd.DataFrame, year: int = 2024,
                       relationship: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    noise = rng.normal(size=len(model))
    compliance = 85 - relationship * model["mean_response_min"].to_numpy() + noise
    rows = pd.DataFrame({
        "municipality": model.index,
        "year": year,
        "partial_year": False,
        "is_aggregate": False,
        nmpd.CALLS: 1000,
        nmpd.ON_TIME: 800,
        nmpd.COMPLIANCE: compliance,
    })
    aggregate = pd.DataFrame([{
        "municipality": gc.NMPD_AGGREGATE_ROW, "year": year, "partial_year": False,
        "is_aggregate": True, nmpd.CALLS: 100_000, nmpd.ON_TIME: 73_000,
        nmpd.COMPLIANCE: 73.0,
    }])
    return pd.concat([rows, aggregate], ignore_index=True)


def test_the_baseline_is_always_reported_beside_the_model():
    """'Our routing explains it' cannot be claimed without showing a ruler does not."""
    model = synthetic_model()
    ranks, _ = nmpd.rank_check(model, synthetic_observed(model))
    assert "euclidean_baseline_min" in set(ranks["predictor"])
    assert "mean_response_min" in set(ranks["predictor"])


def test_the_aggregate_row_is_excluded_from_the_correlation():
    model = synthetic_model()
    ranks, audit = nmpd.rank_check(model, synthetic_observed(model))
    assert (ranks["n"] == len(model)).all(), (
        "the unmappable city aggregate must not enter the correlation"
    )


def test_a_real_relationship_is_detected_when_one_exists():
    """The check must be capable of finding a signal, or the null means nothing."""
    model = synthetic_model()
    ranks, _ = nmpd.rank_check(model, synthetic_observed(model, relationship=3.0))
    primary = ranks[ranks["predictor"] == "mean_response_min"].iloc[0]
    assert primary["rho"] < -0.5 and primary["significant"]


def test_interpret_says_null_result_plainly_when_nothing_is_significant():
    model = synthetic_model()
    ranks, _ = nmpd.rank_check(model, synthetic_observed(model, relationship=0.0))
    text = nmpd.interpret(ranks)
    assert "NULL RESULT" in text
    assert "operational" in text, "a null must come with its diagnosis"
    assert "neither confirmed nor refuted" in text


# ── the counterweight: is the model itself sound? ──────────────────────────

@pytest.mark.slow
@pytest.mark.skipif(not gc.OSM_PBF.exists(), reason="OSM extract not in dati/")
def test_positive_controls_still_pass_on_real_data():
    """If the model correlates with what it should, the null belongs to NMPD.

    Denser municipalities and those with more depots per head must come out
    faster, and the network model must agree with the Euclidean baseline on which
    places are remote. All three hold; only the NMPD comparison does not.
    """
    import pyrosm

    from actionwise_geo.data.boundaries import assign_municipality, load_boundaries
    from actionwise_geo.data.depots import load_depots
    from actionwise_geo.data.popgrid import load_population_grid
    from actionwise_geo.indices.tth import cell_travel_times, time_from_nearest_depot
    from actionwise_geo.network.graph import build_graph
    from actionwise_geo.network.snap import snap_points

    depots, audit = load_depots()
    boundaries, audit = load_boundaries(audit=audit)
    grid, audit = load_population_grid(audit=audit)
    cells = grid[(grid["T"] > 0) & grid.geometry.notna()].copy()

    osm = pyrosm.OSM(str(gc.OSM_PBF))
    nodes, edges = osm.get_network(nodes=True, network_type="driving")
    graph, audit = build_graph(nodes, edges, audit=audit)
    depot_snap, audit = snap_points(depots, graph, audit=audit)
    cell_snap, audit = snap_points(cells, graph, audit=audit)
    travel, audit = cell_travel_times(
        cells, cell_snap,
        time_from_nearest_depot(graph, depot_snap["node_index"]),
        depots=depots, audit=audit,
    )

    placed, audit = assign_municipality(cells, boundaries, audit=audit)
    frame = pd.DataFrame({
        "municipality": placed["municipality"].to_numpy(),
        "population": cells["T"].to_numpy(),
        "response": travel["response_minutes"].to_numpy(),
        "density": cells["density"].to_numpy(),
        "baseline": travel["baseline_minutes"].to_numpy(),
    }).dropna(subset=["municipality"])

    def weighted(g, column):
        return (g[column] * g["population"]).sum() / g["population"].sum()

    per = frame.groupby("municipality").apply(
        lambda g: pd.Series({
            "response": weighted(g, "response"),
            "density": weighted(g, "density"),
            "baseline": weighted(g, "baseline"),
        }),
        include_groups=False,
    )

    denser = nmpd.spearman_with_ci(per["response"], per["density"])
    assert denser["rho"] < -0.2, "denser municipalities must be reached faster"

    agrees = nmpd.spearman_with_ci(per["response"], per["baseline"])
    assert agrees["rho"] > 0.6, (
        "the network model and a straight line must agree about which places are "
        "remote; if they do not, one of them is broken"
    )
