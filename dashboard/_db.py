"""The dashboard's only route to data.

There is one connection helper, it is read-only, and nothing here computes
anything.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from actionwise.config import DUCKDB_PATH

# En local, la base complete produite par le pipeline. Sur un hebergeur, seule
# la base publique est versionnee : meme schema, sans les microdonnees.
DB_PATH = DUCKDB_PATH
if not DB_PATH.exists():
    _public = DUCKDB_PATH.with_name("actionwise-public.duckdb")
    if _public.exists():
        DB_PATH = _public


@st.cache_data(show_spinner="Reading DuckDB…")
def q(sql: str) -> pd.DataFrame:
    """Run a read-only query against the shared cache."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


@st.cache_data
def available_tables() -> set[str]:
    return set(q("SELECT table_name FROM duckdb_tables()")["table_name"])


def require(*tables: str) -> bool:
    """Warn and return False when a page's inputs have not been built yet."""
    missing = [t for t in tables if t not in available_tables()]
    if missing:
        st.warning(
            f"Missing table(s): {', '.join(missing)}. Run the pipeline scripts first — "
            "see the README."
        )
        return False
    return True


def pct(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.1%}"


def minutes(v: float) -> str:
    return "—" if pd.isna(v) else f"{v:.1f} min"
