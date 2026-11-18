#!/usr/bin/env bash
# CI self-test (XC-FND-03, TT-C "seeded violation fails the stage"): every stage run with
# JUDE_CI_SEED=<stage> must exit non-zero, and must fail because of the seed (the output
# names it). Clean runs are the regular stage jobs. `smoke` is seeded in the demonstration
# PR recorded in docs/ops/CI_PIPELINE.md (it needs the full compose stack).
# Usage: bash scripts/ci/selftest.sh [stage ...]   (integration needs JUDE_TEST_ADMIN_URL)
set -uo pipefail

STAGES=("$@")
[[ ${#STAGES[@]} -gt 0 ]] || STAGES=(lint unit determinism contract integration oracle security e2e performance)
HERE="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${JUDE_CI_REPORTS:-reports}/selftest"
mkdir -p "$LOG_DIR"
fail=0

for stage in "${STAGES[@]}"; do
  log="$LOG_DIR/$stage.log"
  JUDE_CI_SEED="$stage" JUDE_CI_REPORTS="$LOG_DIR" bash "$HERE/stage.sh" "$stage" >"$log" 2>&1
  code=$?
  if [[ $code -eq 0 ]]; then
    echo "FAIL  $stage: seeded run passed (gate does not fail)"; fail=1
  elif grep -qE "seeded failure for CI stage '$stage'|jude_kernel[._/]_ci_seed" "$log"; then
    echo "ok    $stage: seeded run failed (exit $code) because of the seed"
  else
    echo "FAIL  $stage: seeded run failed (exit $code) but not because of the seed"; fail=1
    tail -20 "$log"
  fi
done

[[ $fail -eq 0 ]] && echo "ci-selftest: every seeded stage fails" || echo "ci-selftest: FAILED" >&2
exit $fail
