"""ActionWise project #2 — Time-to-Help.

Modelled travel time from Latvia's 87 VUGD fire-and-rescue depots across the real
road network, weighted by where people actually live, and scored against the
arrival times set in MK noteikumi Nr. 297.

A sibling of `actionwise`, not a subpackage of it: this is a peer deliverable, and
the two communicate through the shared DuckDB file rather than through imports.
Project #1 must never import from here — enforced by tests/test_geo_isolation.py.

Geospatial dependencies are an optional extra:

    pip install -e ".[geo]"

so that a broken wheel in the geo stack can never stop `run_pipeline.py` or the
survey test suite.
"""
