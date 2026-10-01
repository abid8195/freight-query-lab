"""Export the warehouse tables to Parquet.

consignments -> warehouse/consignments/month=YYYY-MM/  (by created_at)
invoices     -> warehouse/invoices/month=YYYY-MM/      (by issued_at)
customers, carriers -> one file each (small dimensions, needed for FK checks
and for carrier names in the monthly totals query).

Each table is streamed out of Postgres once with COPY TO STDOUT, parsed by
pyarrow with explicit types (numeric stays exact decimal), and written as a
hive-partitioned dataset.
"""
import shutil
import tempfile
import time

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from common import WAREHOUSE, connect

TS = pa.timestamp("us")
MONEY = pa.decimal128(12, 2)

TABLES = {
    "consignments": ("created_at", {
        "consignment_id": pa.int64(), "customer_id": pa.int32(), "carrier_id": pa.int32(),
        "tracking_number": pa.string(), "status": pa.string(), "created_at": TS,
        "weight_kg": pa.decimal128(10, 2), "price": MONEY,
    }),
    "invoices": ("issued_at", {
        "invoice_id": pa.int64(), "consignment_id": pa.int64(), "customer_id": pa.int32(),
        "issued_at": TS, "due_at": TS, "amount": MONEY, "status": pa.string(),
    }),
    "customers": (None, {"customer_id": pa.int32(), "name": pa.string(), "country": pa.string(), "created_at": TS}),
    "carriers": (None, {"carrier_id": pa.int32(), "name": pa.string(), "mode": pa.string()}),
}


def fetch(conn, table, schema, tmpdir) -> pa.Table:
    # Sessions are UTC (see common.connect), so timestamptz text is UTC; strip the
    # offset and re-attach UTC on the Arrow side.
    cols = ", ".join(f"{c} AT TIME ZONE 'UTC' AS {c}" if t == TS else c for c, t in schema.items())
    path = f"{tmpdir}/{table}.csv"
    with open(path, "wb") as f, conn.cursor() as cur:
        with cur.copy(f"COPY (SELECT {cols} FROM {table}) TO STDOUT (FORMAT csv)") as copy:
            for chunk in copy:
                f.write(chunk)
    tbl = pacsv.read_csv(
        path,
        read_options=pacsv.ReadOptions(column_names=list(schema)),
        convert_options=pacsv.ConvertOptions(column_types=schema, strings_can_be_null=False),
    )
    utc = pa.timestamp("us", tz="UTC")
    for i, field in enumerate(tbl.schema):
        if field.type == TS:
            tbl = tbl.set_column(i, field.name, tbl.column(i).cast(utc))
    return tbl


def main():
    t0 = time.perf_counter()
    if WAREHOUSE.exists():
        shutil.rmtree(WAREHOUSE)
    WAREHOUSE.mkdir()
    with connect() as conn, tempfile.TemporaryDirectory() as tmpdir:
        for table, (partition_col, schema) in TABLES.items():
            tbl = fetch(conn, table, schema, tmpdir)
            if partition_col is None:
                pq.write_table(tbl, WAREHOUSE / f"{table}.parquet")
            else:
                # strftime on the naive (UTC) values: avoids needing a tz database on Windows.
                month = pc.strftime(tbl[partition_col].cast(TS), format="%Y-%m")
                tbl = tbl.append_column("month", month)
                ds.write_dataset(
                    tbl, WAREHOUSE / table, format="parquet",
                    partitioning=ds.partitioning(pa.schema([("month", pa.string())]), flavor="hive"),
                    basename_template="part-{i}.parquet",
                )
            print(f"{table:13} {tbl.num_rows:>10,} rows  ({time.perf_counter() - t0:5.1f}s)", flush=True)
    size = sum(p.stat().st_size for p in WAREHOUSE.rglob("*.parquet"))
    print(f"warehouse: {size / 2**20:,.1f} MB in {WAREHOUSE}")


if __name__ == "__main__":
    main()
