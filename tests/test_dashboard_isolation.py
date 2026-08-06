"""The dashboard must read the pipeline's output, never re-derive it.

In `virality-code` the Streamlit app loaded a spreadsheet and recomputed every
index in memory. The consequences were that 3.9 GB of pipeline output was never
read by anything, and that two definitions of the same index drifted apart
without anyone noticing. This test makes that failure mode impossible here.
"""
import ast
from pathlib import Path

import pytest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"

# Modules that define or compute an index. The dashboard may not import them.
FORBIDDEN_PREFIXES = ("actionwise.indices", "actionwise.models", "actionwise.data")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def dashboard_files() -> list[Path]:
    return sorted(DASHBOARD.rglob("*.py"))


def test_dashboard_exists():
    assert dashboard_files(), "no dashboard sources found"


@pytest.mark.parametrize("path", dashboard_files(), ids=lambda p: p.name)
def test_dashboard_does_not_import_index_or_model_code(path: Path):
    offending = sorted(
        m for m in _imported_modules(path) if m.startswith(FORBIDDEN_PREFIXES)
    )
    assert not offending, (
        f"{path.name} imports {offending}. The dashboard must read computed results from "
        "DuckDB, not recompute them — otherwise two definitions of the same index can drift."
    )


@pytest.mark.parametrize("path", dashboard_files(), ids=lambda p: p.name)
def test_dashboard_does_not_read_raw_or_processed_files(path: Path):
    """Reading parquet or the .sav directly would bypass the shared cache."""
    source = path.read_text(encoding="utf-8")
    for banned in ("read_parquet", "read_sav", "read_excel", "read_csv"):
        assert banned not in source, (
            f"{path.name} calls {banned}. Query DuckDB instead so the dashboard and the "
            "pipeline can never disagree about what a number means."
        )


def test_dashboard_opens_duckdb_read_only():
    app = DASHBOARD / "app.py"
    assert "read_only=True" in app.read_text(encoding="utf-8"), (
        "the dashboard should open DuckDB read-only so a stray query cannot mutate the "
        "shared cache"
    )
