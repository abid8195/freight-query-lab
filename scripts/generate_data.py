"""Generate synthetic freight data and bulk-load it into PostgreSQL with COPY.

Volume is skewed: customer popularity follows a Zipf-like curve (s=1.1), so
customer 1 alone owns ~18% of consignments and the top 10 own ~50%.
Customer ids are assigned by rank, so a lower id means a bigger customer.

Usage: python scripts/generate_data.py [--consignments 2000000] [--seed 42]
"""
import argparse
import io
import time

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv

from common import AS_OF, HISTORY_START, ROOT, TRACKING_MULTIPLIER, connect

N_CUSTOMERS = 1_000
N_CARRIERS = 50
CHUNK = 200_000

STATUSES = np.array(["created", "picked_up", "in_transit", "out_for_delivery", "delivered", "exception"])
CREATED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED, EXCEPTION = range(6)

# (max age in days, status probabilities) - older consignments are mostly done.
# The 2% still "in_transit" after a week are the stuck ones query 5 looks for.
STATUS_BY_AGE = [
    (1, [0.30, 0.30, 0.40, 0.00, 0.00, 0.00]),
    (3, [0.00, 0.10, 0.55, 0.15, 0.18, 0.02]),
    (7, [0.00, 0.00, 0.25, 0.05, 0.66, 0.04]),
    (np.inf, [0.00, 0.00, 0.02, 0.00, 0.955, 0.025]),
]
# Inclusive range of tracking events per final status.
EVENT_COUNTS = {
    CREATED: (1, 1), PICKED_UP: (2, 2), IN_TRANSIT: (3, 6),
    OUT_FOR_DELIVERY: (4, 6), DELIVERED: (4, 6), EXCEPTION: (3, 5),
}

CITIES = np.array([
    "Rotterdam", "Hamburg", "Antwerp", "Felixstowe", "Le Havre", "Valencia", "Genoa", "Gdansk",
    "Amsterdam", "Berlin", "Munich", "Frankfurt", "Cologne", "Paris", "Lyon", "Marseille",
    "Madrid", "Barcelona", "Lisbon", "Porto", "Milan", "Turin", "Rome", "Naples", "Vienna",
    "Zurich", "Basel", "Brussels", "Liege", "Luxembourg", "Copenhagen", "Aarhus", "Stockholm",
    "Gothenburg", "Oslo", "Helsinki", "Warsaw", "Krakow", "Poznan", "Prague", "Brno", "Budapest",
    "Bratislava", "Ljubljana", "Zagreb", "Bucharest", "Sofia", "Athens", "Dublin", "London",
    "Manchester", "Birmingham", "Leeds", "Glasgow", "Edinburgh", "Bristol", "Cardiff", "Leipzig",
    "Dortmund", "Duisburg",
])
COUNTRIES = np.array(["NL", "DE", "BE", "FR", "ES", "IT", "PL", "GB", "SE", "DK", "AT", "CZ", "IE", "PT"])
NAME_A = ["Northwind", "Bluewater", "Ironbridge", "Silverline", "Crestview", "Harbor", "Summit",
          "Evergreen", "Redstone", "Brightpath", "Oakfield", "Westgate", "Kestrel", "Atlas", "Meridian"]
NAME_B = ["Trading", "Retail", "Foods", "Electronics", "Pharma", "Textiles", "Components",
          "Home", "Outdoor", "Beverages", "Auto Parts", "Supplies"]
NAME_C = ["Ltd", "GmbH", "BV", "SA", "Srl", "AB", "plc", "NV"]
CARRIER_MODES = np.array(["road", "air", "sea", "rail", "courier"])


def decimal_array(cents: np.ndarray, precision: int = 12) -> pa.Array:
    """Exact decimal(precision, 2) array from integer cents, without going via float."""
    cents = cents.astype(np.int64)
    words = np.empty((len(cents), 2), dtype=np.int64)
    words[:, 0] = cents
    words[:, 1] = np.where(cents < 0, -1, 0)  # two's-complement high word
    return pa.Array.from_buffers(pa.decimal128(precision, 2), len(cents), [None, pa.py_buffer(words.tobytes())])


