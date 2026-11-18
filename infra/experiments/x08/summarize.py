"""Summarise an XC-EXP-08 run directory: median/p95 per measure, SOUP list as CSV."""

import csv
import json
from pathlib import Path
import statistics
import sys


def p95(values: list[float]) -> float:
    s = sorted(values)
    # nearest-rank p95
    return s[max(0, min(len(s) - 1, -(-95 * len(s) // 100) - 1))]


def main(out: Path) -> None:
    builds = [float(r["seconds"]) for r in csv.DictReader((out / "builds.csv").open())]
    lines = (out / "smoke.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    measures = sorted({k for r in rows for k, v in r.items() if k.endswith("_s")})
    summary = {
        "env": json.loads((out / "env.json").read_text()),
        "builds": {"n": len(builds), "median_s": statistics.median(builds), "p95_s": p95(builds)},
        "runs": len(rows),
        "all_runs_ok": all(r.get("all_ok") for r in rows),
        "measures": {
            m: {
                "median": round(statistics.median([r[m] for r in rows]), 6),
                "p95": round(p95([r[m] for r in rows]), 6),
            }
            for m in measures
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    soup = json.loads((out / "soup.json").read_text(encoding="utf-8"))
    with (out / "soup.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["kind", "name", "version", "licence"])
        w.writerow(["runtime", "CPython", soup["python"], "PSF-2.0"])
        for p in soup["packages"]:
            w.writerow(["python", p["name"], p["version"], p["licence"]])
        for name, version in soup["debian"]:
            w.writerow(["debian", name, version, "see /usr/share/doc/<pkg>/copyright"])
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
