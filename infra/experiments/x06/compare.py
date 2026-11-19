"""Compare XC-EXP-06 results of two hosts: per series and kernel, is the output hash identical?

Usage: compare.py <host_a_dir> <host_b_dir>
  prints the comparison and writes <host_a_dir>/../cross_host.json
"""

import json
from pathlib import Path
import sys


def main(a: Path, b: Path) -> None:
    sa = json.loads((a / "summary.json").read_text(encoding="utf-8"))
    sb = json.loads((b / "summary.json").read_text(encoding="utf-8"))
    result: dict = {
        "hosts": {a.name: sa["env"], b.name: sb["env"]},
        "same_image": sa["env"]["image_id"] == sb["env"]["image_id"],
        "series": {},
    }
    for key in sorted(set(sa["hashes"]) & set(sb["hashes"])):
        per_kernel = {}
        for kernel in sorted(sa["hashes"][key]):
            ha, hb = sa["hashes"][key][kernel], sb["hashes"][key].get(kernel)
            per_kernel[kernel] = isinstance(ha, str) and ha == hb
        result["series"][key] = {"kernels_equal": per_kernel, "all_equal": all(per_kernel.values())}
    # host-specific vs generic code on the same host
    for host, s in ((a.name, sa), (b.name, sb)):
        h, g = s["hashes"].get("host-cold", {}), s["hashes"].get("generic-cold", {})
        result.setdefault("host_vs_generic", {})[host] = {
            k: h.get(k) == g.get(k) for k in sorted(h)
        }
    (a.parent / "cross_host.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
