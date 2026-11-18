#!/usr/bin/env python3
"""check_docs.py - DOC-CHK for XC-FND-10: every MVP requirement has >= 1 task and >= 1 test ID.

A requirement counts as having a test ID when at least one of these holds:
  1. the test catalogue has a TC row for it (column `requirement`);
  2. a WBS task that lists it has a non-empty `tests` column (UT-/IT-/GT-/CI-/OT- ... IDs);
  3. the RTM `verified_by` column names a verification suite (VER-nn).
Also checked: every requirement ID referenced by a WBS task or a TC row exists in the RTM, and
every TC row points to an existing requirement.

Usage: python docs/tools/check_docs.py [RTM.csv] [CATALOGUE.csv] [WBS.csv]
Defaults: RTM v0.4, test catalogue v0.4, WBS v1.1. Exit 0 = pass, 1 = findings.
"""

import csv
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
REQ_RE = re.compile(r"\b(?:STK|UR|FR|NFR|DATA|INT|SEC|SAF|VER|AI)-\d+\b")
DEFAULTS = [
    ROOT / "docs/design/04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.4.csv",
    ROOT / "docs/design/09_TEST_CASE_CATALOGUE_v0.4.csv",
    ROOT / "docs/plan/WORK_BREAKDOWN_STRUCTURE_v1.1.csv",
]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str]) -> int:
    rtm_p, tc_p, wbs_p = [Path(a) for a in argv] if len(argv) == 3 else DEFAULTS
    rtm = {r["id"]: r for r in rows(rtm_p)}
    mvp = sorted((i for i, r in rtm.items() if r["release"].strip() == "MVP"),
                 key=lambda i: (i.split("-")[0], int(i.split("-")[1])))

    tasks: dict[str, list[str]] = {}
    task_tests: dict[str, bool] = {}
    unknown_in_wbs: set[str] = set()
    for w in rows(wbs_p):
        if w["level"] != "Task":
            continue
        for rid in REQ_RE.findall(w["requirement_ids"]):
            tasks.setdefault(rid, []).append(w["id"])
            task_tests[rid] = task_tests.get(rid, False) or bool(w["tests"].strip())
            if rid not in rtm:
                unknown_in_wbs.add(rid)

    tcs: dict[str, list[str]] = {}
    unknown_in_tc: set[str] = set()
    for t in rows(tc_p):
        for rid in REQ_RE.findall(t["requirement"]):
            tcs.setdefault(rid, []).append(t["tc_id"])
            if rid not in rtm:
                unknown_in_tc.add(rid)

    no_task, no_test, sources = [], [], {"catalogue": 0, "wbs-tests": 0, "verified_by": 0}
    for rid in mvp:
        if rid not in tasks:
            no_task.append(rid)
        if rid in tcs:
            sources["catalogue"] += 1
        elif task_tests.get(rid):
            sources["wbs-tests"] += 1
        elif re.search(r"\bVER-\d+\b", rtm[rid]["verified_by"]):
            sources["verified_by"] += 1
        else:
            no_test.append(rid)

    print(f"RTM: {rtm_p.name} ({len(rtm)} rows, {len(mvp)} MVP)")
    print(f"Test ID source for MVP requirements: {sources}")
    findings = 0
    for label, items in (
        ("MVP requirements without a task", no_task),
        ("MVP requirements without a test ID", no_test),
        ("Requirement IDs in WBS tasks not in RTM", sorted(unknown_in_wbs)),
        ("Requirement IDs in test catalogue not in RTM", sorted(unknown_in_tc)),
    ):
        print(f"{label}: {len(items)}" + (f" -> {', '.join(items)}" if items else ""))
        findings += len(items)
    print("DOC-CHK: PASS" if not findings else "DOC-CHK: FAIL")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
