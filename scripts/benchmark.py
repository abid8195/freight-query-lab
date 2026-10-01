"""Run each query N times, record the median, and save EXPLAIN (ANALYZE, BUFFERS).

Usage: python scripts/benchmark.py --label before
       python scripts/benchmark.py --label after/01_q2_tracking_number --only q2
Writes results/<label>/timings.json, results/<label>/<qid>.plan.txt and summary.md.
"""
import argparse
import json
import statistics
import time

from common import ROOT, connect
from queries import QUERIES, resolve_sql


def run(conn, q, runs):
    sql, rewritten = resolve_sql(conn, q)
    with conn.cursor() as cur:
        cur.execute(sql, q["params"])  # warm-up, not counted
        rows = len(cur.fetchall())
        times = []
        for _ in range(runs):
            t = time.perf_counter()
            cur.execute(sql, q["params"])
            cur.fetchall()
            times.append((time.perf_counter() - t) * 1000)
        cur.execute("EXPLAIN (ANALYZE, BUFFERS, SETTINGS) " + sql, q["params"])
        plan = "\n".join(r[0] for r in cur.fetchall())
    return rows, times, plan, sql, rewritten


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="output folder under results/, e.g. before")
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--only", nargs="*", help="query ids to run (default: all)")
    args = ap.parse_args()

    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=True)
    timings_path = out / "timings.json"
    timings = json.loads(timings_path.read_text()) if timings_path.exists() else {}

    with connect(autocommit=True) as conn:
        conn.execute("SET statement_timeout = '10min'")
        for q in QUERIES:
            if args.only and q["id"] not in args.only:
                continue
            print(f"{q['id']}: {q['name']} ...", flush=True)
            rows, times, plan, sql, rewritten = run(conn, q, args.runs)
            tag = " (rewritten)" if rewritten else ""
            (out / f"{q['id']}.plan.txt").write_text(f"-- {q['name']}{tag}\n{sql.strip()}\n-- params: {q['params']}\n\n{plan}\n")
            timings[q["id"]] = {
                "name": q["name"], "rewritten": rewritten, "rows": rows, "runs": args.runs,
                "median_ms": round(statistics.median(times), 2),
                "min_ms": round(min(times), 2), "max_ms": round(max(times), 2),
            }
    timings_path.write_text(json.dumps(timings, indent=2))

    lines = ["| query | description | rows | median ms | min ms | max ms |", "|---|---|---:|---:|---:|---:|"]
    lines += [f"| {k} | {v['name']} | {v['rows']:,} | {v['median_ms']:,.2f} | {v['min_ms']:,.2f} | {v['max_ms']:,.2f} |"
              for k, v in sorted(timings.items())]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
