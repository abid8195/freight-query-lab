# freight-query-lab

A PostgreSQL 16 tuning lab on a synthetic freight platform: five realistic
queries, their execution plans read one by one, fixes applied one at a time,
then a Parquet/DuckDB warehouse with checks that prove it matches the source.

## The problem

A multi-tenant freight platform with ~2M consignments and ~10M tracking events,
created with primary and foreign keys and **no secondary indexes**. Customer
traffic is heavily skewed: customer 1 owns 18% of consignments and the top 10
own 48%. The five everyday queries take 0.15–2 s each. The goal is to find the
root cause of each from its plan, fix it, and measure what the fix costs.

## Schema

| table | rows | heap | notes |
|---|---:|---:|---|
| customers | 1,000 | 0.1 MB | `customer_id` = popularity rank (1 = biggest) |
| carriers | 50 | – | road / air / sea / rail / courier |
| consignments | 2,000,000 | 188 MB | customer, carrier, tracking_number, status, created_at, weight_kg, price |
| tracking_events | 9,913,806 | 758 MB | consignment_id, status, location, occurred_at (~5 per consignment) |
| invoices | 1,941,336 | 157 MB | one per delivered/exception consignment, `paid` / `issued` / `void` |

[sql/schema.sql](sql/schema.sql) has primary keys only. The foreign keys are in
[sql/constraints.sql](sql/constraints.sql) and are added *after* the COPY load,
because validating them once in bulk is far cheaper than checking row by row.
The data covers 2024‑10‑01 to a fixed "now" of 2026‑10‑01, with volume growing
over time, so the benchmarks are reproducible.

## How to run

Requirements: Docker Desktop and Python 3.12.

```bash
docker compose up -d --wait                     # Postgres 16 on localhost:5433 (freight/freight)
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # macOS/Linux: .venv/bin/pip
.venv/Scripts/python scripts/generate_data.py   # ~6 min here; --consignments 200000 for a quick run
.venv/Scripts/python scripts/run_tuning.py      # reset -> baseline -> fixes 01..06, ~15 min
.venv/Scripts/python scripts/export_parquet.py
.venv/Scripts/python scripts/duckdb_compare.py
.venv/Scripts/python scripts/dq_checks.py       # exits 1 on any mismatch
```

`run_tuning.py` resets to the PK/FK-only schema, so the whole study can be
rerun. You can also run the pieces separately: `benchmark.py --label X`,
`apply_fix.py <fix>`, `index_report.py`, `write_cost.py`, `compare.py`, and
`reset_tuning.py`. Set `FREIGHT_DSN` to point at another server.

**Method:** 1 warm-up run, then 10 timed runs per query (client-side, all rows
fetched). The median is reported, and EXPLAIN (ANALYZE, BUFFERS, SETTINGS) is
saved to `results/<label>/qN.plan.txt`. Config is mostly defaults
(`shared_buffers=512MB`, `work_mem=4MB`), see
[docker-compose.yml](docker-compose.yml).

## Results

All numbers come from one uninterrupted pass ([results/comparison.md](results/comparison.md)).
"Buffers" are 8 kB pages from the top node of the plan: *hit* means the page
was in shared buffers, *read* means it came from outside (the OS cache or disk).

| query | before | after | buffers before → after | root cause | fix |
|---|---:|---:|---|---|---|
| q1 customer's consignments, 3-month range, newest first, page 3 | 144 ms | 0.85 ms | 24k → 13 | Parallel seq scan of 2M rows to find 61k, then a top-N sort | `(customer_id, created_at, consignment_id)`: equality column, then the range/sort column, then the tie-breaker. The index is scanned **backward** and stops after 150 entries, with no sort. |
| q2 lookup by tracking_number | 147 ms | 0.71 ms | 24k → 4 | Seq scan of 2M rows to return 1 | Unique index, promoted to a `UNIQUE` constraint (it was a missing business rule too) |
| q3 latest event per consignment for one customer | 868 ms* | 84 ms | 116k (80k read) → 54k (0 read) | Hash join that seq-scans **all 9.9M events** for 13k consignments. Postgres doesn't index FK columns. | `tracking_events(consignment_id, occurred_at)`: nested loop with ~5 index entries per consignment, already in order |
| q4 monthly invoice totals per carrier, 12 months | 2,046 ms* | 526 ms | 47k + 45k temp → 20k, no temp | (1) the planner estimated **1.2M groups, actual 600**, so it sorted 1.2M rows by a text key and **spilled to disk**; (2) a 2M-row join just to get `carrier_id` | Copy `carrier_id` onto invoices and group by the integer id with a HashAggregate (1 MB, in memory), then join the 50 carrier names afterwards |
| q5 consignments in transit with no event for 5+ days | 540 ms | 230 ms | 116k (78k read) → 149k (0 read) | Same 9.9M-event seq scan, then a seq scan of 2M consignments for the 2.5% in transit | The q3 index (index-only scan), plus a **partial** index `WHERE status = 'in_transit'` with `INCLUDE` columns (2.4 MB) |

\* Wall-clock time on this laptop is noisy (see Limitations). In an earlier
identical baseline, q3 took 407 ms and q4 1,215 ms, so a fair reading is q3 ~5–10× and
q4 ~2–4×. The buffer columns don't depend on machine load.

### A fix that didn't help: index on `invoices(issued_at)` (step 04)

