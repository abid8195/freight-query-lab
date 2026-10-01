-- q2: tracking-number lookup did a parallel seq scan of 2M rows to return 1.
-- A unique B-tree turns it into ~4 page reads (root -> leaf -> heap), and the
-- uniqueness is a real business rule we were missing anyway.
CREATE UNIQUE INDEX ix_consignments_tracking_number ON consignments (tracking_number);
ALTER TABLE consignments ADD CONSTRAINT consignments_tracking_number_key UNIQUE USING INDEX ix_consignments_tracking_number;
