# Before / after, per tuning step

Median of 10 warm runs. Each step adds one change on top of the previous ones and
re-runs all five queries; this table shows each step's target queries.

| step | query | ms before | ms after | speed-up | buffers before | buffers after |
|---|---|---:|---:|---:|---|---|
| 01_q2_tracking_number | q2 | 146.69 | 0.59 | 248.6x | 20,654 hit / 3,438 read | 4 hit / 0 read |
| 02_q1_customer_created | q1 | 70.33 | 0.84 | 83.7x | 23,784 hit / 396 read | 13 hit / 0 read |
| 03_q3_q5_events_consignment_time | q3 | 483.93 | 113.43 | 4.3x | 24,274 hit / 72,902 read | 53,947 hit / 0 read |
| 03_q3_q5_events_consignment_time | q5 | 838.23 | 345.70 | 2.4x | 49,356 hit / 71,750 read | 165,315 hit / 7,391 read |
| 04_q4_invoices_issued_at | q4 | 1,701.91 | 1,752.76 | 1.0x | 27,556 hit / 22,511 read / 45,200 temp | 25,278 hit / 22,510 read / 45,183 temp |
| 05_q4_denormalise_carrier | q4 | 1,752.76 | 520.29 | 3.4x | 25,278 hit / 22,510 read / 45,183 temp | 2,181 hit / 17,852 read |
| 06_q5_partial_in_transit | q5 | 315.32 | 230.49 | 1.4x | 166,768 hit / 5,938 read | 148,919 hit / 0 read |

Noise check: queries a step did not target moved between 0.56x and 2.04x between consecutive steps, so treat wall-clock changes under ~2x as unproven and look at the buffer counts.

## Overall

| query | description | ms before | ms final | speed-up | buffers before | buffers final |
|---|---|---:|---:|---:|---|---|
| q1 | customer consignments, date range, page 3 | 143.54 | 0.85 | 169x | 19,590 hit / 4,590 read | 13 hit / 0 read |
| q2 | consignment by tracking_number | 146.69 | 0.71 | 207x | 20,654 hit / 3,438 read | 4 hit / 0 read |
| q3 | latest tracking event per consignment, one customer | 867.95 | 83.54 | 10x | 35,449 hit / 80,275 read | 53,947 hit / 0 read |
| q4 | monthly invoice totals per carrier (12 months) | 2,045.57 | 525.63 | 4x | 24,604 hit / 22,510 read / 45,175 temp | 2,629 hit / 17,404 read |
| q5 | stuck in transit > 5 days | 539.86 | 230.49 | 2x | 37,977 hit / 77,597 read | 148,919 hit / 0 read |
