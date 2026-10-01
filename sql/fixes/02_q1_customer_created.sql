-- q1: equality on customer_id + range on created_at + ORDER BY created_at DESC.
-- Column order matters: equality column first, then the range/sort column, then
-- the tie-breaker. Postgres walks the index backwards inside customer 1's
-- slice and stops after LIMIT+OFFSET = 150 entries: no sort, no full scan.
CREATE INDEX ix_consignments_customer_created ON consignments (customer_id, created_at, consignment_id);
