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

# Lint/format/type gates arrive with XC-FND-04
lint:
    @echo "lint tooling is set up by XC-FND-04 (ruff, mypy, eslint, import-linter)"
