"""Shared settings for all scripts."""
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
DSN = os.environ.get("FREIGHT_DSN", "postgresql://freight:freight@localhost:5433/freight")

# The data is generated relative to a fixed "now" so benchmarks are reproducible.
AS_OF = datetime(2026, 10, 1, tzinfo=timezone.utc)
HISTORY_START = datetime(2024, 10, 1, tzinfo=timezone.utc)

TRACKING_MULTIPLIER = 2654435761  # odd, not divisible by 5 -> bijective mod 10**10


def tracking_number(consignment_id: int) -> str:
    return f"FQ{(consignment_id * TRACKING_MULTIPLIER) % 10**10:010d}"


def connect(**kwargs) -> psycopg.Connection:
    # UTC everywhere so date_trunc(month) agrees between Postgres and DuckDB.
    return psycopg.connect(DSN, options="-c TimeZone=UTC", **kwargs)


WAREHOUSE = ROOT / "warehouse"


def duckdb_conn():
    import duckdb

    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    for name, path in {
        "consignments": "consignments/*/*.parquet",
        "invoices": "invoices/*/*.parquet",
        "customers": "customers.parquet",
        "carriers": "carriers.parquet",
    }.items():
        hive = ", hive_partitioning = true" if "*" in path else ""
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{(WAREHOUSE / path).as_posix()}'{hive})")
    return con
