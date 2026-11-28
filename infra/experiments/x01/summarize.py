"""XC-EXP-01 summary: one host's series -> summary.json.

    python summarize.py <out_dir>

Reads <out_dir>/series.jsonl (one JSON line per fresh process). For every (library, phantom)
and output array it counts the distinct hashes over the runs (1 = deterministic), and reports
median and nearest-rank p95 of the first-call and second-call times.
"""

import json
import math
from pathlib import Path
import statistics
import sys


def p95(xs: list[float]) -> float:
    s = sorted(xs)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def summarize(out: Path) -> dict:
    rows = [json.loads(line) for line in (out / "series.jsonl").read_text().splitlines() if line]
    good = [r for r in rows if "error" not in r]
    result: dict = {"runs": len(rows), "errors": len(rows) - len(good), "groups": {}}
    for group, fields in (("closest", ("face", "sqdist", "point")), ("lod", ("V", "F"))):
        for key in sorted(good[0][group]) if good else []:
            entries = [r[group][key] for r in good]
            first = [e["first_s"] for e in entries]
            second = [e["second_s"] for e in entries]
            result["groups"][f"{group}/{key}"] = {
                "distinct_hashes": {f: len({e[f] for e in entries}) for f in fields},
                "hash": {f: entries[0][f] for f in fields},
                "same_in_process": sum(e["same_in_process"] for e in entries),
                "first_s": {"median": statistics.median(first), "p95": p95(first)},
                "second_s": {"median": statistics.median(second), "p95": p95(second)},
                **{k: entries[0][k] for k in ("n_queries", "faces_in", "faces_out")
                   if k in entries[0]},
            }  # fmt: skip
    totals = [r["total_s"] for r in good]
    warm = [r["import_and_warmup_s"] for r in good]
    if good:
        result["process_s"] = {"median": statistics.median(totals), "p95": p95(totals)}
        result["import_and_warmup_s"] = {"median": statistics.median(warm), "p95": p95(warm)}
    result["deterministic"] = bool(good) and all(
        all(n == 1 for n in g["distinct_hashes"].values()) and g["same_in_process"] == len(good)
        for g in result["groups"].values()
    )
    return result


if __name__ == "__main__":
    out = Path(sys.argv[1])
    summary = summarize(out)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"runs": summary["runs"], "errors": summary["errors"],
                      "deterministic": summary["deterministic"]}))  # fmt: skip