def ts_array(epoch_us: np.ndarray) -> pa.Array:
    return pa.array(epoch_us.astype(np.int64), pa.timestamp("us", tz="UTC"))


def copy_table(cur, table: str, columns: list[str], data: pa.Table) -> None:
    buf = io.BytesIO()
    pacsv.write_csv(data, buf, pacsv.WriteOptions(include_header=False, quoting_style="needed"))
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN (FORMAT csv)") as copy:
        copy.write(buf.getvalue())


def us(dt) -> int:
    return int(dt.timestamp() * 1_000_000)


def make_customers(rng):
    ids = np.arange(1, N_CUSTOMERS + 1)
    names = [f"{rng.choice(NAME_A)} {rng.choice(NAME_B)} {rng.choice(NAME_C)} #{i}" for i in ids]
    created = rng.integers(us(HISTORY_START) - 5 * 365 * 86_400_000_000, us(HISTORY_START), N_CUSTOMERS)
    return pa.table({
        "customer_id": pa.array(ids, pa.int32()),
        "name": pa.array(names),
        "country": pa.array(rng.choice(COUNTRIES, N_CUSTOMERS)),
        "created_at": ts_array(created),
    })


def make_carriers(rng):
    ids = np.arange(1, N_CARRIERS + 1)
    modes = rng.choice(CARRIER_MODES, N_CARRIERS, p=[0.5, 0.1, 0.1, 0.1, 0.2])
    names = [f"{rng.choice(NAME_A)} {m.title()} Logistics #{i}" for i, m in zip(ids, modes)]
    return pa.table({"carrier_id": pa.array(ids, pa.int32()), "name": pa.array(names), "mode": pa.array(modes)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--consignments", type=int, default=2_000_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    t0 = time.perf_counter()

    customer_p = 1.0 / np.arange(1, N_CUSTOMERS + 1) ** 1.1
    customer_p /= customer_p.sum()
    carrier_p = rng.dirichlet(np.full(N_CARRIERS, 0.8))
    carrier_rate = rng.uniform(1.1, 3.0, N_CARRIERS)  # EUR per kg

    # Volume grows over time (u**0.7 puts more mass near AS_OF); ids follow time order.
    start_us, end_us = us(HISTORY_START), us(AS_OF)
    created_all = np.sort(start_us + (rng.random(args.consignments) ** 0.7 * (end_us - start_us - 60e6)).astype(np.int64))

    with connect(autocommit=False) as conn, conn.cursor() as cur:
        cur.execute((ROOT / "sql" / "schema.sql").read_text())
        copy_table(cur, "customers", ["customer_id", "name", "country", "created_at"], make_customers(rng))
        copy_table(cur, "carriers", ["carrier_id", "name", "mode"], make_carriers(rng))

        next_event_id = next_invoice_id = 1
        totals = {"consignments": 0, "tracking_events": 0, "invoices": 0}
        for lo in range(0, args.consignments, CHUNK):
            created = created_all[lo:lo + CHUNK]
            n = len(created)
            cid = np.arange(lo + 1, lo + n + 1, dtype=np.int64)
            customer = rng.choice(N_CUSTOMERS, n, p=customer_p) + 1
            carrier = rng.choice(N_CARRIERS, n, p=carrier_p) + 1
            weight_cents = np.clip(np.round(rng.lognormal(np.log(8), 1.2, n) * 100), 10, 2_000_000).astype(np.int64)
            price_cents = np.round((600 + weight_cents * carrier_rate[carrier - 1]) * rng.uniform(0.9, 1.15, n)).astype(np.int64)

            age_days = (end_us - created) / 86_400e6
            status = np.empty(n, dtype=np.int64)
            prev = -np.inf
            for max_age, p in STATUS_BY_AGE:
                mask = (age_days >= prev) & (age_days < max_age)
                status[mask] = rng.choice(6, mask.sum(), p=p)
                prev = max_age

            # --- tracking events -------------------------------------------------
            counts = np.empty(n, dtype=np.int64)
            for s, (a, b) in EVENT_COUNTS.items():
                m = status == s
                counts[m] = rng.integers(a, b + 1, m.sum())
            starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
            total = counts.sum()
            owner = np.repeat(np.arange(n), counts)
            pos = np.arange(total) - starts[owner]
            last = pos == counts[owner] - 1
            final = status[owner]

            ev_status = np.full(total, IN_TRANSIT)
            ev_status[pos == 1] = PICKED_UP
            ev_status[(final == DELIVERED) & (pos == counts[owner] - 2)] = OUT_FOR_DELIVERY
            ev_status[last] = final[last]
            ev_status[pos == 0] = CREATED

            gaps = rng.exponential(14 * 3600e6, total)  # ~14h between scans
            gaps[pos == 0] = 0
            cs = np.cumsum(gaps)
            offset = cs - cs[starts][owner]
            span = offset[np.cumsum(counts) - 1]  # time from first to last event
            allowed = age_days * 86_400e6 * 0.95  # never schedule events after AS_OF
            scale = np.minimum(1.0, allowed / np.maximum(span, 1))
            occurred = created[owner] + (offset * scale[owner]).astype(np.int64)

            # --- invoices: finished consignments, issued up to 3 days after last event
            last_event_at = occurred[np.cumsum(counts) - 1]
            billable = (status == DELIVERED) | (status == EXCEPTION)
            issued = last_event_at + rng.integers(0, 3 * 86_400_000_000, n)
            billable &= issued < end_us
            inv_n = int(billable.sum())
            inv_issued = issued[billable]
            inv_status = np.where(inv_issued < end_us - 30 * 86_400_000_000,
                                  rng.choice(["paid", "issued"], inv_n, p=[0.97, 0.03]), "issued")
            inv_status[rng.random(inv_n) < 0.01] = "void"
            surcharge = rng.uniform(1.08, 1.15, inv_n)

            consignments = pa.table({
                "consignment_id": pa.array(cid),
                "customer_id": pa.array(customer, pa.int32()),
                "carrier_id": pa.array(carrier, pa.int32()),
                "tracking_number": pa.array(np.char.add("FQ", np.char.zfill(((cid * TRACKING_MULTIPLIER) % 10**10).astype(str), 10))),
                "status": pa.array(STATUSES[status]),
                "created_at": ts_array(created),
                "weight_kg": decimal_array(weight_cents, 10),
                "price": decimal_array(price_cents),
            })
            events = pa.table({
                "event_id": pa.array(np.arange(next_event_id, next_event_id + total, dtype=np.int64)),
                "consignment_id": pa.array(cid[owner]),
                "status": pa.array(STATUSES[ev_status]),
                "location": pa.array(rng.choice(CITIES, total)),
                "occurred_at": ts_array(occurred),
            })
            invoices = pa.table({
                "invoice_id": pa.array(np.arange(next_invoice_id, next_invoice_id + inv_n, dtype=np.int64)),
                "consignment_id": pa.array(cid[billable]),
                "customer_id": pa.array(customer[billable], pa.int32()),
                "issued_at": ts_array(inv_issued),
                "due_at": ts_array(inv_issued + 30 * 86_400_000_000),
                "amount": decimal_array(np.round(price_cents[billable] * surcharge).astype(np.int64)),
                "status": pa.array(inv_status),
            })
            for name, tbl in (("consignments", consignments), ("tracking_events", events), ("invoices", invoices)):
                copy_table(cur, name, tbl.column_names, tbl)
                totals[name] += tbl.num_rows
            next_event_id += total
            next_invoice_id += inv_n
            print(f"  loaded {lo + n:>9,} consignments  ({time.perf_counter() - t0:6.1f}s)", flush=True)

        print("adding foreign keys ...", flush=True)
        cur.execute((ROOT / "sql" / "constraints.sql").read_text())
        conn.commit()

    with connect(autocommit=True) as conn:
        print("VACUUM ANALYZE ...", flush=True)
        conn.execute("VACUUM ANALYZE")

    print(f"done in {time.perf_counter() - t0:.0f}s: {N_CUSTOMERS:,} customers, {N_CARRIERS} carriers, "
          + ", ".join(f"{v:,} {k}" for k, v in totals.items()))


if __name__ == "__main__":
    main()
