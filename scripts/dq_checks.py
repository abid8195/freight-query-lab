"""Prove the Parquet warehouse matches PostgreSQL. Exit code 1 on any mismatch.

Checks:
  1. row counts per table
  2. exact decimal sums (price, weight, invoice amount), overall and per month
  3. every row sits in the partition that matches its own timestamp
  4. primary keys are unique in the warehouse (no duplicated export)
  5. no orphaned foreign keys inside the warehouse
  6. the monthly carrier totals query returns identical results in both engines
"""
import sys

from common import connect, duckdb_conn
from duckdb_compare import DUCK_SQL, Q4
from queries import resolve_sql

failures: list[str] = []


def check(name, pg_value, wh_value):
    ok = pg_value == wh_value
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        failures.append(name)
        show = lambda v: v if not isinstance(v, list) or len(v) < 6 else f"{len(v)} rows, first: {v[:3]}"
        print(f"         postgres : {show(pg_value)}\n         warehouse: {show(wh_value)}")


def main():
    duck = duckdb_conn()
    with connect() as pg:
        def both(pg_sql, wh_sql=None, params=None):
            return pg.execute(pg_sql, params).fetchall(), duck.execute(wh_sql or pg_sql, params).fetchall()

        print("1. row counts")
        for t in ("customers", "carriers", "consignments", "invoices"):
            check(f"count({t})", *both(f"SELECT count(*) FROM {t}"))

        print("2. sums")
        check("sum(consignments.price), sum(weight_kg)", *both("SELECT sum(price), sum(weight_kg) FROM consignments"))
        check("sum(invoices.amount) by status",
              *both("SELECT status, count(*), sum(amount) FROM invoices GROUP BY status ORDER BY status"))
        check("consignments count/sum(price) per month",
              pg.execute("SELECT to_char(created_at, 'YYYY-MM') m, count(*), sum(price) FROM consignments GROUP BY m ORDER BY m").fetchall(),
              duck.execute("SELECT month, count(*), sum(price) FROM consignments GROUP BY month ORDER BY month").fetchall())
        check("invoices count/sum(amount) per month",
              pg.execute("SELECT to_char(issued_at, 'YYYY-MM') m, count(*), sum(amount) FROM invoices GROUP BY m ORDER BY m").fetchall(),
              duck.execute("SELECT month, count(*), sum(amount) FROM invoices GROUP BY month ORDER BY month").fetchall())

        print("3. partition placement")
        for t, col in (("consignments", "created_at"), ("invoices", "issued_at")):
            check(f"{t} rows in wrong month partition", 0,
                  duck.execute(f"SELECT count(*) FROM {t} WHERE strftime({col}, '%Y-%m') <> month").fetchone()[0])

        print("4. primary key uniqueness in warehouse")
        for t, key in (("consignments", "consignment_id"), ("invoices", "invoice_id"),
                       ("customers", "customer_id"), ("carriers", "carrier_id")):
            check(f"duplicate {t}.{key}", 0,
                  duck.execute(f"SELECT count(*) - count(DISTINCT {key}) FROM {t}").fetchone()[0])

        print("5. orphaned foreign keys in warehouse")
        for child, col, parent, pk in (
            ("consignments", "customer_id", "customers", "customer_id"),
            ("consignments", "carrier_id", "carriers", "carrier_id"),
            ("invoices", "consignment_id", "consignments", "consignment_id"),
            ("invoices", "customer_id", "customers", "customer_id"),
        ):
            check(f"{child}.{col} -> {parent}", 0, duck.execute(
                f"SELECT count(*) FROM {child} x ANTI JOIN {parent} p ON p.{pk} = x.{col}").fetchone()[0])

        print("6. monthly carrier totals identical in both engines")
        pg_rows, wh_rows = both(resolve_sql(pg, Q4)[0], DUCK_SQL.format(extra=""), Q4["params"])
        check(f"q4 result ({len(pg_rows)} rows)", pg_rows, wh_rows)

    if failures:
        print(f"\n{'!' * 60}\nDATA QUALITY FAILED: {len(failures)} check(s)\n" + "\n".join(f"  - {f}" for f in failures)
              + f"\n{'!' * 60}", file=sys.stderr)
        sys.exit(1)
    print("\nAll data-quality checks passed.")


if __name__ == "__main__":
    main()
