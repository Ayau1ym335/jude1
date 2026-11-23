#!/usr/bin/env bash
# One entry point per CI stage (XC-FND-03, GEOMETRY_TESTING_STRATEGY §7,
# DEVELOPMENT_TEST_PLAN §5). CI jobs and local runs call the same command:
#
#   bash scripts/ci/stage.sh <stage>        (or: just ci <stage>)
#
# Merge-blocking: lint, unit, determinism, contract, integration, smoke
# Release-blocking (nightly): oracle, security, e2e     Report-only: performance
#
# Tasks that own a stage's content extend its branch below (see docs/ops/CI_PIPELINE.md).
# JUDE_CI_SEED=<stage>|all injects a seeded failure through the stage's real path; the
# stage must then fail (scripts/ci/selftest.sh checks this).
set -euo pipefail

STAGE="${1:?usage: stage.sh <stage>}"
SEED="${JUDE_CI_SEED:-}"
REPORTS="${JUDE_CI_REPORTS:-reports}"
mkdir -p "$REPORTS"

seeded() { [[ "$SEED" == "$STAGE" || "$SEED" == "all" ]]; }

# Every other stage's marker, so `unit` runs exactly the unmarked tests.
NON_UNIT="lint_selftest or integration or determinism or contract or oracle or security or e2e or performance"

run_pytest() {  # <marker expression> [extra pytest args...]
  uv run --frozen pytest -p no:cacheprovider -m "$1" --junitxml="$REPORTS/$STAGE.xml" "${@:2}"
}

case "$STAGE" in
  lint)
    # Wording/localisation lint (FN-OPS-01) joins here with TSK-OPS-01-C.
    if seeded; then
      seed_file="packages/kernel/src/jude_kernel/_ci_seed.py"
      printf 'import os\n\nSEEDED = os.sep\n' > "$seed_file"   # violates kernel purity
      trap 'rm -f "$seed_file"' EXIT
    fi
    uv run --frozen ruff check
    uv run --frozen ruff format --check
    uv run --frozen mypy
    uv run --frozen lint-imports --no-cache
    uv run --frozen python tools/archlint/kernel_builtins.py
    pnpm --filter @jude/web lint
    pnpm --filter @jude/web format:check
    pnpm --filter @jude/web typecheck
    pnpm --filter @jude/contracts format:check
    pnpm --filter @jude/contracts typecheck
    ;;
  unit)
    # Coverage is reported now; the thresholds of DEVELOPMENT_TEST_PLAN §6 apply from M1/M2.
    run_pytest "not ($NON_UNIT)" \
      --cov=jude_kernel --cov=jude_api --cov=jude_worker --cov=jude_storage_fake \
      --cov-report=term --cov-report="xml:$REPORTS/coverage.xml"
    ;;
  determinism)  # T9 golden hashes + 100-run determinism join with TSK-OPS-04-C
    run_pytest "determinism"
    ;;
  contract)     # XC-FND-06: OpenAPI contract of record + generated client (IF-01)
    # 1. openapi.json matches the API code.
    uv run --frozen jude-openapi --check
    # 2. No breaking change against the base (CI sets JUDE_CONTRACT_BASE; locally origin/main).
    base="${JUDE_CONTRACT_BASE:-}"
    if [[ -z "$base" ]] && git rev-parse --verify --quiet origin/main >/dev/null; then base=origin/main; fi
    if [[ -n "$base" ]]; then
      uv run --frozen python tools/contract/oacompat.py --base-ref "$base"
    else
      echo "contract: no base ref (set JUDE_CONTRACT_BASE): breaking-change check skipped"
    fi
    # 2b. Error catalogue error/1 (TSK-API-02-A): every FS/RTM code catalogued; codes stable.
    uv run --frozen python tools/contract/error_catalogue.py ${base:+--base-ref "$base"}
    # 2c. Audit event catalogue (TSK-AUD-01-A): every FS event type catalogued.
    uv run --frozen python tools/contract/audit_events.py
    # 3. The TypeScript client regenerates to the committed bytes.
    pnpm --filter @jude/contracts generate
    git diff --exit-code -- packages/contracts/src/schema.d.ts       || { echo "contract: src/schema.d.ts is stale; run pnpm --filter @jude/contracts generate" >&2; exit 1; }
    run_pytest "contract"
    ;;
  integration)  # needs JUDE_TEST_ADMIN_URL (disposable Postgres)
    run_pytest "integration"
    ;;
  smoke)
    [[ -f .env ]] || cp .env.example .env
    docker compose up --build --detach --wait --wait-timeout 300
    if seeded; then docker compose stop worker; fi
    bash scripts/smoke.sh
    ;;
  oracle)       # TSK-OPS-07-C: oracle container comparisons
    run_pytest "oracle"
    ;;
  security)     # TSK-OPS-02-C licences/SOUP, TSK-OPS-03-C CVSS >= 7.0 scan, TSK-OPS-12-C
    run_pytest "security"
    ;;
  e2e)          # TSK-OPS-08-C: Playwright UC-02..UC-10 on the browser matrix
    run_pytest "e2e"
    ;;
  performance)  # XC-EXP-BM01: BM-01 trend, report-only until XC-PLT-03 sets budgets
    run_pytest "performance"
    ;;
  *)
    echo "unknown stage: $STAGE" >&2
    exit 2
    ;;
esac
