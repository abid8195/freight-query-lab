-- q3/q5: tracking_events.consignment_id is a foreign key, and Postgres does not
-- index FK columns automatically, so every "events for these consignments"
-- question read all ~10M rows. (consignment_id, occurred_at) serves both
-- "latest event per consignment" (q3) and "max(occurred_at) per consignment"
-- (q5) straight from the index in already-sorted order.
CREATE INDEX ix_tracking_events_consignment_time ON tracking_events (consignment_id, occurred_at);
