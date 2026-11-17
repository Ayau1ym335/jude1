# Jude

Jude is a web-based, mesh-based CAD tool for cranial remolding helmet positive moulds. A clinic technician imports a 3D head scan, sets landmarks and the anatomical frame, measures, edits the mould with recorded and replayable operations, reviews and approves the design, and exports a binary STL with a manifest for manufacturing.

**Intended-use boundary.** Jude does not diagnose, decide treatment candidacy, prescribe a correction, guarantee fit or validate clinical outcomes. Geometry checks passing is not evidence of clinical safety. See [CLAUDE.md](CLAUDE.md) and `docs/plan/MVP_SCOPE_v1.1.md`.

**Data rule.** Use synthetic fixtures only. Never commit or load real scans or patient data (SEC-17, EXT-01).

## Repository layout

| Path | What it is |
|---|---|
| `apps/web/` | Next.js UI and three.js viewer. Feature modules go in `src/features/<mod>`. |
| `services/api/` | FastAPI domain API under `/api/v1` (package `jude_api`). |
| `services/worker/` | Geometry worker: Postgres job queue → kernel via IF-03 (package `jude_worker`). |
| `packages/kernel/` | Pure geometry kernel K01–K09 (package `jude_kernel`). No I/O, clock, randomness or network. |
| `packages/contracts/` | OpenAPI contract and generated TypeScript client (XC-FND-06). |
| `tools/storage_fake/` | Content-addressed blob store for dev and tests only, in place of Supabase Storage. Never deployed. |
| `infra/` | Caddy config and the shared Python Dockerfile. |
| `scripts/` | Developer scripts (`smoke.sh`). |
| `docs/` | Plan, design and decision records. The source of truth for scope is `docs/plan/`. |

Python is a **uv** workspace (`pyproject.toml`, `uv.lock`). JS is a **pnpm** workspace (`pnpm-workspace.yaml`, `pnpm-lock.yaml`). Python 3.12 and Node 26 LTS, with images built for linux/amd64 only (IDR-09).

## Local stack

```
proxy (Caddy, :8080) ─┬─ /api/*  → api (FastAPI :8000) ─┬─ postgres (17)
                      └─ /*      → web (Next.js :3000)   └─ storage-fake (:9000)
                                   worker (:8001 health) ─┴─ postgres, storage-fake
```

Only the proxy is published on the host, at `127.0.0.1:8080`. Everything else is internal to the compose network.

### Prerequisites

- Docker with Compose v2
- [uv](https://docs.astral.sh/uv/) 0.10.6
- Node 26.13.1 (`.nvmrc`) and pnpm 12.21.0 (`npm i -g pnpm@12.21.0`). Node ≥ 25 no longer ships corepack. You need these only for working on the web app outside Docker.
- [just](https://github.com/casey/just) (`uv tool install rust-just`) and bash (Git Bash on Windows)

### Commands

| Command | Does |
|---|---|
| `just up` | Creates `.env` from `.env.example` if it is missing, builds the images, starts all services and waits until every one is healthy. |
| `just smoke` | Checks every health endpoint. Exits non-zero unless all of them return 200. |
| `just ci-smoke` | Runs `up` and `smoke`, and dumps the logs on failure. This is what CI runs. |
| `just down` / `just reset` | Stops the stack. `reset` also deletes the database and blob volumes. |
| `just logs [service]` | Follows the logs. |
| `just sync` | Installs Python and JS dependencies from the lockfiles. |
| `just test` | Runs the Python unit tests (`uv run pytest`). |
| `just lint` | Runs every coding-standard and architecture gate, the same as CI. |
| `just fmt` | Applies the ruff fixes and formatting, and prettier. |
| `just lint-selftest` | Checks that every gate rejects a seeded violation and accepts its clean counterpart. |
| `just hooks` | Installs the git hooks: pre-commit runs the lint gates, commit-msg runs commitlint. |

Without `just`: `cp .env.example .env && docker compose up --build --detach --wait`, then `bash scripts/smoke.sh`.

### Health endpoints

| Service | Endpoint | Reached via |
|---|---|---|
| proxy | `GET /proxy-healthz` | `http://127.0.0.1:8080/proxy-healthz` |
| web | `GET /healthz` | `http://127.0.0.1:8080/healthz` |
| api | `GET /api/v1/health` (503 if Postgres is unreachable) | `http://127.0.0.1:8080/api/v1/health` |
| worker | `GET /healthz` on :8001 (503 if Postgres is unreachable) | inside the container |
| storage-fake | `GET /healthz` on :9000 | inside the container |
| postgres | `pg_isready` | inside the container |

## CI

There are two workflows. The staged quality-gate pipeline and branch protection come with XC-FND-03.

- `.github/workflows/smoke.yml` checks that `uv.lock` is in sync, runs the unit tests, starts the stack and runs `scripts/smoke.sh`.
- `.github/workflows/lint.yml` runs four jobs:
  - **python:** ruff, format check, `mypy --strict` and import-linter.
  - **web:** eslint, prettier and `tsc`.
  - **commits:** commitlint.
  - **selftest:** checks that seeded violations fail every gate.

### Layer rules

These are enforced by import-linter, ruff, `tools/archlint` and eslint:

| Rule | Enforced by |
|---|---|
| The kernel (`jude_kernel`) does no file, OS or network I/O, reads no clock, uses no randomness, starts no threads and accesses no DB. It does not use `print`, `open`, `exec`, `eval`, `__import__` or `numpy.random`. | import-linter `kernel-pure`, ruff TID251/T201, `tools/archlint/kernel_builtins.py` |
| The kernel does not import api, worker or storage-fake. | `kernel-leaf` |
| api and worker never import the dev-only storage fake. | `no-dev-fakes-in-services` |
| api and worker do not import each other. They communicate through the Postgres job queue. | `api-worker-independent` |
| The web UI never imports the kernel. It uses the `/api/v1` contract. | eslint `no-restricted-imports` |

## Working rules

Use one task ID per branch and per PR (`<type>/<TASK-ID>-short-name`). Write Conventional Commits with a `Task: <TASK-ID>` trailer. The full rules are in [CLAUDE.md](CLAUDE.md).
