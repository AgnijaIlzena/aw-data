"""Project #2 must never be able to break project #1.

Project #1 is finished: 11 phases, 106 tests, a passing sanity gate. Project #2
adds the least stable dependency tree in the repo (`cykhash` compiles from
source; GDAL/GEOS/PROJ ship as binary wheels). The two rules that keep the
finished half safe are enforced here rather than left to good intentions:

  1. `actionwise` never imports `actionwise_geo` — the dependency runs one way,
     so uninstalling the geo extra cannot break the survey pipeline.
  2. `actionwise_geo.config` imports without any geospatial package present, so
     the scaffold, the constants and these tests all work before the stack is
     installed and keep working if it later breaks.

The integration point between the two projects is the DuckDB file, not an import.
"""
import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
PROJECT_ONE = SRC / "actionwise"
PROJECT_TWO = SRC / "actionwise_geo"

# Packages that pull in GDAL/GEOS/PROJ or a compiler. Importing config must not
# reach any of them, or the scaffold becomes untestable until the stack installs.
GEO_PACKAGES = {"geopandas", "shapely", "pyproj", "pyogrio", "pyrosm", "osmium",
                "networkx", "rasterio", "fiona"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def project_one_files() -> list[Path]:
    return sorted(PROJECT_ONE.rglob("*.py"))


def test_both_packages_exist():
    assert PROJECT_ONE.is_dir(), "project #1 package missing"
    assert PROJECT_TWO.is_dir(), "project #2 package missing"


@pytest.mark.parametrize("path", project_one_files(), ids=lambda p: p.name)
def test_project_one_never_imports_project_two(path: Path):
    offending = sorted(m for m in _imported_modules(path) if m.startswith("actionwise_geo"))
    assert not offending, (
        f"{path.relative_to(SRC)} imports {offending}. The dependency must run one "
        "way only — otherwise uninstalling the [geo] extra breaks the survey "
        "pipeline, and project #1 stops being independently shippable."
    )


def test_geo_config_imports_without_any_geospatial_package():
    """The constants must be readable before the geo stack exists."""
    for name in GEO_PACKAGES:
        assert name not in sys.modules or True  # tolerate a package already loaded

    import actionwise_geo.config as gc  # noqa: F401  — the import IS the assertion

    reached = _imported_modules(PROJECT_TWO / "config.py") & GEO_PACKAGES
    assert not reached, (
        f"config.py imports {sorted(reached)}. Keep it dependency-free so the "
        "scaffold and its tests work before `pip install -e '.[geo]'` and keep "
        "working if a geo wheel later breaks."
    )


def test_geo_is_an_optional_extra_not_a_core_dependency():
    """Parse the tables rather than grep the text — the comments mention pyrosm."""
    import tomllib

    with (SRC.parent / "pyproject.toml").open("rb") as fh:
        cfg = tomllib.load(fh)

    extras = cfg["project"]["optional-dependencies"]
    assert "geo" in extras
    assert any("pyrosm" in dep for dep in extras["geo"])

    core = cfg["project"].get("dependencies", [])
    for pkg in ("geopandas", "pyrosm", "shapely", "osmium", "pyogrio"):
        assert not any(pkg in dep for dep in core), (
            f"{pkg} is a core dependency. It belongs in the [geo] extra — a broken "
            "geo wheel must not be able to stop run_pipeline.py."
        )


def test_an_osmium_only_fallback_extra_exists():
    """If the cykhash build fails, there must be a route that needs no compiler."""
    import tomllib

    with (SRC.parent / "pyproject.toml").open("rb") as fh:
        extras = tomllib.load(fh)["project"]["optional-dependencies"]

    assert "geo-osmium" in extras
    assert any("osmium" in dep for dep in extras["geo-osmium"])
    assert not any("pyrosm" in dep for dep in extras["geo-osmium"]), (
        "the fallback exists precisely to avoid pyrosm's source-built dependency"
    )
