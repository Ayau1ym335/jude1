"""Summarise one XC-EXP-06 host directory: hash agreement and warm-up median/p95.

Usage: summarize.py <out_dir>   -> summary.json, results.csv
"""

import csv
import json
from pathlib import Path
import statistics
import sys


def p95(values: list[float]) -> float:
    s = sorted(values)
    return s[max(0, min(len(s) - 1, -(-95 * len(s) // 100) - 1))]


def stats(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "median": round(statistics.median(values), 4),
        "p95": round(p95(values), 4),
    }


def main(out: Path) -> None:
    series: dict[str, list[dict]] = {}
    for path in sorted(out.glob("series-*.jsonl")):
        key = path.stem.removeprefix("series-")
        series[key] = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]

    with (out / "results.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["series", "run", "kernel", "first_s", "second_s", "sha256", "repeat_equal"])
        for key, rows in series.items():
            for r in rows:
                for name, k in r["kernels"].items():
                    w.writerow(
                        [
                            key,
                            r["run"],
                            name,
                            k["first_s"],
                            k["second_s"],
                            k["sha"],
                            k["repeat_equal"],
                        ]
                    )

    summary: dict = {"env": json.loads((out / "env.json").read_text()), "series": {}, "hashes": {}}
    for key, rows in series.items():
        kernels = sorted(rows[0]["kernels"])
        distinct = {k: sorted({r["kernels"][k]["sha"] for r in rows}) for k in kernels}
        timed = rows[1:] if key.endswith("warm") else rows  # warm run 1 fills the cache
        summary["series"][key] = {
            "runs": len(rows),
            "llvm_host_cpu": sorted({r["llvm_host_cpu"] for r in rows}),
            "numba_cpu_name": sorted({r["numba_cpu_name"] for r in rows}),
            "all_repeats_equal": all(
                k["repeat_equal"] for r in rows for k in r["kernels"].values()
            ),
            "distinct_hashes_per_kernel": {k: len(v) for k, v in distinct.items()},
            "deterministic": all(len(v) == 1 for v in distinct.values()),
            "import_s": stats([r["import_s"] for r in timed]),
            "first_calls_total_s": stats([r["first_calls_total_s"] for r in timed]),
            "warmup_total_s": stats([r["warmup_total_s"] for r in timed]),
            "steady_second_call_total_s": stats(
                [sum(k["second_s"] for k in r["kernels"].values()) for r in timed]
            ),
        }
        summary["hashes"][key] = {k: v[0] if len(v) == 1 else v for k, v in distinct.items()}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                k: {"deterministic": v["deterministic"], "warmup_total_s": v["warmup_total_s"]}
                for k, v in summary["series"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
