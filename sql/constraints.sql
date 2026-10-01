-- Run after the bulk load: validating FKs once in bulk is far cheaper than
-- checking them row by row during COPY. Note Postgres does NOT index FK columns.
ALTER TABLE consignments
    ADD CONSTRAINT consignments_customer_fk FOREIGN KEY (customer_id) REFERENCES customers (customer_id),
    ADD CONSTRAINT consignments_carrier_fk  FOREIGN KEY (carrier_id)  REFERENCES carriers (carrier_id);

ALTER TABLE tracking_events
    ADD CONSTRAINT tracking_events_consignment_fk FOREIGN KEY (consignment_id) REFERENCES consignments (consignment_id);

ALTER TABLE invoices
    ADD CONSTRAINT invoices_consignment_fk FOREIGN KEY (consignment_id) REFERENCES consignments (consignment_id),
    ADD CONSTRAINT invoices_customer_fk    FOREIGN KEY (customer_id)    REFERENCES customers (customer_id);
