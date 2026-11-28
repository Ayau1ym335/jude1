"""XC-EXP-01 cross-host comparison.

    python compare.py <host_a_dir> <host_b_dir> > cross_host.json

For every (library, phantom) output array: is the single hash of host A equal to the single
hash of host B? A group that was not deterministic on one host counts as different.
"""

import json
from pathlib import Path
import sys


def compare(a: Path, b: Path) -> dict:
    sa = json.loads((a / "summary.json").read_text())
    sb = json.loads((b / "summary.json").read_text())
    groups = {}
    for key in sorted(set(sa["groups"]) | set(sb["groups"])):
        ga, gb = sa["groups"].get(key), sb["groups"].get(key)
        if ga is None or gb is None:
            groups[key] = {"present_on_both": False}
            continue
        groups[key] = {
            f: ga["distinct_hashes"][f] == 1
            and gb["distinct_hashes"][f] == 1
            and ga["hash"][f] == gb["hash"][f]
            for f in ga["hash"]
        }
    same = sum(all(v.values()) for v in groups.values() if "present_on_both" not in v)
    return {"groups": groups, "groups_identical": same, "groups_total": len(groups)}


if __name__ == "__main__":
    print(json.dumps(compare(Path(sys.argv[1]), Path(sys.argv[2])), indent=1, sort_keys=True))
