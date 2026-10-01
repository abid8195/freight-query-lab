-- q4, attempt 2: remove the work instead of making it faster.
-- Root cause 1: carrier_id lives only on consignments, so every run hash-joins
-- 1.2M invoices against all 2M consignments (hash spilling into 16 batches).
-- An invoice's carrier never changes after issue, so copying it onto the
-- invoice is a safe denormalisation (FK keeps it honest). Rebuilt with CREATE
-- TABLE AS rather than ADD COLUMN + UPDATE, which would rewrite every row and
-- leave the table 2x bloated until a VACUUM FULL.
-- Root cause 2: the planner estimated 1.2M groups (actual: 600), so it chose a
-- sort-based aggregate over a text key (carrier name) that spills to disk.
-- The rewritten query (queries.py, q4 "rewrite") groups by integer carrier_id
-- with a HashAggregate and joins the 50 carrier names after aggregating.
CREATE TABLE invoices_new AS
    SELECT i.invoice_id, i.consignment_id, i.customer_id, c.carrier_id,
           i.issued_at, i.due_at, i.amount, i.status
    FROM invoices i JOIN consignments c ON c.consignment_id = i.consignment_id
    ORDER BY i.invoice_id;
DROP TABLE invoices;
ALTER TABLE invoices_new RENAME TO invoices;
ALTER TABLE invoices
    ALTER COLUMN invoice_id SET NOT NULL, ALTER COLUMN consignment_id SET NOT NULL,
    ALTER COLUMN customer_id SET NOT NULL, ALTER COLUMN carrier_id SET NOT NULL,
    ALTER COLUMN issued_at SET NOT NULL, ALTER COLUMN due_at SET NOT NULL,
    ALTER COLUMN amount SET NOT NULL, ALTER COLUMN status SET NOT NULL,
    ADD PRIMARY KEY (invoice_id),
    ADD CONSTRAINT invoices_status_check CHECK (status IN ('issued', 'paid', 'void')),
    ADD CONSTRAINT invoices_consignment_fk FOREIGN KEY (consignment_id) REFERENCES consignments (consignment_id),
    ADD CONSTRAINT invoices_customer_fk FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    ADD CONSTRAINT invoices_carrier_fk FOREIGN KEY (carrier_id) REFERENCES carriers (carrier_id);
-- Fix 04's index didn't help; it went away with the old table and isn't recreated.
VACUUM ANALYZE invoices;
