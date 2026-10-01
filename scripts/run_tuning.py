"""Reproduce the whole tuning study in one pass so every number is measured
under the same machine conditions:

reset -> baseline (benchmark, sizes, write cost) -> each sql/fixes/*.sql in
order (apply, benchmark, sizes) -> final write cost -> comparison table.
"""
import shutil
import subprocess
import sys

from common import ROOT


def py(script, *args):
    subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], check=True)


py("reset_tuning.py")
for d in ("before", "after"):
    shutil.rmtree(ROOT / "results" / d, ignore_errors=True)
py("benchmark.py", "--label", "before")
py("index_report.py", "--label", "before")
py("write_cost.py", "--label", "before")
for fix in sorted((ROOT / "sql" / "fixes").glob("*.sql")):
    py("apply_fix.py", fix.stem)
py("write_cost.py", "--label", "after")
py("compare.py")
