| table | table MB | index | index MB | definition |
|---|---:|---|---:|---|
| carriers | 0.0 | carriers_pkey | 0.0 | `btree (carrier_id)` |
| consignments | 188.2 | consignments_pkey | 43.7 | `btree (consignment_id)` |
| consignments | 188.2 | consignments_tracking_number_key | 60.2 | `btree (tracking_number)` |
| consignments | 188.2 | ix_consignments_customer_created | 77.4 | `btree (customer_id, created_at, consignment_id)` |
| consignments | 188.2 | ix_consignments_in_transit | 2.4 | `btree (consignment_id) INCLUDE (tracking_number, customer_id, carrier_id) WHERE (status = 'in_transit'::text)` |
| customers | 0.1 | customers_pkey | 0.0 | `btree (customer_id)` |
| invoices | 156.5 | invoices_pkey | 41.6 | `btree (invoice_id)` |
| tracking_events | 757.9 | tracking_events_pkey | 216.7 | `btree (event_id)` |
| tracking_events | 757.9 | ix_tracking_events_consignment_time | 298.1 | `btree (consignment_id, occurred_at)` |

Secondary indexes total: **438.1 MB**
