#!/usr/bin/env bash
# Smoke test for the local stack (XC-FND-02 completion criterion):
# every service's health endpoint must answer HTTP 200.
# Expects the stack to be up: docker compose up --build --wait
set -euo pipefail

PORT="${JUDE_HTTP_PORT:-8080}"
BASE="http://127.0.0.1:${PORT}"
fail=0

check_http() {  # name url
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$2" || true)"
  if [[ "$code" == "200" ]]; then
    printf 'ok    %-13s %s\n' "$1" "$2"
  else
    printf 'FAIL  %-13s %s -> %s\n' "$1" "$2" "${code:-no response}"
    fail=1
  fi
}

check_internal() {  # service url — services not published on the host are probed from inside their container
  if docker compose exec -T "$1" python -c \
      "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('$2', timeout=5).status == 200 else 1)" \
      >/dev/null 2>&1; then
    printf 'ok    %-13s %s (in container)\n' "$1" "$2"
  else
    printf 'FAIL  %-13s %s (in container)\n' "$1" "$2"
    fail=1
  fi
}

check_http proxy "${BASE}/proxy-healthz"
check_http web "${BASE}/healthz"
check_http api "${BASE}/api/v1/health"
check_internal worker "http://127.0.0.1:8001/healthz"
check_internal storage-fake "http://127.0.0.1:9000/healthz"

if docker compose exec -T postgres pg_isready -U jude -d jude >/dev/null 2>&1; then
  printf 'ok    %-13s pg_isready\n' postgres
else
  printf 'FAIL  %-13s pg_isready\n' postgres
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "smoke: FAILED" >&2
  exit 1
fi
echo "smoke: all services healthy"
