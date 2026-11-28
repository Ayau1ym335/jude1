#!/usr/bin/env bash
# XC-EXP-01 runner. Usage: run.sh <image> <out_dir> [runs=100]
# <runs> fresh processes inside one read-only, network-less container (series.jsonl), one
# agreement/tie run (agree.json), the host description (env.json) and summary.json.
set -euo pipefail

IMAGE="$1"
OUT="$2"
RUNS="${3:-100}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"

# MSYS_NO_PATHCONV: stops Git Bash on Windows rewriting /tmp (no-op on Linux)
dock() {
  MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --network none --read-only \
    --tmpfs /tmp:rw,exec,size=512m "$IMAGE" "$@"
}
echo "series ($RUNS runs)"
dock series "$RUNS" > "$OUT/series.jsonl"
echo "agreement and ties"
dock agree > "$OUT/agree.json"

image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE")
cpu_model=$(MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --entrypoint sh "$IMAGE" -c \
  "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'")
versions=$(MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --entrypoint python "$IMAGE" -c \
  "import importlib.metadata as m, json; print(json.dumps({p: m.version(p) for p in ('numpy','numba','libigl','open3d-cpu','fast-simplification','meshoptimizer')}))")
docker info --format '{"docker_os":"{{.OperatingSystem}}","kernel":"{{.KernelVersion}}","ncpu":{{.NCPU}},"mem_bytes":{{.MemTotal}},"arch":"{{.Architecture}}"}' > "$OUT/docker_info.json"
"$PY" - "$OUT" "$image_id" "$cpu_model" "$versions" <<'PY'
import json, sys
out, image_id, cpu, versions = sys.argv[1:5]
info = json.load(open(f"{out}/docker_info.json"))
info.update({"image_id": image_id, "cpu_model": cpu.strip(), "versions": json.loads(versions)})
json.dump(info, open(f"{out}/env.json", "w"), indent=2)
PY
rm "$OUT/docker_info.json"
"$PY" "$(dirname "$0")/summarize.py" "$OUT"
