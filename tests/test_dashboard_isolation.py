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
# Both projects, on the same rule: project #2 adds a whole second pipeline, and
# an unguarded dashboard would be free to recompute travel times in the browser
# and drift from the tables the scripts wrote.
FORBIDDEN_PREFIXES = (
    "actionwise.indices", "actionwise.models", "actionwise.data",
    "actionwise_geo.indices", "actionwise_geo.models", "actionwise_geo.data",
    "actionwise_geo.network", "actionwise_geo.validate",
)


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


def test_project_two_pages_are_imported_lazily_and_conditionally():
    """Removing project #2 must not half-break the shared app.

    `geo_pages` may only be imported from inside a function guarded by a table
    check. A module-level import would make `app.py` fail outright the moment
    `actionwise_geo` or the geo extra is removed — the same reasoning that keeps
    the FEMA phase deletable.
    """
    app = DASHBOARD / "app.py"
    tree = ast.parse(app.read_text(encoding="utf-8"), filename=str(app))

    top_level = {
        alias.name
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in getattr(node, "names", [])
    } | {
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("geo_pages" in str(name) for name in top_level), (
        "geo_pages must not be imported at module level — app.py would then fail "
        "to start once project #2 is removed"
    )

    imports_geo = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
        and "geo_pages" in node.module
    ]
    assert imports_geo, "app.py never registers the project #2 pages"

    guarded = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.If)
        and any(child in imports_geo for child in ast.walk(node))
    ]
    assert guarded, "the geo_pages import must sit inside a conditional"


def test_dashboard_opens_duckdb_read_only():
    """Every connection the dashboard opens must be read-only.

    Asserted against wherever `duckdb.connect` actually appears rather than
    against one named file: the accessor moved to `_db.py` when project #2's
    pages needed it too, and a test pinned to `app.py` would have gone green
    while checking nothing.
    """
    opens = [
        path for path in dashboard_files()
        if "duckdb.connect" in path.read_text(encoding="utf-8")
    ]
    assert opens, "no DuckDB connection found anywhere in the dashboard"

    for path in opens:
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "duckdb.connect" in line:
                assert "read_only=True" in line, (
                    f"{path.name} opens DuckDB writable: {line.strip()!r}. A stray "
                    "query must not be able to mutate the shared cache."
                )
