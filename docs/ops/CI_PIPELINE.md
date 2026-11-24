# CI pipeline and branch protection record

| Field | Value |
|---|---|
| Task | XC-FND-03 — CI pipeline with staged quality gates |
| Requirements | VER-20, VER-07, SEC-09 · Ref BL-002 |
| Sources | GEOMETRY_TESTING_STRATEGY_v1.0 §7, DEVELOPMENT_TEST_PLAN_v1.1 §5 |
| Workflows | `.github/workflows/ci.yml` (merge stages), `nightly.yml` (release and report stages), `x08.yml` (experiment) |
| Entry point | `bash scripts/ci/stage.sh <stage>`, or `just ci <stage>`. CI and local runs use the same command |

## 1. Stages

| Stage | Workflow / job | Runs | Blocks | Content today | Content added by |
|---|---|---|---|---|---|
| lint | ci / `lint` | every PR, push to main | merge | ruff, ruff format, `mypy --strict`, import-linter, kernel builtins, eslint, prettier, tsc, commitlint | TSK-OPS-01-C (wording/localisation lint, VER-09); schema checks |
| unit | ci / `unit` | every PR, push to main | merge | unit and property tests (kernel, API, worker, storage fake); coverage report (`reports/coverage.xml`) | every K/B/A/J task; web component tests start with the first TT-U task |
| determinism | ci / `determinism` | every PR, push to main | merge | jude-arr/1 golden bytes and bit-exact round trips (`-m determinism`) | TSK-OPS-04-C (T9 golden hashes, 100-run determinism nightly) |
| contract | ci / `contract` | every PR, push to main | merge | `openapi.json` matches the code; no breaking change against the base commit (`tools/contract/oacompat.py`); TS client regenerates to the committed bytes; `-m contract` tests; audit immutability: no `/audit*` mutate path in contract, routes, HTTP probe or shipped SQL (`tools/contract/audit_immutability.py`, TSK-AUD-06-C) | XC-FND-06 (done); JSON Schema of stored documents joins with their tasks |
| integration | ci / `integration` | every PR, push to main | merge | schema, grant and service tests on a fresh Postgres (`-m integration`), incl. the audit immutability catalogue check (TSK-AUD-06-C) | every TT-B/TT-J task (VER-12 permissions, VER-13 audit) |
| smoke | ci / `smoke` | every PR, push to main | merge | `docker compose up` + every health endpoint 200 | XC-FND-11 (readiness) |
| ci-selftest | ci / `ci-selftest` | every PR, push to main | merge | 25 seeded lint violations (XC-FND-04) and a seeded failure in each stage | — |
| oracle | nightly / `oracle` | nightly 02:17 UTC, dispatch, tags `v*` | release | gate only (`-m oracle`) | TSK-OPS-07-C (oracle container) |
| security | nightly / `security` | nightly, dispatch, tags | release | gate only (`-m security`) | TSK-OPS-02-C (licence allow-list, SOUP), TSK-OPS-03-C (CVSS ≥ 7.0, SD-04), TSK-OPS-12-C |
| e2e | nightly / `e2e` | nightly, dispatch, tags | release | gate only (`-m e2e`) | TSK-OPS-08-C (Playwright UC-02…UC-10) |
| performance | nightly / `performance` | nightly, dispatch, tags | report only (`continue-on-error`) | gate only (`-m performance`) | XC-EXP-BM01 (BM-01 trend); budgets from XC-PLT-03 |

"Gate only" means the stage runs, collects its seeded test and goes green or red; the owning task adds the real content to that stage's branch in `stage.sh`. A stage is never removed to make a build pass.

## 2. Seeded failures

`JUDE_CI_SEED=<stage>|all` makes a stage fail through its real path:

- `lint`: a kernel module importing `os` is written into the tree; import-linter breaks the contract `kernel-pure`.
- `unit`, `determinism`, `contract`, `integration`, `oracle`, `security`, `e2e`, `performance`: a test in `tools/ci_selftest/tests/` that carries the stage marker fails instead of skipping.
- `smoke`: the worker is stopped after the stack starts, so its health check fails.

The `ci-selftest` job runs `scripts/ci/selftest.sh` on every PR. It checks that each stage exits non-zero *because of* its seed, by matching the stage's output.

A demonstration PR containing the file `.github/ci-seed` (one line: a stage name or `all`) seeds every job of that PR. It must never be merged, and the required checks make sure it cannot be. The evidence is in §5.

## 3. Branch protection on `main` (settings record)

