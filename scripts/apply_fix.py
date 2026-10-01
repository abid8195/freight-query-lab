"""Apply one tuning step from sql/fixes/, then re-run the full benchmark and size
report into results/after/<step>/.

Usage: python scripts/apply_fix.py 01_q2_tracking_number
"""
import subprocess
import sys

from common import ROOT, connect

step = sys.argv[1]
text = (ROOT / "sql" / "fixes" / f"{step}.sql").read_text()
# Fix files use whole-line comments only, so dropping them makes splitting on ';' safe.
sql = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
with connect(autocommit=True) as conn:  # autocommit so VACUUM / CONCURRENTLY work
    for stmt in filter(str.strip, sql.split(";")):
        conn.execute(stmt)
    conn.execute("ANALYZE")
print(f"applied {step}")
for script in ("benchmark.py", "index_report.py"):
    subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--label", f"after/{step}"], check=True)
