#!/usr/bin/env bash
# XC-EXP-06 runner for a workstation: same series as run.sh, but all four run sequentially
# inside ONE detached container that writes to a bind-mounted directory, so the run survives
# the terminal (or agent session) that started it. Collect with: run_detached.sh collect <out>
#   run_detached.sh start   <image> <out_dir> [runs=100]
#   run_detached.sh collect <image> <out_dir>      (after the container has exited)
set -euo pipefail

MODE="$1"
IMAGE="$2"
OUT="$3"
RUNS="${4:-100}"
NAME=jude-x06-detached
PY="${PYTHON:-python3}"

case "$MODE" in
  start)
    mkdir -p "$OUT"
    # Docker Desktop on Windows needs a Windows path (pwd -W in Git Bash); plain pwd elsewhere.
    host_out=$(cd "$OUT" && { pwd -W 2>/dev/null || pwd; })
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    MSYS_NO_PATHCONV=1 docker run -d --name "$NAME" --platform linux/amd64 --network none \
      --read-only --tmpfs /tmp:rw,exec,size=512m -v "$host_out:/out" --entrypoint sh "$IMAGE" -c "
        for cpu in host generic; do for cache in cold warm; do
          python /opt/x06/probe.py series $RUNS \$cpu \$cache > /out/series-\$cpu-\$cache.jsonl.part \
            && mv /out/series-\$cpu-\$cache.jsonl.part /out/series-\$cpu-\$cache.jsonl
        done; done"
    ;;
  collect)
    test "$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$NAME")" = "exited 0"
    for s in host-cold host-warm generic-cold generic-warm; do
      test "$(wc -l < "$OUT/series-$s.jsonl")" -ge 1
    done
    image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE")
    cpu_model=$(MSYS_NO_PATHCONV=1 docker run --rm --platform linux/amd64 --entrypoint sh "$IMAGE" -c \
      "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'")
    docker info --format '{"docker_os":"{{.OperatingSystem}}","kernel":"{{.KernelVersion}}","ncpu":{{.NCPU}},"mem_bytes":{{.MemTotal}},"arch":"{{.Architecture}}"}' > "$OUT/docker_info.json"
    "$PY" - "$OUT" "$image_id" "$cpu_model" <<'PY'
import json, sys
out, image_id, cpu = sys.argv[1:4]
info = json.load(open(f"{out}/docker_info.json"))
info.update({"image_id": image_id, "cpu_model": cpu.strip(), "runner": "run_detached.sh"})
json.dump(info, open(f"{out}/env.json", "w"), indent=2)
PY
    rm "$OUT/docker_info.json"
    docker rm "$NAME" >/dev/null
    "$PY" "$(dirname "$0")/summarize.py" "$OUT"
    ;;
  *) echo "usage: run_detached.sh start|collect <image> <out_dir> [runs]" >&2; exit 2 ;;
esac
