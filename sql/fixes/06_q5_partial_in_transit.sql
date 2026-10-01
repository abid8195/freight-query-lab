-- q5: after fix 03 the event side is an index-only scan, but finding the ~49k
-- in-transit consignments still seq-scans all 2M rows (status has 6 values,
-- so a plain index on status is a poor fit for the common ones).
-- A partial index stores only rows WHERE status = 'in_transit' (~2.5% of the
-- table), and INCLUDE carries the other columns q5 returns so it's index-only.
-- Trade-off: every status change into or out of in_transit now touches this
-- index (and an indexed-column change rules out HOT updates).
CREATE INDEX ix_consignments_in_transit ON consignments (consignment_id)
    INCLUDE (tracking_number, customer_id, carrier_id)
    WHERE status = 'in_transit';
