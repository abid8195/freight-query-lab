"""Build results/comparison.md: baseline vs each tuning step.

Every step folder under results/after/ holds timings and plans for all five
queries. A step's target queries are the q-ids in its name
(e.g. 03_q3_q5_events_consignment_time). Buffer counts come from the top node
of each EXPLAIN (ANALYZE, BUFFERS) plan and, unlike wall-clock time, don't
depend on what else the laptop is doing.
"""
import json
import re

from common import ROOT


def load(path):
    timings = json.loads((path / "timings.json").read_text())
    for qid, t in timings.items():
        plan = (path / f"{qid}.plan.txt").read_text()
        m = re.search(r"Buffers: (.*)", plan)
        nums = dict(re.findall(r"(hit|read|written)=(\d+)", m.group(1) if m else ""))
        t["hit"], t["read"] = int(nums.get("hit", 0)), int(nums.get("read", 0))
        temp = re.search(r"temp read=(\d+) written=(\d+)", m.group(1) if m else "")
        t["temp"] = int(temp.group(1)) + int(temp.group(2)) if temp else 0
    return timings


def pages(t):
    s = f"{t['hit']:,} hit / {t['read']:,} read"
    return s + (f" / {t['temp']:,} temp" if t["temp"] else "")


def main():
    before = load(ROOT / "results" / "before")
    steps = sorted(p for p in (ROOT / "results" / "after").iterdir() if (p / "timings.json").exists())
    lines = ["# Before / after, per tuning step", "",
             "Median of 10 warm runs. Each step adds one change on top of the previous ones and",
             "re-runs all five queries; this table shows each step's target queries.", "",
             "| step | query | ms before | ms after | speed-up | buffers before | buffers after |",
             "|---|---|---:|---:|---:|---|---|"]
    current = dict(before)
    noise = []
    for step in steps:
        targets = set(re.findall(r"q\d", step.name))
        for qid, t in sorted(load(step).items()):
            prev = current[qid]
            ratio = prev["median_ms"] / t["median_ms"]
            if qid in targets:
                lines.append(f"| {step.name} | {qid} | {prev['median_ms']:,.2f} | {t['median_ms']:,.2f} | "
                             f"{ratio:,.1f}x | {pages(prev)} | {pages(t)} |")
            elif abs((t["hit"] + t["read"]) / (prev["hit"] + prev["read"]) - 1) < 0.05:
                noise.append(ratio)  # plan did the same work, so the time change is noise
            current[qid] = t
    lines += ["", f"Noise check: queries a step did not target moved between {min(noise):.2f}x and "
              f"{max(noise):.2f}x between consecutive steps, so treat wall-clock changes under ~2x "
              "as unproven and look at the buffer counts.", "",
              "## Overall", "",
              "| query | description | ms before | ms final | speed-up | buffers before | buffers final |",
              "|---|---|---:|---:|---:|---|---|"]
    for qid, t in sorted(before.items()):
        f = current[qid]
        lines.append(f"| {qid} | {t['name']} | {t['median_ms']:,.2f} | {f['median_ms']:,.2f} | "
                     f"{t['median_ms'] / f['median_ms']:,.0f}x | {pages(t)} | {pages(f)} |")
    (ROOT / "results" / "comparison.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
