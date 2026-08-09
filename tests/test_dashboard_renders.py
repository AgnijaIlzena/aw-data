"""Every dashboard page must render without raising.

Streamlit renders client-side, so a page that throws still returns HTTP 200 — the
server is fine, the page is blank. `AppTest` runs the script headlessly and
surfaces exceptions, which is the only way to know the dashboard actually works
short of opening it.

Skipped when the DuckDB file has not been built yet, so a fresh clone can still
run the suite.
"""
from pathlib import Path

import pytest

from actionwise.config import DUCKDB_PATH

# AppTest resolves relative paths against the *calling* file, so pass an absolute one.
APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
PAGES = [
    "Overview",
    "The gap",
    "What predicts the gap",
    "Resilience horizon",
    "Item bank",
    "Country vs Europe",
    "Composite (live weights)",
    "Method & limitations",
]

pytestmark = pytest.mark.skipif(
    not DUCKDB_PATH.exists(),
    reason="run the pipeline scripts first to build data/db/actionwise.duckdb",
)


def _run(page: str | None = None, timeout: int = 120):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=timeout)
    at.run()
    if page is not None and at.radio:
        at.radio[0].set_value(page).run()
    return at


def test_app_starts_without_exception():
    at = _run()
    assert not at.exception, [str(e) for e in at.exception]


@pytest.mark.parametrize("page", PAGES)
def test_each_page_renders(page: str):
    at = _run(page)
    assert not at.exception, f"{page} raised: {[str(e) for e in at.exception]}"


def test_overview_shows_the_headline_metrics():
    at = _run("Overview")
    labels = " ".join(m.label for m in at.metric)
    assert "Aware but hasn't acted" in labels
    assert "Conversion rate" in labels


def test_composite_sliders_change_the_ranking():
    """The live-weights page is the oral-defence demo — the sliders must do something."""
    at = _run("Composite (live weights)")
    assert len(at.slider) >= 3, "expected one slider per index"

    baseline = at.metric[1].value          # Latvia's composite score
    at.slider[0].set_value(1.0).run()      # all weight on PRI
    at.slider[1].set_value(0.0).run()
    at.slider[2].set_value(0.0).run()
    assert not at.exception, [str(e) for e in at.exception]
    assert at.metric[1].value != baseline, "re-weighting did not change the score"


def test_zero_weights_are_handled_not_crashed():
    at = _run("Composite (live weights)")
    for i in range(3):
        at.slider[i].set_value(0.0)
    at.run()
    assert not at.exception
    assert any("at least one weight" in w.value.lower() for w in at.warning)


# ── project #2 pages, registered conditionally ─────────────────────────────

GEO_PAGES = [
    "Time-to-Help",
    "Legal coverage",
    "Preparedness × Proximity",
    "Traffic",
    "Validation",
    "Method — Time-to-Help",
]


def _geo_available() -> bool:
    import duckdb

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        names = con.execute("SELECT table_name FROM duckdb_tables()").fetchdf()
    finally:
        con.close()
    return any(str(n).startswith("geo_") for n in names["table_name"])


needs_geo = pytest.mark.skipif(
    not DUCKDB_PATH.exists() or not _geo_available(),
    reason="project #2 tables not built — run scripts/run_geo_*.py",
)


@needs_geo
@pytest.mark.parametrize("page", GEO_PAGES)
def test_each_geo_page_renders(page: str):
    at = _run(page)
    assert not at.exception, f"{page} raised: {[str(e) for e in at.exception]}"


@needs_geo
def test_geo_pages_are_registered_alongside_project_one():
    """Both projects share one app; neither may displace the other."""
    at = _run()
    listed = set(at.radio[0].options)
    assert set(PAGES) <= listed, "project #1's pages must survive"
    assert set(GEO_PAGES) <= listed, "project #2's pages must appear"


@needs_geo
def test_the_matrix_page_states_the_axes_run_opposite_ways():
    """The finding inverts the project's original pitch — it must not be quiet."""
    at = _run("Preparedness × Proximity")
    shown = " ".join(e.value for e in at.error) + " ".join(c.value for c in at.caption)
    assert "opposite" in shown.lower()


@needs_geo
def test_the_validation_page_declares_the_null_result():
    at = _run("Validation")
    text = " ".join(w.value for w in at.warning)
    assert "null" in text.lower(), "a null result must be stated, not omitted"


def test_drivers_page_states_the_capability_vs_information_ranking():
    """The one number in this dashboard most likely to be quoted at the defence."""
    at = _run("What predicts the gap")
    assert not at.exception
    shown = " ".join(i.value for i in at.info)
    assert "capability" in shown.lower() and "ranks" in shown.lower()


def test_drivers_page_shows_the_holdout_metrics():
    """Every number here must be beside its baseline — a number alone is not a result."""
    at = _run("What predicts the gap")
    labels = " ".join(m.label for m in at.metric)
    assert "Full model" in labels
    assert "Demographics only" in labels
    assert "Mean predictor" in labels


def test_country_page_serves_every_focus_country():
    """Latvia and France must both render, from the same generalised page.

    The page was hardcoded to Latvia; adding France by copy-paste would have left
    two versions to drift apart. This asserts one page serves both.
    """
    from actionwise.config import COUNTRY_NAMES, FOCUS_COUNTRIES

    at = _run("Country vs Europe")
    assert not at.exception

    country = [r for r in at.radio if r.label == "Country"]
    assert country, "no country selector on the page"
    assert set(country[0].options) == {COUNTRY_NAMES[c] for c in FOCUS_COUNTRIES}

    for iso in FOCUS_COUNTRIES:
        at = _run("Country vs Europe")
        [r for r in at.radio if r.label == "Country"][0].set_value(iso).run()
        assert not at.exception, f"{iso} raised: {[str(e) for e in at.exception]}"
        labels = " ".join(m.label for m in at.metric)
        assert COUNTRY_NAMES[iso] in labels, f"{iso} metrics not shown"
