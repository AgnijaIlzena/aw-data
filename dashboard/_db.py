"""The dashboard's only route to data.

There is one connection helper, it is read-only, and nothing here computes
anything.
"""
from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from actionwise.config import DUCKDB_PATH


@st.cache_data(show_spinner="Reading DuckDB…")
def q(sql: str) -> pd.DataFrame:
    """Run a read-only query against the shared cache."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
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
