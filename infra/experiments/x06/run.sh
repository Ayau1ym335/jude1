#!/usr/bin/env bash
# XC-EXP-06 runner. Usage: run.sh <image> <out_dir> [runs=100]
# For CPU in {host, generic} x CACHE in {cold, warm}: <runs> fresh processes inside one
# read-only, network-less container. Writes series-<cpu>-<cache>.jsonl and env.json.
set -euo pipefail

IMAGE="$1"
OUT="$2"
RUNS="${3:-100}"
PY="${PYTHON:-python3}"
mkdir -p "$OUT"

for cpu in host generic; do
  for cache in cold warm; do
    echo "series $cpu/$cache ($RUNS runs)"
    # MSYS_NO_PATHCONV: stops Git Bash on Windows rewriting /tmp (no-op on Linux)
    MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --network none --read-only \
      --tmpfs /tmp:rw,exec,size=512m "$IMAGE" series "$RUNS" "$cpu" "$cache" \
      > "$OUT/series-$cpu-$cache.jsonl"
  done
done

image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE")
cpu_model=$(MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --entrypoint sh "$IMAGE" -c \
  "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'")
docker info --format '{"docker_os":"{{.OperatingSystem}}","kernel":"{{.KernelVersion}}","ncpu":{{.NCPU}},"mem_bytes":{{.MemTotal}},"arch":"{{.Architecture}}"}' > "$OUT/docker_info.json"
"$PY" - "$OUT" "$image_id" "$cpu_model" <<'PY'
import json, sys
out, image_id, cpu = sys.argv[1:4]
info = json.load(open(f"{out}/docker_info.json"))
info.update({"image_id": image_id, "cpu_model": cpu.strip()})
json.dump(info, open(f"{out}/env.json", "w"), indent=2)
PY
rm "$OUT/docker_info.json"
"$PY" "$(dirname "$0")/summarize.py" "$OUT"
