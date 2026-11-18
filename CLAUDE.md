# CLAUDE.md — Jude (cranial remolding helmet CAD)

Jude is a web-based, mesh-based CAD tool. A clinic technician imports a 3D head scan, sets anatomy (landmarks, frame), measures, edits the helmet positive mould with recorded operations, reviews, approves and exports a binary STL + manifest for downstream manufacturing. First user: Saigak Orto (Kazakhstan). It is a CAD platform first.

## Intended-use boundary (never cross)
- The software does NOT diagnose, decide treatment candidacy, prescribe a correction, guarantee fit or validate clinical outcomes (FR-045, FR-082, SAF-02, STK-05, NFR-06).
- No clinical, threshold, correction-magnitude or production value is ever defaulted in code. Such keys are NOT_SET until the clinic configures them (DEC-029). Test-only configs carry `test_only` and cannot reach production (FN-CFG-07).
- Do not write UI text or comments that sound like diagnosis ("abnormal", "needs treatment", "severe", "corrected"). A wording lint exists; keep it green.
- Geometry checks passing is not evidence of clinical safety.

## Data safety
- NEVER commit secrets or patient data. No real scans in any session or repo. Synthetic fixtures only (T1–T15) until the VER-22 record exists (SEC-17, EXT-01).
- Do not paste real patient data into prompts.

## Architecture in one paragraph
Next.js UI + three.js viewer → same-origin Caddy proxy → FastAPI domain API → Postgres job queue (SKIP LOCKED) → Python geometry worker → pure-function kernel (K01 io, K02 validate, K03 frames, K04 anchors, K05 measure, K06 ops, K07 compare, K08 replay, K09 export). Supabase Postgres + Storage. Design = op-log with deterministic replay. Approval and export are bound to SHA-256 hashes. Audit is a hash chain. Own session auth (argon2id). Details: `docs/design/TECHNICAL_DESIGN_v1.0.md`.

## Kernel rules (DEVELOPMENT_STANDARDS §5)
- `packages/kernel` is pure: arrays + explicit params in, `OpResult` out (contract IF-03). No I/O, clock, randomness, global state, network.
- float64, millimetres. Deterministic ordering everywhere. numba: fastmath off, parallel off.
- Exact predicates (own Shewchuk port) and ONE shared deterministic BVH. libigl/trimesh/CGAL/PyMeshLab are CI oracles only, never imported by shipped code.
- Tolerances: DEC-025 (e = 0.011 mm, perimeter 0.032 mm, file fidelity 1e-4 mm). No ad-hoc epsilons.
- Every op has a registry entry with `op_version`; changing behaviour means a version bump.
- A kernel task (TT-K) is verified by a separate verification task (TT-V). Do not mark K done without its V.

## Identifiers
- Task: `TSK-<MOD>-<NN>-<T>` (T = K/V/B/U/J/A/O/C) or `XC-<GRP>-<NN>`. Function: `FN-…`. Requirement: `FR-/NFR-/SEC-/SAF-/DATA-/INT-/VER-…`. Decision: `IDR-nn`. Open decision: `OD-nn`. IDs are never reused.
- Source of truth for scope and order: `docs/plan/WORK_BREAKDOWN_STRUCTURE_v1.1.csv` and `docs/plan/TASK_DEPENDENCY_MATRIX_v1.1.csv`. Decisions: `docs/plan/IMPLEMENTATION_PLAN_v1.1.md` §6.

## Working rules
1. One task ID per branch and per PR. Branch: `<type>/<TASK-ID>-short-name`. Trunk-based, short-lived branches.
2. Commit messages: Conventional Commits + trailer `Task: <TASK-ID>`.
3. PR description lists: task ID, function ID(s), requirement ID(s), test IDs.
4. Do not start a task whose dependencies (TASK_DEPENDENCY_MATRIX) are not Done. Do not start a task of a later milestone.
5. Definition of done: DoD-STD + the type-specific DoD (DEVELOPMENT_STANDARDS §11): code + unit/property tests + docs + CI green + review.
6. TT-V (geometry verification) PRs need a human reviewer who did not write the K task.
7. Human-only tasks (do not do them yourself, prepare drafts and stop): XC-FND-01 (countersign decisions), XC-FND-10 (document updates needing owner sign-off), anything on the EXT-01…07 list (privacy inspection, clinic data, legal review, hardware access).
8. If a requirement is unclear or conflicts with a decision, stop and ask. Do not invent clinical rules.

## Commands
- Stack: `just up` (= `cp .env.example .env` + `docker compose up --build --detach --wait`) · `just smoke` (all health endpoints 200) · `just down` / `just reset`
- Python: `uv sync --locked` · `uv run pytest` · `uv run ruff check` · `uv run ruff format --check` · `uv run mypy` (strict, all packages) · `uv run lint-imports` (layer contracts)
- Web: `pnpm install --frozen-lockfile` · `pnpm build` · `pnpm lint` · `pnpm format:check` · `pnpm typecheck`
- Database: `jude-migrate upgrade` (forward-only Alembic; the compose `migrate` service runs it) · `just test-int` (integration tests on a throwaway Postgres) · `just migrate-sql` · schema and grants: `services/api/SCHEMA.md`
- CI: `just ci <stage>` runs a stage exactly as CI (lint, unit, determinism, contract, integration, smoke; nightly: oracle, security, e2e, performance) · `just ci-selftest` · seed a failure with `JUDE_CI_SEED=<stage>` · `main` is protected (PR-only, required checks, applies to admins) · record: `docs/ops/CI_PIPELINE.md`
- All gates: `just lint` · autofix `just fmt` · seeded-violation self-test `just lint-selftest` · git hooks `just hooks` (pre-commit + commit-msg/commitlint)
- Lint rules (XC-FND-04, EL decision 2026-11-17 in place of the missing DEVELOPMENT_STANDARDS §2–4): ruff E/F/W/I/B/UP/N/S/RUF, line length 100; kernel also bans print, numpy.random, and (tools/archlint) open/input/exec/eval/compile/__import__. Commit messages: Conventional Commits + exactly one `Task: <ID>` trailer that exists in the WBS.
- Toolchain: Python 3.12, uv 0.10.6, Node 26.13.1 LTS, pnpm 12.21.0 (Node ≥ 25 has no corepack: `npm i -g pnpm@12.21.0`), just via `uv tool install rust-just`. Images linux/amd64, base images pinned by digest.
- Geometry regression/golden hashes: see `docs/plan/DEVELOPMENT_TEST_PLAN_v1.1.md`

## Docs layout
- `docs/plan/` — implementation plan, MVP scope, roadmap, WBS, dependency matrix, repo structure, standards, test plan, risk register, change notice CN-2026-11-17.
- `docs/design/` — Functional Spec, Function Catalog, Technical Design set, Algorithm Catalog, Library Comparison, Geometry Testing Strategy, RTM.
- `docs/adr/` — new architecture decisions (Proposed → Accepted by engineering lead).

## Current state
Milestone M0. First queue: XC-FND-01 (human) → XC-FND-02 → XC-FND-04 → XC-FND-05 → XC-FND-12 → XC-FND-10 (human) → XC-EXP-08 → XC-FND-03 → XC-FND-11 → XC-SHR-01.
Update this section at every milestone exit.
