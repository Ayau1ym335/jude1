# Jude developer commands. Run `just` to list them.
# Install just: `uv tool install rust-just` (or any package manager). Recipes need bash (Git Bash on Windows).
set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# Create .env from the example if it does not exist (local dev values only)
env:
    @test -f .env || cp .env.example .env

# Build images and start the whole stack; waits until every service is healthy
up: env
    docker compose up --build --detach --wait --wait-timeout 300

# Stop the stack (keeps volumes)
down:
    docker compose down

# Stop the stack and delete local volumes (database, blobs)
reset:
    docker compose down --volumes

# Probe every health endpoint (stack must be up)
smoke:
    bash scripts/smoke.sh

# Start, smoke-test, and print logs on failure — what the CI smoke job runs
ci-smoke: up
    bash scripts/smoke.sh || (docker compose logs --no-color; exit 1)

# Follow logs of all services or one: `just logs api`
logs *service:
    docker compose logs --follow {{service}}

# Install Python (uv) and JS (pnpm) dependencies from the lockfiles
sync:
    uv sync --locked
    pnpm install --frozen-lockfile

# Python unit tests
test:
    uv run pytest

# All coding-standard and architecture gates — same as the CI lint workflow
lint: lint-py lint-web

# Python: ruff, format check, mypy --strict, import-linter layer contracts, kernel builtins
lint-py:
    uv run --frozen ruff check
    uv run --frozen ruff format --check
    uv run --frozen mypy
    uv run --frozen lint-imports --no-cache
    uv run --frozen python tools/archlint/kernel_builtins.py

# Web: eslint (incl. "UI never imports kernel"), prettier check, tsc --noEmit
lint-web:
    pnpm --filter @jude/web lint
    pnpm --filter @jude/web format:check
    pnpm --filter @jude/web typecheck

# Apply ruff fixes + formatting and prettier
fmt:
    uv run --frozen ruff check --fix
    uv run --frozen ruff format
    pnpm --filter @jude/web format

# Prove every gate rejects a seeded violation and accepts its clean counterpart
lint-selftest:
    uv run --frozen pytest -m lint_selftest

# Install the pre-commit and commit-msg git hooks
hooks:
    uv run --frozen pre-commit install
