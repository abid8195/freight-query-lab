"""Measure what indexes cost on the write path.

Inserts 20k consignments, 100k tracking events and 20k invoices in one
transaction, then rolls back. Repeated 5 times; the median is saved to
results/<label>/write_cost.json. Run once with no secondary indexes and once
with all of them.
"""
import argparse
import json
import statistics
import time

from common import AS_OF, ROOT, connect

STEPS = {
    "consignments": """
        INSERT INTO consignments
        SELECT 10000000 + g, 1 + g %% 1000, 1 + g %% 50, 'WC' || lpad(g::text, 10, '0'), 'in_transit',
               %(as_of)s - make_interval(mins => g), 5.00, 20.00
        FROM generate_series(1, 20000) g""",
    "tracking_events": """
        INSERT INTO tracking_events
        SELECT 100000000 + g, 10000001 + g %% 20000, 'in_transit', 'Rotterdam', %(as_of)s - make_interval(mins => g)
        FROM generate_series(1, 100000) g""",
    "invoices": """
        INSERT INTO invoices (invoice_id, consignment_id, customer_id, issued_at, due_at, amount, status{carrier_col})
        SELECT 10000000 + g, 10000000 + g, 1 + g %% 1000, %(as_of)s, %(as_of)s + interval '30 days', 21.50, 'issued'{carrier_val}
        FROM generate_series(1, 20000) g""",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()
    samples = {k: [] for k in STEPS}
    with connect() as conn:
        # After fix 05, invoices carry a denormalised carrier_id that must be written too.
        has_carrier = conn.execute("""SELECT EXISTS (SELECT 1 FROM information_schema.columns
            WHERE table_name = 'invoices' AND column_name = 'carrier_id')""").fetchone()[0]
        steps = dict(STEPS, invoices=STEPS["invoices"].format(
            carrier_col=", carrier_id" if has_carrier else "", carrier_val=", 1 + g %% 50" if has_carrier else ""))
        for _ in range(args.repeats + 1):  # first round is warm-up
            for name, sql in steps.items():
                t = time.perf_counter()
                conn.execute(sql, {"as_of": AS_OF})
                samples[name].append((time.perf_counter() - t) * 1000)
            conn.rollback()
    result = {k: round(statistics.median(v[1:]), 1) for k, v in samples.items()}
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=True)
    (out / "write_cost.json").write_text(json.dumps(result, indent=2))
    for k, v in result.items():
        print(f"{k:16} {v:8.1f} ms")


if __name__ == "__main__":
    main()
