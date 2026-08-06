"""The Phase 2 gate, as a test.

Keeping this in the suite means a future change to the cleaner cannot quietly
break agreement with the published figures. If someone "fixes" the weighting or
the reversal and these drift, the suite says so.
"""
import pandas as pd
import pytest

from actionwise.config import DATA_PROCESSED, SANITY_TOLERANCE
from actionwise.sanity import run_gate

PROCESSED = DATA_PROCESSED / "eb547_features.parquet"

pytestmark = pytest.mark.skipif(
    not PROCESSED.exists(),
    reason="run `python scripts/run_pipeline.py` first to build the processed table",
)


@pytest.fixture(scope="module")
def gate() -> pd.DataFrame:
    return run_gate(pd.read_parquet(PROCESSED))


def test_every_published_figure_reproduces(gate: pd.DataFrame):
    failures = gate[~gate["pass"]]
    assert failures.empty, (
        "pipeline no longer reproduces DG ECHO's published figures:\n"
        f"{failures.to_string(index=False)}"
    )


def test_gate_covers_both_scale_families(gate: pd.DataFrame):
    """Guard against the gate being weakened to only easy checks."""
    checks = " ".join(gate["check"])
    assert "qc8_2" in checks, "agreement-scale check missing"
    assert "qc7" in checks, "horizon-scale check missing"
    assert "Slovenia" in checks and "Malta" in checks, "country-spread check missing"


def test_deltas_are_tight(gate: pd.DataFrame):
    """A pass at the tolerance boundary is a warning sign, not a success."""
    worst = gate["delta"].abs().max()
    assert worst <= SANITY_TOLERANCE, f"worst delta {worst:.4f} exceeds {SANITY_TOLERANCE}"
