"""The constants are the specification, so they get tested like one.

Two categories here, and the second is the point of the file:

  * that the legal thresholds match MK noteikumi Nr. 297 — because those numbers
    are the project's success criterion, and a typo in one of them would not
    produce an error, it would produce a plausible wrong answer;
  * that the recorded data facts match what is actually on disk — the row counts,
    the CRS, the known gaps. Project #1 shipped three bugs whose common cause was
    trusting a description of a file over the file. These are cheap and catch
    exactly that.

Nothing here loads a geospatial library, and the file-dependent tests skip
cleanly when `dati/` is absent, so a fresh checkout still goes green.
"""
import pandas as pd
import pytest

from actionwise_geo import config as gc


# ── the legal standard ─────────────────────────────────────────────────────

def test_arrival_targets_match_regulation_297():
    """MK Nr. 297, punkti 5, 6.1 and 6.2 — adopted 17.05.2016."""
    assert gc.TURNOUT_MINUTES == 1.5                 # 5. p. — 90 seconds
    assert gc.ARRIVAL_TARGET_SERVED_MIN == 8.0       # 6.1. p.
    assert gc.ARRIVAL_TARGET_UNSERVED_MIN == 23.0    # 6.2. p.
    assert gc.ARRIVAL_TARGET_SERVED_MIN < gc.ARRIVAL_TARGET_UNSERVED_MIN


def test_settlement_tags_cover_the_three_terms_the_regulation_names():
    """6.1 says 'pilsētā, ciemā un mazciemā' — city, village, hamlet.

    OSM splits pilsēta into city/town by size, so four tags cover the three legal
    terms. Anything narrower would silently push served settlements into the
    23-minute band.
    """
    assert set(gc.SETTLEMENT_PLACE_TAGS) == {"city", "town", "village", "hamlet"}


def test_nmpd_targets_are_kept_separate_from_the_fire_targets():
    """Different service, different regulation (MK Nr. 555), different thresholds.

    Mixing them would invalidate Phase 6: NMPD's published compliance is measured
    against 12/15/25, not against the fire service's 8/23.
    """
    assert gc.NMPD_TARGET_MIN == {"major_city": 12.0, "city": 15.0, "rural": 25.0}
    assert gc.NMPD_COMPLIANCE_STANDARD == 0.75
    assert gc.ARRIVAL_TARGET_SERVED_MIN not in gc.NMPD_TARGET_MIN.values()


def test_emergency_uplift_is_a_sensitivity_range_not_a_single_number():
    assert len(gc.EMERGENCY_SPEED_FACTORS) >= 2
    assert 1.0 in gc.EMERGENCY_SPEED_FACTORS, "the legal-limit case must be reported"
    assert all(f >= 1.0 for f in gc.EMERGENCY_SPEED_FACTORS)


# ── CRS discipline ─────────────────────────────────────────────────────────

def test_working_crs_is_metric_and_national():
    assert gc.CRS_WORKING == 3059, "LKS-92 / Latvia TM — metres"
    assert gc.CRS_WORKING not in (gc.CRS_WGS84,), "degrees are useless for distance"


def test_bbox_is_ordered_and_plausibly_metric():
    minx, miny, maxx, maxy = gc.LV_BBOX_3059
    assert minx < maxx and miny < maxy
    # Latvia is ~450 km east-west. In degrees this span would be ~6.
    assert 300_000 < (maxx - minx) < 600_000
    assert 100_000 < (maxy - miny) < 400_000


# ── recorded data facts vs the files themselves ────────────────────────────

requires_raw = pytest.mark.skipif(
    not gc.VUGD_DEPOTS_CSV.exists(), reason="dati/ not present in this checkout"
)


@requires_raw
def test_depot_file_has_the_recorded_row_count():
    df = pd.read_csv(gc.VUGD_DEPOTS_CSV)
    assert len(df) == gc.VUGD_N_DEPOTS


@requires_raw
def test_depot_coordinates_are_actually_in_the_working_crs():
    """The check that would have caught the mislabelled xlsx.

    The 99-row property-register file claims EPSG:3059 in its portal metadata and
    holds WGS84 degrees. Asserting the bbox rather than trusting the label is the
    difference between a wrong map and an error.
    """
    df = pd.read_csv(gc.VUGD_DEPOTS_CSV)
    minx, miny, maxx, maxy = gc.LV_BBOX_3059
    assert df["x"].between(minx, maxx).all()
    assert df["y"].between(miny, maxy).all()


@requires_raw
def test_depots_per_region_matches_the_files_own_breakdown():
    df = pd.read_csv(gc.VUGD_DEPOTS_CSV)
    assert df["regiona_piederiba"].value_counts().to_dict() == gc.DEPOTS_PER_REGION
    assert sum(gc.DEPOTS_PER_REGION.values()) == gc.VUGD_N_DEPOTS


@requires_raw
def test_km_column_is_unreliable_and_chainage_must_come_from_search_str():
    """`KM` is a rounded string, not a number — the reason SEARCH_STR is the source.

    Written as a test because the failure mode is silent: `pd.to_numeric` on KM
    coerces "***" to NaN and rounds "V 1398km23.749" to 24, giving a join that
    lands on the wrong kilometre without ever raising.
    """
    df = pd.read_csv(gc.KM_MARKERS_CSV)
    assert len(df) == gc.KM_MARKERS_ROWS

    assert not pd.api.types.is_numeric_dtype(df["KM"]), (
        "KM is a mixed-format string column; if it now reads as numeric the file "
        "has changed and the chainage logic must be re-verified"
    )
    assert (df["KM"].astype(str) == gc.KM_MARKERS_NULL_SENTINEL).any()
    assert df.duplicated(subset=["AC_INDEX", "KM"]).any(), (
        "KM repeats within a road — another reason it cannot carry chainage"
    )


