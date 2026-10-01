"""Undo every tuning step: back to primary + foreign keys only.

Drops all ix_* indexes and the tracking-number unique constraint, and removes
the denormalised invoices.carrier_id (VACUUM FULL so the table is rewritten
to its original width).
"""
from common import connect

with connect(autocommit=True) as conn:
    conn.execute("ALTER TABLE consignments DROP CONSTRAINT IF EXISTS consignments_tracking_number_key")
    for (name,) in conn.execute(r"SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname LIKE 'ix\_%'").fetchall():
        conn.execute(f"DROP INDEX {name}")
        print(f"dropped index {name}")
    has_carrier = conn.execute("""SELECT EXISTS (SELECT 1 FROM information_schema.columns
        WHERE table_name = 'invoices' AND column_name = 'carrier_id')""").fetchone()[0]
    if has_carrier:
        conn.execute("ALTER TABLE invoices DROP COLUMN carrier_id")
        conn.execute("VACUUM FULL invoices")
        print("removed invoices.carrier_id")
    conn.execute("VACUUM ANALYZE")
print("reset to baseline schema")
