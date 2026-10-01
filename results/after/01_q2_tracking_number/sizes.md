| table | table MB | index | index MB | definition |
|---|---:|---|---:|---|
| carriers | 0.0 | carriers_pkey | 0.0 | `btree (carrier_id)` |
| consignments | 188.2 | consignments_pkey | 43.7 | `btree (consignment_id)` |
| consignments | 188.2 | consignments_tracking_number_key | 60.2 | `btree (tracking_number)` |
| customers | 0.1 | customers_pkey | 0.0 | `btree (customer_id)` |
| invoices | 166.0 | invoices_pkey | 84.0 | `btree (invoice_id)` |
| tracking_events | 757.9 | tracking_events_pkey | 216.7 | `btree (event_id)` |

Secondary indexes total: **60.2 MB**
