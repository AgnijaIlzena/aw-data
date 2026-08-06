"""Thin DuckDB accessor — the shared cache between pipeline, notebooks and dashboard.

The dashboard reads through here and never recomputes an index. That rule is
enforced by tests/test_dashboard_isolation.py.
"""
from pathlib import Path

import duckdb

from actionwise.config import DUCKDB_PATH


def get_connection(db_path: Path = DUCKDB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open (creating if needed) the project DuckDB file.

    Args:
        db_path: override the default location.
        read_only: open without write access — use from the dashboard so a
            stray query can never mutate the shared cache.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if read_only and not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist yet — run `python scripts/run_pipeline.py` first."
        )
    return duckdb.connect(str(db_path), read_only=read_only)


def write_table(df, table: str, con: duckdb.DuckDBPyConnection | None = None) -> int:
    """Replace `table` with the contents of `df`. Returns the row count written."""
    owns = con is None
    con = con or get_connection()
    try:
        con.register("_incoming", df)
        con.execute(f"DROP TABLE IF EXISTS {table}")
        con.execute(f"CREATE TABLE {table} AS SELECT * FROM _incoming")
        con.unregister("_incoming")
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        if owns:
            con.close()
