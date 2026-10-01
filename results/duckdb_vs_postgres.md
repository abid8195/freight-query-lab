| engine | median ms | vs PostgreSQL |
|---|---:|---:|
| PostgreSQL 16 (Docker, 2 parallel workers/gather, rewritten q4) | 885.8 | 1.0x |
| DuckDB over Parquet (12 threads) | 201.4 | 4.4x faster |
| DuckDB + partition filter on `month` | 202.3 | 4.4x faster |

PostgreSQL secondary indexes at the time of the run: consignments_tracking_number_key, ix_consignments_customer_created, ix_consignments_in_transit, ix_tracking_events_consignment_time