Applied on 2026-11-19 through the GitHub API (`PUT /repos/Ayau1ym335/jude1/branches/main/protection`), as decided by the engineering lead / product owner on 2026-11-19:

- required checks, yes;
- required review, no (single developer);
- applies to administrators, yes.

| Setting | Value |
|---|---|
| Required status checks | `lint`, `unit`, `determinism`, `contract`, `integration`, `smoke`, `ci-selftest` |
| Require branch up to date (`strict`) | true |
| Enforce for administrators | true |
| Required pull-request reviews | none |
| Allow force pushes / deletions | false / false |
| Linear history, conversation resolution | not required |

Before XC-FND-03, the required checks were the job names of the earlier workflows: `python`, `web`, `commits`, `seeded violations fail each gate`, `smoke`, `migrations`. They were replaced by the list above when this pipeline merged.

## 4. Artefact retention

| Artefact | Retention |
|---|---|
| `unit-reports` (JUnit + `coverage.xml`), `determinism-reports`, `integration-reports` | 30 days |
| `smoke-logs` (only on failure), `ci-selftest-logs` | 14 days |
| `nightly-<stage>-reports` | 90 days |
| `x08-ci` (experiment) | 90 days |

## 5. Pipeline time and seeded-failure evidence

### 5.1 Pipeline time

Merge stages, `ci.yml` run 44411616233 on `main` @ 8722e0c (merge of PR #9), 2026-11-18 22:26:36 → 22:27:43 UTC, GitHub-hosted `ubuntu-24.04`. Jobs run in parallel.

| Job | Duration | Target (DEVELOPMENT_TEST_PLAN §5) |
|---|---|---|
| lint | 29 s | ≤ 5 min |
| unit | 21 s | ≤ 10 min |
| determinism | 22 s | ≤ 10 min (PR) |
| contract | 15 s | ≤ 2 min |
| integration | 32 s | ≤ 15 min |
| smoke | 65 s | — |
| ci-selftest | 59 s | — |
| **Whole pipeline (wall clock)** | **67 s** | |

Release and report stages, `nightly.yml` run 44411663717 (manual dispatch on `main`), 2026-11-18 22:26:56 → 22:27:23 UTC, green:

| Job | Duration |
|---|---|
| oracle | 21 s |
| security | 22 s |
| e2e | 16 s |
| performance | 21 s |

The release stages hold only their gates so far (§1); their times grow as the owning tasks add content.

### 5.2 A seeded failure in each stage blocks the merge

Demonstration PR #10 (`.github/ci-seed` = `all`), `ci.yml` run 44411699434:

| Stage | Result | Cause seen in the job log |
|---|---|---|
| lint | fail | import-linter: `jude_kernel._ci_seed -> os` (contract `kernel-pure` broken) |
| unit | fail | `seeded failure for CI stage 'unit'` |
| determinism | fail | `seeded failure for CI stage 'determinism'` |
| contract | fail | `seeded failure for CI stage 'contract'` |
| integration | fail | `seeded failure for CI stage 'integration'` |
| smoke | fail | `FAIL worker` (worker stopped after `compose up`) |
| ci-selftest | pass | expected: it seeds each stage itself and checks that each one fails |

- GitHub reported `mergeStateStatus = BLOCKED`.
- `gh pr merge 10 --merge` was refused: "the base branch policy prohibits the merge".
- PR #10 was closed unmerged and its branch deleted.

The release stages (oracle, security, e2e) and performance are checked on every PR by `ci-selftest`, which runs `scripts/ci/selftest.sh`. Each one exits non-zero on its own seed.

### 5.3 A breaking API change blocks the merge (XC-FND-06)

Demonstration PR #19 removed the response field `service` from `GET /api/v1/health`. It regenerated `openapi.json` and the TypeScript client and updated the unit tests, so only the contract rule could stop it.

| Check | Result |
|---|---|
| `contract` (run 45020329537) | **fail**: `BREAKING GET /api/v1/health response 200 application/json.service: response field removed`, against base `d68e338` |
| `lint`, `unit`, `determinism`, `integration`, `smoke`, `ci-selftest` | pass |

- GitHub reported `mergeStateStatus = BLOCKED`.
- `gh pr merge 19 --merge` was refused: "the base branch policy prohibits the merge".
- PR #19 was closed unmerged and its branch deleted.

The client regenerates deterministically. The `contract` stage regenerates `src/schema.d.ts` on the Linux runner and diffs it against the file committed from Windows (PR #18: identical).