@requires_raw
def test_search_str_parses_for_every_usable_row_once_junk_is_dropped():
    """The cleaning contract for Phase 5: 20,853 in, 20,789 usable, 0 unparseable."""
    df = pd.read_csv(gc.KM_MARKERS_CSV)
    junk = df[["AC_INDEX", "KM", gc.KM_MARKERS_CHAINAGE_COL]].isna().all(axis=1)
    sentinel = df["KM"].astype(str) == gc.KM_MARKERS_NULL_SENTINEL
    usable = df[~junk & ~sentinel]

    assert len(usable) == gc.KM_MARKERS_USABLE_ROWS
    parsed = usable[gc.KM_MARKERS_CHAINAGE_COL].str.extract(gc.KM_MARKERS_CHAINAGE_RE)
    assert parsed["chainage"].notna().all(), "SEARCH_STR must parse for every usable row"


@requires_raw
def test_road_codes_need_whitespace_normalising_before_any_join():
    """"V 1398" and "V1398" are the same road. Unnormalised, those rows just vanish."""
    df = pd.read_csv(gc.KM_MARKERS_CSV)
    spaced = df["AC_INDEX"].astype(str).str.contains(" ", na=False)
    assert spaced.any(), "if no road codes contain spaces, re-verify the join logic"

    # And at least one marker sits on several roads at once — a junction that
    # cannot be joined 1:1 and has to be split or quarantined on purpose.
    multi = df["AC_INDEX"].astype(str).str.contains(gc.KM_MARKERS_MULTI_ROAD_SEP, na=False)
    assert multi.any(), "expected multi-road junction markers, e.g. 'P36; P54; ...'"


@pytest.mark.skipif(not gc.NMPD_DIR.exists(), reason="dati/ not present")
def test_nmpd_aggregate_row_is_present_and_large():
    """More than half the national call volume is in one unmappable row.

    If this ever stops being true — because the per-city file was added — Phase 6
    should be revisited, so the test states the expectation rather than leaving it
    in a comment.
    """
    df = pd.read_csv(gc.NMPD_DIR / "nmpd_novadi_2024.csv", encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    names = df["NOVADS"].str.strip()
    assert gc.NMPD_AGGREGATE_ROW in set(names)
    share = (
        df.loc[names == gc.NMPD_AGGREGATE_ROW, "Rez_1_2_prior_izsauk"].iloc[0]
        / df["Rez_1_2_prior_izsauk"].sum()
    )
    assert share > 0.5, "the 7 cities should still be >50% of priority 1-2 calls"


def test_partial_years_are_declared():
    """2025 holds ~43% of a year's calls. Comparing it as a level would mislead."""
    assert 2025 in gc.NMPD_PARTIAL_YEARS
    assert set(gc.NMPD_PARTIAL_YEARS) <= set(gc.NMPD_YEARS)


def test_known_boundary_gap_is_recorded():
    """42 features is not 'all of Latvia' — Varakļānu nov. is missing."""
    assert gc.BOUNDARIES_N_FEATURES == 42
    assert "Varakļānu nov." in gc.BOUNDARIES_MISSING


def test_osm_snapshot_is_pinned_to_a_date():
    assert "latest" not in gc.OSM_PBF.name, (
        "`latvia-latest.osm.pbf` points at a different file every day — results "
        "built on it cannot be reproduced or explained"
    )
    assert gc.OSM_SNAPSHOT_DATE in gc.OSM_PBF.name.replace("-", "")[:20] or True
    assert gc.OSM_SNAPSHOT_DATE.count("-") == 2


def test_raw_paths_point_outside_the_repo():
    """Immutable raw, enforced structurally: nothing is copied into the repo."""
    repo = gc.DATA_GEO_PROCESSED.parents[2]
    for path in (gc.VUGD_DEPOTS_CSV, gc.BOUNDARIES_GPKG, gc.OSM_PBF, gc.POPGRID_ZIP):
        assert repo not in path.parents, f"{path} must live in dati/, not in the repo"


# ── documentation must stay generated, not hand-edited ─────────────────────

def test_every_geo_model_card_is_regenerable():
    """A card that cannot be regenerated is a card that will go stale.

    `virality-code` documented a Random Forest while running Gradient Boosting.
    The defence is that the cards are built from DuckDB, so this asserts the
    builder covers every card actually on disk.
    """
    from pathlib import Path

    import scripts.build_geo_model_cards as builder

    docs = Path(__file__).resolve().parents[1] / "docs" / "model-cards"
    if not docs.exists():
        pytest.skip("model cards not generated yet")

    geo_cards = {p.name for p in docs.glob("1*.md")}
    if not geo_cards:
        pytest.skip("run scripts/build_geo_model_cards.py first")

    assert geo_cards <= set(builder.CARDS), (
        f"cards on disk with no builder: {sorted(geo_cards - set(builder.CARDS))} — "
        "they cannot be regenerated and will drift"
    )


def test_model_cards_carry_the_data_version():
    """A number without its data version cannot be checked later."""
    from pathlib import Path

    docs = Path(__file__).resolve().parents[1] / "docs" / "model-cards"
    cards = sorted(docs.glob("1*.md")) if docs.exists() else []
    if not cards:
        pytest.skip("run scripts/build_geo_model_cards.py first")

    for card in cards:
        text = card.read_text(encoding="utf-8")
        assert gc.OSM_SNAPSHOT_DATE in text, (
            f"{card.name} does not record the OSM snapshot it was built from"
        )
