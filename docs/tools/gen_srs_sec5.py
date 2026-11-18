#!/usr/bin/env python3
"""gen_srs_sec5.py - regenerate SRS section 5 ("Requirements by capability, MVP release") from the RTM.

The SRS adds no requirement: requirement text, acceptance criteria and verification live only in the RTM CSV.
Usage:  python tools/gen_srs_sec5.py <RTM.csv> <out.md>
Rows are grouped by the first ODC id in the RTM column `capability`; rows without one go to ODC-00 (unassigned).
Only release = MVP rows are listed (post-MVP / research-only rows stay in the RTM).
"""
import csv, re, sys
from collections import defaultdict

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8-sig", newline="")))
groups = defaultdict(list)
for r in rows:
    if r["release"].strip() != "MVP":
        continue
    m = re.search(r"ODC-(\d+)", r["capability"])
    groups[int(m.group(1)) if m else 0].append(r)

def key(r):
    t = {"STK": 0, "UR": 1, "FR": 2, "NFR": 3, "DATA": 4, "INT": 5, "SEC": 6, "SAF": 7, "VER": 8, "AI": 9}
    m = re.match(r"([A-Z]+)-(\d+)", r["id"])
    return (t.get(m.group(1), 99), int(m.group(2)))

def cell(s):
    return re.sub(r"\s+", " ", s.replace("|", "\\|")).strip()

out = ["## 5. Requirements by capability (MVP release; generated from the RTM)", "",
       "Post-MVP, research-only and TBD-release rows are in the RTM only.", ""]
n = 0
for g in sorted(groups):
    out += [f"#### {'ODC-%02d' % g if g else 'ODC-00 (no capability assigned)'}", "",
            "| ID | Type | Title | Pri | Verification | Acceptance criteria |", "|---|---|---|---|---|---|"]
    for r in sorted(groups[g], key=key):
        v = (r["verification_method"] + " → " + r["verified_by"]).strip(" →")
        out.append(f"| {r['id']} | {r['type']} | {cell(r['title'])} | {r['priority']} | {cell(v)} | {cell(r['acceptance_criteria'])} |")
        n += 1
    out.append("")
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(out))
print(f"{n} MVP requirements in {len(groups)} capability groups -> {sys.argv[2]}")
