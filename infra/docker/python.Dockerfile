# syntax=docker/dockerfile:1
# Shared image for Python workspace members (api, worker, storage-fake).
# Build context: repository root. Select the member with --build-arg PACKAGE=<uv package name>.
# Base images pinned by tag + index digest (IDR-09); linux/amd64 only.
ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.10.6@sha256:2f2ccd27bbf953ec7a9e3153a4563705e41c852a5e1912b438fc44d88d6cb52c

FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS build
ARG PACKAGE
COPY --from=uv /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/kernel packages/kernel
COPY packages/platform packages/platform
COPY services services
COPY tools/storage_fake tools/storage_fake
RUN test -n "${PACKAGE}" && uv sync --locked --no-dev --no-editable --package "${PACKAGE}"

FROM ${PYTHON_IMAGE}
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin jude \
 && install -d -o 10001 -g 10001 /var/lib/jude
COPY --from=build /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:${PATH} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
USER 10001
