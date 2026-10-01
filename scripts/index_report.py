"""Table and index sizes, written to results/<label>/sizes.md."""
import argparse

from common import ROOT, connect

SQL = """
SELECT c.relname AS table, i.relname AS index,
       pg_relation_size(i.oid) AS index_bytes,
       pg_relation_size(c.oid) AS table_bytes,
       ix.indisprimary AS primary
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class c ON c.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
ORDER BY c.relname, ix.indisprimary DESC, i.relname
"""


def mb(b):
    return f"{b / 2**20:,.1f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    args = ap.parse_args()
    with connect() as conn:
        rows = conn.execute(SQL).fetchall()
        defs = dict(conn.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public'").fetchall())
    lines = ["| table | table MB | index | index MB | definition |", "|---|---:|---|---:|---|"]
    secondary = 0
    for table, index, ib, tb, primary in rows:
        lines.append(f"| {table} | {mb(tb)} | {index} | {mb(ib)} | `{defs[index].split(' USING ')[1]}` |")
        secondary += 0 if primary else ib
    lines.append(f"\nSecondary indexes total: **{mb(secondary)} MB**")
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=True)
    (out / "sizes.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
