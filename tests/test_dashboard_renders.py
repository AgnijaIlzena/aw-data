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
    "Resilience horizon",
    "Item bank",
    "Latvia vs Europe",
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
