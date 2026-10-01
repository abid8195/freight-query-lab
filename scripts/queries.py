"""The five benchmark queries. Customer ids are popularity ranks (1 = biggest)."""
from datetime import datetime, timedelta, timezone

from common import AS_OF, tracking_number

QUERIES = [
    {
        "id": "q1",
        "name": "customer consignments, date range, page 3",
        # Customer 1 is the heaviest tenant (~18% of all consignments).
        "sql": """
            SELECT consignment_id, tracking_number, status, created_at, weight_kg, price
            FROM consignments
            WHERE customer_id = %(customer_id)s
              AND created_at >= %(date_from)s AND created_at < %(date_to)s
            ORDER BY created_at DESC, consignment_id DESC
            LIMIT 50 OFFSET 100
        """,
        "params": {
            "customer_id": 1,
            "date_from": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "date_to": datetime(2026, 9, 1, tzinfo=timezone.utc),
        },
    },
    {
        "id": "q2",
        "name": "consignment by tracking_number",
        "sql": """
            SELECT consignment_id, customer_id, carrier_id, status, created_at, weight_kg, price
            FROM consignments
            WHERE tracking_number = %(tracking_number)s
        """,
        "params": {"tracking_number": tracking_number(1_234_567)},
    },
    {
        "id": "q3",
        "name": "latest tracking event per consignment, one customer",
        # Customer 20 is a mid-size tenant (~13k consignments, ~65k events).
        "sql": """
            SELECT DISTINCT ON (e.consignment_id)
                   e.consignment_id, e.status, e.location, e.occurred_at
            FROM tracking_events e
            JOIN consignments c ON c.consignment_id = e.consignment_id
            WHERE c.customer_id = %(customer_id)s
            ORDER BY e.consignment_id, e.occurred_at DESC
        """,
        "params": {"customer_id": 20},
    },
    {
        "id": "q4",
        "name": "monthly invoice totals per carrier (12 months)",
        "sql": """
            SELECT ca.name AS carrier, date_trunc('month', i.issued_at) AS month,
                   count(*) AS invoices, sum(i.amount) AS total
            FROM invoices i
            JOIN consignments c ON c.consignment_id = i.consignment_id
            JOIN carriers ca    ON ca.carrier_id = c.carrier_id
            WHERE i.status <> 'void'
              AND i.issued_at >= %(date_from)s AND i.issued_at < %(date_to)s
            GROUP BY ca.name, date_trunc('month', i.issued_at)
            ORDER BY carrier, month
        """,
        "params": {"date_from": AS_OF - timedelta(days=365), "date_to": AS_OF},
        # Used once fix 05 has copied carrier_id onto invoices: no 2M-row join,
        # and the aggregate groups on an int instead of sorting by carrier name.
        "rewrite": {
            "requires": """SELECT EXISTS (SELECT 1 FROM information_schema.columns
                            WHERE table_name = 'invoices' AND column_name = 'carrier_id')""",
            "sql": """
                SELECT ca.name AS carrier, t.month, t.invoices, t.total
                FROM (
                    SELECT carrier_id, date_trunc('month', issued_at) AS month,
                           count(*) AS invoices, sum(amount) AS total
                    FROM invoices
                    WHERE status <> 'void'
                      AND issued_at >= %(date_from)s AND issued_at < %(date_to)s
                    GROUP BY carrier_id, date_trunc('month', issued_at)
                ) t
                JOIN carriers ca ON ca.carrier_id = t.carrier_id
                ORDER BY carrier, month
            """,
        },
    },
    {
        "id": "q5",
        "name": "stuck in transit > 5 days",
        "sql": """
            SELECT c.consignment_id, c.tracking_number, c.customer_id, c.carrier_id,
                   max(e.occurred_at) AS last_event_at
            FROM consignments c
            JOIN tracking_events e ON e.consignment_id = c.consignment_id
            WHERE c.status = 'in_transit'
            GROUP BY c.consignment_id
            HAVING max(e.occurred_at) < %(cutoff)s
            ORDER BY last_event_at
        """,
        "params": {"cutoff": AS_OF - timedelta(days=5)},
    },
]


def resolve_sql(conn, q) -> tuple[str, bool]:
    """The SQL to run for q against the current schema, and whether it's the rewrite."""
    rw = q.get("rewrite")
    if rw and conn.execute(rw["requires"]).fetchone()[0]:
        return rw["sql"], True
    return q["sql"], False
