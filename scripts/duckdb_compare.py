"""Monthly carrier totals (benchmark query q4): PostgreSQL vs DuckDB over Parquet.

Both engines run the same query 10 times (after a warm-up) in this script, on
the same machine, back to back. DuckDB is also run a second time with an extra
filter on the hive `month` column, which lets it skip whole partitions.
Writes results/duckdb_vs_postgres.md.
"""
import statistics
import time

from common import ROOT, connect, duckdb_conn
from queries import QUERIES, resolve_sql

Q4 = next(q for q in QUERIES if q["id"] == "q4")
P = Q4["params"]

DUCK_SQL = """
    SELECT ca.name AS carrier, date_trunc('month', i.issued_at) AS month,
           count(*) AS invoices, sum(i.amount) AS total
    FROM invoices i
    JOIN consignments c ON c.consignment_id = i.consignment_id
    JOIN carriers ca    ON ca.carrier_id = c.carrier_id
    WHERE i.status <> 'void'
      AND i.issued_at >= $date_from AND i.issued_at < $date_to
      {extra}
    GROUP BY ALL
    ORDER BY carrier, month
"""
PRUNED = "AND i.month >= strftime($date_from, '%Y-%m') AND i.month < strftime($date_to + INTERVAL 1 MONTH, '%Y-%m')"


def bench(fn, runs=10):
    fn()
    times = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t) * 1000)
    return statistics.median(times)


def main():
    duck = duckdb_conn()
    threads = duck.execute("SELECT current_setting('threads')").fetchone()[0]
    with connect(autocommit=True) as pg:
        pg_sql, rewritten = resolve_sql(pg, Q4)
        pg_ms = bench(lambda: pg.execute(pg_sql, P).fetchall())
        pg_workers = pg.execute("SHOW max_parallel_workers_per_gather").fetchone()[0]
        pg_indexes = [r[0] for r in pg.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname NOT LIKE '%pkey'").fetchall()]
    plain_ms = bench(lambda: duck.execute(DUCK_SQL.format(extra=""), P).fetchall())
    pruned_ms = bench(lambda: duck.execute(DUCK_SQL.format(extra=PRUNED), P).fetchall())

    lines = [
        "| engine | median ms | vs PostgreSQL |",
        "|---|---:|---:|",
        f"| PostgreSQL 16 (Docker, {pg_workers} parallel workers/gather{', rewritten q4' if rewritten else ''}) | {pg_ms:,.1f} | 1.0x |",
        f"| DuckDB over Parquet ({threads} threads) | {plain_ms:,.1f} | {pg_ms / plain_ms:.1f}x faster |",
        f"| DuckDB + partition filter on `month` | {pruned_ms:,.1f} | {pg_ms / pruned_ms:.1f}x faster |",
        "",
        f"PostgreSQL secondary indexes at the time of the run: {', '.join(pg_indexes) or 'none'}",
    ]
    (ROOT / "results" / "duckdb_vs_postgres.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
