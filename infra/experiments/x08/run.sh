#!/usr/bin/env bash
# XC-EXP-08 runner. Usage: run.sh <out_dir> [builds=3] [runs=20]
# Produces in <out_dir>: env.json, builds.csv, smoke.jsonl, soup.json, summary.json, soup.csv
# Build timings are "--no-cache" builds with the pinned base image already pulled.
set -euo pipefail

OUT="$1"
BUILDS="${2:-3}"
RUNS="${3:-20}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TAG="jude-x08:exp"
mkdir -p "$OUT"
PY="${PYTHON:-python3}"

now() { "$PY" -c "import time; print(time.perf_counter())"; }
elapsed() { "$PY" -c "print(round($2 - $1, 3))"; }

echo "run,seconds" > "$OUT/builds.csv"
for i in $(seq 1 "$BUILDS"); do
  t0=$(now)
  docker build --quiet --no-cache --platform linux/amd64 -t "$TAG" "$HERE" >/dev/null
  t1=$(now)
  echo "$i,$(elapsed "$t0" "$t1")" >> "$OUT/builds.csv"
  echo "build $i done"
done

image_id=$(docker image inspect --format '{{.Id}}' "$TAG")
image_size=$(docker image inspect --format '{{.Size}}' "$TAG")
cpu_model=$(docker run --rm --platform linux/amd64 --entrypoint sh "$TAG" -c \
  "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'")
docker info --format '{"docker_os":"{{.OperatingSystem}}","kernel":"{{.KernelVersion}}","ncpu":{{.NCPU}},"mem_bytes":{{.MemTotal}},"server_version":"{{.ServerVersion}}","arch":"{{.Architecture}}"}' > "$OUT/docker_info.json"
"$PY" - "$OUT" "$image_id" "$image_size" "$cpu_model" <<'PY'
import json, sys
out, image_id, size, cpu = sys.argv[1:5]
info = json.load(open(f"{out}/docker_info.json"))
info.update({"image_id": image_id, "image_size_bytes": int(size), "cpu_model": cpu.strip()})
json.dump(info, open(f"{out}/env.json", "w"), indent=2)
PY
rm "$OUT/docker_info.json"

: > "$OUT/smoke.jsonl"
for i in $(seq 1 "$RUNS"); do
  t0=$(now)
  # MSYS_NO_PATHCONV: stops Git Bash on Windows rewriting /tmp into a Windows path (no-op on Linux)
  line=$(MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --network none --read-only --tmpfs /tmp "$TAG" smoke)
  t1=$(now)
  "$PY" - "$line" "$i" "$(elapsed "$t0" "$t1")" >> "$OUT/smoke.jsonl" <<'PY'
import json, sys
row = json.loads(sys.argv[1]); row["run"] = int(sys.argv[2]); row["container_wall_s"] = float(sys.argv[3])
print(json.dumps(row, ensure_ascii=False))
PY
done

docker run --rm --platform linux/amd64 --network none "$TAG" soup > "$OUT/soup.json"
"$PY" "$HERE/summarize.py" "$OUT"