q4 filters on `issued_at`, so indexing it is the reflex. The 12-month window
matches **62% of invoices**. Fetching most of a table through an index costs a
random heap visit per row, so a sequential scan is cheaper, and the planner
kept choosing it. Before and after, the plan was identical, the buffers were
identical (47k + 45k temp), and the time didn't move (1,702 → 1,753 ms). The
index added 41.6 MB to store and maintain for nothing, and it was dropped in
step 05. Two other q4 ideas also failed in rolled-back experiments:
- **Raising `work_mem` to 64MB** removed the spill but made the query *slower* (1,376 → 1,603 ms). The spill files were in the OS cache anyway. The real cost was sorting 1.2M rows on a text key, not the disk.
- **Grouping by carrier_id without denormalizing** switched to a hash aggregate but lost parallelism, so it was slower.

Removing the join and the text sort is what worked.

### What the indexes cost

| | before | after (all fixes) |
|---|---:|---:|
| Secondary index storage | 0 MB | 438 MB (the events index alone is 298 MB, 39% of its table) |
| Insert 20k consignments | 286 ms | 450–527 ms (3 extra indexes; every test row is `in_transit`, so all of them hit the partial index too) |
| Insert 100k tracking events | 645 ms | 970–1,053 ms (1 extra index) |
| Insert 20k invoices | 212 ms | 372–402 ms (no new index, but an extra FK check on `carrier_id`; possibly partly noise) |

So reads got 2–200× faster, and writes got about 1.5–1.8× slower. For an
event-ingest table that trade is acceptable but not free. The 298 MB events
index is the one to watch. The partial index also changes `status` updates:
moving a row into or out of `in_transit` now touches an index, which rules out
HOT updates for those changes.

## Warehouse: Parquet + DuckDB

[scripts/export_parquet.py](scripts/export_parquet.py) streams each table out
of Postgres with `COPY` and writes hive-partitioned Parquet: `consignments/` by
`created_at` month and `invoices/` by `issued_at` month (24 partitions each,
131 MB total versus 345 MB of heap). Money stays exact `decimal(12,2)`. The
customers and carriers tables are exported too: the foreign-key checks need
them, and so do the carrier names.

The same monthly carrier totals query, run back to back on the same laptop
([results/duckdb_vs_postgres.md](results/duckdb_vs_postgres.md)):

| engine | median |
|---|---:|
| PostgreSQL 16, tuned and rewritten (no join) | 886 ms (526 ms in the tuning pass) |
| DuckDB over Parquet, *original* query including the 2M-row join | 201 ms |
| DuckDB + filter on the `month` partition column | 202 ms |

DuckDB is about 2.5–4.5× faster even though it still performs the join that
Postgres needed denormalization to avoid. It's a columnar engine that reads
only the columns the query uses, vectorized, on 12 threads. The explicit
partition filter gained nothing. The window covers half the partitions, and
because each file holds a single month, its min/max statistics on `issued_at`
probably already let DuckDB skip the other half. I didn't profile this to
confirm it. This
comparison isn't apples to apples. Postgres runs inside Docker's VM with 2
parallel workers per query, and DuckDB runs natively on the host.

## Data-quality checks

[scripts/dq_checks.py](scripts/dq_checks.py) compares the warehouse with
Postgres and **exits 1 with a banner** on any mismatch:

1. Row counts for all four tables
2. Exact decimal sums: price, weight, and invoice amount by status, plus count and sum **per month**, which catches rows in the wrong partition or missing partitions
3. Every row sits in the partition that matches its own timestamp
4. Primary keys are unique (catches a doubled export)
5. No orphaned foreign keys: consignments → customers and carriers, invoices → consignments and customers
6. The monthly carrier totals are identical in both engines (600 rows)

All 19 checks pass. To prove they can fail, I moved one invoices partition
(`month=2026-03`) out of the way and reran. 4 checks failed (the count, the
sums, the per-month totals, and the q4 result), with exit code 1.

## Limitations

- **Noisy timings.** This is a laptop running Postgres in a Docker VM. Queries
  that a tuning step didn't touch, with identical plans and buffers, still moved
  between 0.56× and 2.04× from one step to the next. Treat wall-clock changes
  under ~2× as unproven and compare buffers. A dedicated, idle machine would
  give tighter numbers.
- Every run is a **warm-cache** run, so it measures plan quality, not cold disk I/O.
- The data is synthetic. Event timing, statuses and skew are plausible, but
  the real correlations (seasonality, carrier lanes, retries) aren't modeled.
- The q4 fix is a **schema change plus a query rewrite**, not an index. The
  application now has to write `carrier_id` on every invoice (the FK keeps it
  valid but not *consistent* with the consignment's carrier; a trigger or a
  check job would).
- Benchmark queries use fixed parameters: one big customer for q1 and one
  mid-size customer for q3. Small tenants and other date ranges may get
  different plans.

## What I'd do next

- **Keyset pagination for q1:** `WHERE (created_at, consignment_id) < (...)` instead of `OFFSET`. Deep pages currently read and discard every earlier row.
- **Monthly rollup for q4:** a materialized view or a rollup table maintained on insert. 600 rows is about 1 ms instead of a 1.2M-row scan, at the cost of staleness or write-time work.
- **Partition `tracking_events` by month:** old months become cheap to detach and archive, the 298 MB index splits into small per-partition indexes, and vacuum work stays bounded.
- **Tenant sharding by `customer_id`** (for example with Citus), once one node's write throughput becomes the limit. Customer 1 alone is 18% of the volume, so sharding by hash would leave one hot shard. It would need a dedicated shard for the largest tenants, or a composite key.
- `pg_stat_statements` and `auto_explain` in a real environment, so tuning starts from the most expensive queries in production rather than five I picked.
